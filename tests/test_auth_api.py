"""
Tests for the authentication & account recovery flows:
  - POST /api/v1/auth/forgot-password
  - POST /api/v1/auth/reset-password
  - POST /api/v1/auth/verify-email
  - POST /api/v1/auth/resend-verification
  - PATCH /api/v1/users/me/change-password

EMAIL_ENABLED defaults to False, so no SMTP calls are made.
Tokens are retrieved directly from the test DB for end-to-end validation.
"""
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.rate_limiter import forgot_password_limiter
from app.db.database import get_db
from app.main import app
from app.models.auth_token import AuthToken, TokenType
from app.models.base import Base
from app.models.user import User

TEST_DATABASE_URL = "sqlite:///./test_auth.db"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

USERS_BASE = "/api/v1/users"
AUTH_BASE = "/api/v1/auth"

TEST_EMAIL = "authtest@example.com"
TEST_PASSWORD = "AuthPass1!"


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    # Reset in-memory rate limiter so rate-limit tests don't bleed into other tests
    forgot_password_limiter._buckets.clear()
    yield
    Base.metadata.drop_all(bind=test_engine)


def _register_user(email: str = TEST_EMAIL, password: str = TEST_PASSWORD, role: str = "regular"):
    resp = client.post(f"{USERS_BASE}/", json={"email": email, "password": password, "role": role})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _verify_user(email: str) -> None:
    db = TestSessionLocal()
    try:
        user = db.query(User).filter_by(email=email).first()
        if user:
            user.is_email_verified = True
            db.commit()
    finally:
        db.close()


def _register_and_verify(email: str = TEST_EMAIL, password: str = TEST_PASSWORD, role: str = "regular"):
    data = _register_user(email, password, role)
    _verify_user(email)
    return data


def _login(email: str = TEST_EMAIL, password: str = TEST_PASSWORD) -> str:
    resp = client.post(f"{USERS_BASE}/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _get_token_from_db(user_id: int, token_type: TokenType) -> str:
    db = TestSessionLocal()
    try:
        record = (
            db.query(AuthToken)
            .filter_by(user_id=user_id, token_type=token_type, used=False)
            .order_by(AuthToken.id.desc())
            .first()
        )
        assert record is not None, f"No active {token_type} token found for user {user_id}"
        return record.token
    finally:
        db.close()


def _expire_token(user_id: int, token_type: TokenType) -> None:
    db = TestSessionLocal()
    try:
        record = (
            db.query(AuthToken)
            .filter_by(user_id=user_id, token_type=token_type, used=False)
            .first()
        )
        if record:
            record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Forgot Password
# ---------------------------------------------------------------------------

class TestForgotPassword:
    def test_returns_200_for_unknown_email(self):
        resp = client.post(f"{AUTH_BASE}/forgot-password", json={"email": "nobody@example.com"})
        assert resp.status_code == 200
        assert "reset link" in resp.json()["message"].lower()

    def test_returns_200_for_known_email(self):
        _register_user()
        resp = client.post(f"{AUTH_BASE}/forgot-password", json={"email": TEST_EMAIL})
        assert resp.status_code == 200

    def test_creates_token_in_db(self):
        data = _register_user()
        client.post(f"{AUTH_BASE}/forgot-password", json={"email": TEST_EMAIL})
        token_str = _get_token_from_db(data["id"], TokenType.password_reset)
        assert len(token_str) > 20

    def test_rate_limit_blocks_after_3_requests(self):
        _register_user()
        for _ in range(3):
            client.post(f"{AUTH_BASE}/forgot-password", json={"email": TEST_EMAIL})
        resp = client.post(f"{AUTH_BASE}/forgot-password", json={"email": TEST_EMAIL})
        assert resp.status_code == 429

    def test_rate_limit_returns_retry_after_header(self):
        _register_user()
        for _ in range(3):
            client.post(f"{AUTH_BASE}/forgot-password", json={"email": TEST_EMAIL})
        resp = client.post(f"{AUTH_BASE}/forgot-password", json={"email": TEST_EMAIL})
        assert "retry-after" in resp.headers


# ---------------------------------------------------------------------------
# Reset Password
# ---------------------------------------------------------------------------

class TestResetPassword:
    def test_valid_token_resets_password(self):
        data = _register_user()
        client.post(f"{AUTH_BASE}/forgot-password", json={"email": TEST_EMAIL})
        token_str = _get_token_from_db(data["id"], TokenType.password_reset)

        resp = client.post(
            f"{AUTH_BASE}/reset-password",
            json={"token": token_str, "new_password": "NewPass99!"},
        )
        assert resp.status_code == 200

    def test_can_login_after_reset(self):
        data = _register_and_verify()
        client.post(f"{AUTH_BASE}/forgot-password", json={"email": TEST_EMAIL})
        token_str = _get_token_from_db(data["id"], TokenType.password_reset)
        client.post(
            f"{AUTH_BASE}/reset-password",
            json={"token": token_str, "new_password": "NewPass99!"},
        )
        login_resp = client.post(
            f"{USERS_BASE}/login",
            json={"email": TEST_EMAIL, "password": "NewPass99!"},
        )
        assert login_resp.status_code == 200

    def test_invalid_token_returns_400(self):
        resp = client.post(
            f"{AUTH_BASE}/reset-password",
            json={"token": "totally-invalid-token", "new_password": "NewPass99!"},
        )
        assert resp.status_code == 400

    def test_expired_token_returns_400(self):
        data = _register_user()
        client.post(f"{AUTH_BASE}/forgot-password", json={"email": TEST_EMAIL})
        _expire_token(data["id"], TokenType.password_reset)
        # Read directly since token is now expired (consume_token returns None)
        db = TestSessionLocal()
        try:
            record = db.query(AuthToken).filter_by(user_id=data["id"]).first()
            raw = record.token
        finally:
            db.close()

        resp = client.post(
            f"{AUTH_BASE}/reset-password",
            json={"token": raw, "new_password": "NewPass99!"},
        )
        assert resp.status_code == 400

    def test_used_token_returns_400(self):
        data = _register_user()
        client.post(f"{AUTH_BASE}/forgot-password", json={"email": TEST_EMAIL})
        token_str = _get_token_from_db(data["id"], TokenType.password_reset)

        # Use it once
        client.post(
            f"{AUTH_BASE}/reset-password",
            json={"token": token_str, "new_password": "NewPass99!"},
        )
        # Try again
        resp = client.post(
            f"{AUTH_BASE}/reset-password",
            json={"token": token_str, "new_password": "AnotherPass1!"},
        )
        assert resp.status_code == 400

    def test_weak_new_password_returns_422(self):
        data = _register_user()
        client.post(f"{AUTH_BASE}/forgot-password", json={"email": TEST_EMAIL})
        token_str = _get_token_from_db(data["id"], TokenType.password_reset)

        resp = client.post(
            f"{AUTH_BASE}/reset-password",
            json={"token": token_str, "new_password": "weak"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Verify Email
# ---------------------------------------------------------------------------

class TestVerifyEmail:
    def test_valid_token_verifies_email(self):
        data = _register_user()
        token_str = _get_token_from_db(data["id"], TokenType.email_verification)

        resp = client.post(f"{AUTH_BASE}/verify-email", json={"token": token_str})
        assert resp.status_code == 200

        db = TestSessionLocal()
        try:
            user = db.query(User).filter_by(id=data["id"]).first()
            assert user.is_email_verified is True
        finally:
            db.close()

    def test_can_login_after_verification(self):
        data = _register_user()
        token_str = _get_token_from_db(data["id"], TokenType.email_verification)
        client.post(f"{AUTH_BASE}/verify-email", json={"token": token_str})

        login_resp = client.post(
            f"{USERS_BASE}/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        assert login_resp.status_code == 200

    def test_invalid_token_returns_400(self):
        resp = client.post(f"{AUTH_BASE}/verify-email", json={"token": "garbage-token"})
        assert resp.status_code == 400

    def test_expired_token_returns_400(self):
        data = _register_user()
        _expire_token(data["id"], TokenType.email_verification)

        db = TestSessionLocal()
        try:
            record = db.query(AuthToken).filter_by(user_id=data["id"]).first()
            raw = record.token
        finally:
            db.close()

        resp = client.post(f"{AUTH_BASE}/verify-email", json={"token": raw})
        assert resp.status_code == 400

    def test_used_token_returns_400(self):
        data = _register_user()
        token_str = _get_token_from_db(data["id"], TokenType.email_verification)

        client.post(f"{AUTH_BASE}/verify-email", json={"token": token_str})
        resp = client.post(f"{AUTH_BASE}/verify-email", json={"token": token_str})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Resend Verification
# ---------------------------------------------------------------------------

class TestResendVerification:
    def test_always_returns_200_for_unknown_email(self):
        resp = client.post(
            f"{AUTH_BASE}/resend-verification", json={"email": "unknown@example.com"}
        )
        assert resp.status_code == 200

    def test_always_returns_200_for_known_unverified(self):
        _register_user()
        resp = client.post(f"{AUTH_BASE}/resend-verification", json={"email": TEST_EMAIL})
        assert resp.status_code == 200

    def test_creates_new_token_on_resend(self):
        data = _register_user()
        old_token = _get_token_from_db(data["id"], TokenType.email_verification)
        client.post(f"{AUTH_BASE}/resend-verification", json={"email": TEST_EMAIL})
        new_token = _get_token_from_db(data["id"], TokenType.email_verification)
        assert old_token != new_token

    def test_already_verified_user_returns_200_silently(self):
        _register_and_verify()
        resp = client.post(f"{AUTH_BASE}/resend-verification", json={"email": TEST_EMAIL})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Change Password
# ---------------------------------------------------------------------------

class TestChangePassword:
    def test_authenticated_user_can_change_password(self):
        _register_and_verify()
        token = _login()
        resp = client.patch(
            f"{USERS_BASE}/me/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"current_password": TEST_PASSWORD, "new_password": "Changed99!"},
        )
        assert resp.status_code == 200

    def test_can_login_with_new_password_after_change(self):
        _register_and_verify()
        token = _login()
        client.patch(
            f"{USERS_BASE}/me/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"current_password": TEST_PASSWORD, "new_password": "Changed99!"},
        )
        login_resp = client.post(
            f"{USERS_BASE}/login",
            json={"email": TEST_EMAIL, "password": "Changed99!"},
        )
        assert login_resp.status_code == 200

    def test_wrong_current_password_returns_400(self):
        _register_and_verify()
        token = _login()
        resp = client.patch(
            f"{USERS_BASE}/me/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"current_password": "WrongOld1!", "new_password": "Changed99!"},
        )
        assert resp.status_code == 400
        assert "incorrect" in resp.json()["detail"].lower()

    def test_weak_new_password_returns_422(self):
        _register_and_verify()
        token = _login()
        resp = client.patch(
            f"{USERS_BASE}/me/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"current_password": TEST_PASSWORD, "new_password": "weak"},
        )
        assert resp.status_code == 422

    def test_unauthenticated_returns_403(self):
        resp = client.patch(
            f"{USERS_BASE}/me/change-password",
            json={"current_password": TEST_PASSWORD, "new_password": "Changed99!"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Login email verification guard (integration)
# ---------------------------------------------------------------------------

class TestLoginVerificationGuard:
    def test_unverified_user_cannot_login(self):
        _register_user()
        resp = client.post(
            f"{USERS_BASE}/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        assert resp.status_code == 403
        assert "verified" in resp.json()["detail"].lower()

    def test_verified_user_can_login(self):
        _register_and_verify()
        resp = client.post(
            f"{USERS_BASE}/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        assert resp.status_code == 200
