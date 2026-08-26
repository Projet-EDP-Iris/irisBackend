from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import get_db
from app.main import app
from app.models.base import Base
from app.models.user import User

# Create a test database engine (in-memory SQLite)
TEST_DATABASE_URL = "sqlite:///./test.db"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Override the get_db dependency
def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

BASE = "/api/v1/users"

# Test data
TEST_USER_EMAIL = "testuser@example.com"
TEST_USER_PASSWORD = "Secret12!"
TEST_ADMIN_EMAIL = "admin@example.com"
TEST_ADMIN_PASSWORD = "Admin123!"

@pytest.fixture(autouse=True)
def setup_database():
    """Reset database before each test"""
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


def _verify_user(email: str) -> None:
    """Directly mark a user's email as verified in the test DB."""
    db = TestSessionLocal()
    try:
        user = db.query(User).filter_by(email=email).first()
        if user:
            user.is_email_verified = True
            db.commit()
    finally:
        db.close()


def _create_verified_user(email: str, password: str, role: str = "regular"):
    """Create a user via the API and immediately mark their email as verified."""
    resp = client.post(
        f"{BASE}/",
        json={"email": email, "password": password, "role": role},
    )
    if resp.status_code == 201:
        _verify_user(email)
    return resp


def test_create_user_api():
    """Test creating a new user account"""
    response = client.post(
        f"{BASE}/",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "role": "regular"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == TEST_USER_EMAIL
    assert data["role"] == "regular"
    assert "id" in data
    assert "password" not in data
    assert "password_hash" not in data
    assert data["is_email_verified"] is False


def test_create_user_duplicate_email():
    """Test that duplicate email returns 400"""
    # Create first user
    client.post(
        f"{BASE}/",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "role": "regular"
        }
    )

    # Try to create duplicate
    response = client.post(
        f"{BASE}/",
        json={
            "email": TEST_USER_EMAIL,
            "password": "Different1!",
            "role": "regular"
        }
    )
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"].lower()

def test_create_user_weak_password():
    """Test that weak password returns 422"""
    response = client.post(
        f"{BASE}/",
        json={
            "email": "weak@example.com",
            "password": "weak",
            "role": "regular"
        }
    )
    assert response.status_code == 422

def test_login_success():
    """Test successful login returns JWT token"""
    _create_verified_user(TEST_USER_EMAIL, TEST_USER_PASSWORD)

    response = client.post(
        f"{BASE}/login",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert len(data["access_token"]) > 0

def test_login_unverified_user():
    """Unverified users can now login — email verification is no longer required to access the app."""
    client.post(
        f"{BASE}/",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "role": "regular"
        }
    )
    # Do NOT verify email — login should still succeed
    response = client.post(
        f"{BASE}/login",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        }
    )
    assert response.status_code == 200
    assert "access_token" in response.json()

def test_login_wrong_password():
    """Test login with wrong password returns 401"""
    _create_verified_user(TEST_USER_EMAIL, TEST_USER_PASSWORD)

    response = client.post(
        f"{BASE}/login",
        json={
            "email": TEST_USER_EMAIL,
            "password": "WrongPass1!"
        }
    )
    assert response.status_code == 401
    assert "incorrect" in response.json()["detail"].lower()

def test_login_nonexistent_user():
    """Test login with non-existent user returns 401"""
    response = client.post(
        f"{BASE}/login",
        json={
            "email": "nonexistent@example.com",
            "password": "SomePass1!"
        }
    )
    assert response.status_code == 401

def test_get_current_user():
    """Test getting current user info with valid token"""
    _create_verified_user(TEST_USER_EMAIL, TEST_USER_PASSWORD)

    login_response = client.post(
        f"{BASE}/login",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        }
    )
    token = login_response.json()["access_token"]

    response = client.get(
        f"{BASE}/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == TEST_USER_EMAIL
    assert data["role"] == "regular"

def test_get_current_user_no_token():
    """Test getting current user without token returns 403"""
    response = client.get(f"{BASE}/me")
    assert response.status_code == 403

def test_get_current_user_invalid_token():
    """Test getting current user with invalid token returns 401"""
    response = client.get(
        f"{BASE}/me",
        headers={"Authorization": "Bearer invalid_token_here"}
    )
    assert response.status_code == 401

def test_get_user_by_id():
    """Test getting a specific user by ID"""
    create_response = _create_verified_user(TEST_USER_EMAIL, TEST_USER_PASSWORD)
    user_id = create_response.json()["id"]

    login_response = client.post(
        f"{BASE}/login",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        }
    )
    token = login_response.json()["access_token"]

    response = client.get(
        f"{BASE}/{user_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == TEST_USER_EMAIL
    assert data["id"] == user_id

def test_get_user_not_found():
    """Test getting non-existent user returns 404"""
    _create_verified_user(TEST_USER_EMAIL, TEST_USER_PASSWORD)

    login_response = client.post(
        f"{BASE}/login",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        }
    )
    token = login_response.json()["access_token"]

    response = client.get(
        f"{BASE}/99999",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404

def test_update_own_user():
    """Test user can update their own information"""
    create_response = _create_verified_user(TEST_USER_EMAIL, TEST_USER_PASSWORD)
    user_id = create_response.json()["id"]

    login_response = client.post(
        f"{BASE}/login",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        }
    )
    token = login_response.json()["access_token"]

    response = client.patch(
        f"{BASE}/{user_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "newemail@example.com"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "newemail@example.com"

def test_update_own_user_cannot_change_role():
    """A regular user must not be able to self-promote via PATCH /{user_id}."""
    create_response = _create_verified_user(TEST_USER_EMAIL, TEST_USER_PASSWORD)
    user_id = create_response.json()["id"]

    login_response = client.post(
        f"{BASE}/login",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        }
    )
    token = login_response.json()["access_token"]

    response = client.patch(
        f"{BASE}/{user_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "admin"}
    )
    assert response.status_code == 403

def test_update_user_password():
    """Test user can update their password via PATCH /{user_id}"""
    create_response = _create_verified_user(TEST_USER_EMAIL, TEST_USER_PASSWORD)
    user_id = create_response.json()["id"]

    login_response = client.post(
        f"{BASE}/login",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        }
    )
    token = login_response.json()["access_token"]

    new_password = "NewPass123!"
    response = client.patch(
        f"{BASE}/{user_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": new_password}
    )
    assert response.status_code == 200

    # Verify can login with new password
    login_response = client.post(
        f"{BASE}/login",
        json={
            "email": TEST_USER_EMAIL,
            "password": new_password
        }
    )
    assert login_response.status_code == 200

def test_update_other_user_forbidden():
    """Test regular user cannot update another user"""
    _create_verified_user("user1@example.com", "Pass1234!")
    client.post(
        f"{BASE}/",
        json={
            "email": "user2@example.com",
            "password": "Pass1234!",
            "role": "regular"
        }
    )
    user2_id = (
        TestSessionLocal()
        .query(User)
        .filter_by(email="user2@example.com")
        .first()
        .id
    )

    login_response = client.post(
        f"{BASE}/login",
        json={
            "email": "user1@example.com",
            "password": "Pass1234!"
        }
    )
    token = login_response.json()["access_token"]

    response = client.patch(
        f"{BASE}/{user2_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "hacked@example.com"}
    )
    assert response.status_code == 403

def test_admin_can_update_other_user():
    """Test admin can update other users"""
    user_response = client.post(
        f"{BASE}/",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "role": "regular"
        }
    )
    user_id = user_response.json()["id"]

    _create_verified_user(TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD, role="admin")

    login_response = client.post(
        f"{BASE}/login",
        json={
            "email": TEST_ADMIN_EMAIL,
            "password": TEST_ADMIN_PASSWORD
        }
    )
    token = login_response.json()["access_token"]

    response = client.patch(
        f"{BASE}/{user_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"has_subscription": True}
    )
    assert response.status_code == 200
    assert response.json()["has_subscription"] is True

def test_delete_own_user():
    """Test user can delete their own account"""
    create_response = _create_verified_user(TEST_USER_EMAIL, TEST_USER_PASSWORD)
    user_id = create_response.json()["id"]

    login_response = client.post(
        f"{BASE}/login",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        }
    )
    token = login_response.json()["access_token"]

    response = client.delete(
        f"{BASE}/{user_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 204

    # Verify user is deleted (token now invalid)
    get_response = client.get(
        f"{BASE}/{user_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert get_response.status_code == 401  # Token is now invalid

def test_delete_other_user_forbidden():
    """Test regular user cannot delete another user"""
    _create_verified_user("user1@example.com", "Pass1234!")
    user2_response = client.post(
        f"{BASE}/",
        json={
            "email": "user2@example.com",
            "password": "Pass1234!",
            "role": "regular"
        }
    )
    user2_id = user2_response.json()["id"]

    login_response = client.post(
        f"{BASE}/login",
        json={
            "email": "user1@example.com",
            "password": "Pass1234!"
        }
    )
    token = login_response.json()["access_token"]

    response = client.delete(
        f"{BASE}/{user2_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403

def test_admin_can_delete_other_user():
    """Test admin can delete other users"""
    user_response = client.post(
        f"{BASE}/",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "role": "regular"
        }
    )
    user_id = user_response.json()["id"]

    _create_verified_user(TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD, role="admin")

    login_response = client.post(
        f"{BASE}/login",
        json={
            "email": TEST_ADMIN_EMAIL,
            "password": TEST_ADMIN_PASSWORD
        }
    )
    token = login_response.json()["access_token"]

    response = client.delete(
        f"{BASE}/{user_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 204


class TestCaptcha:
    """Tests pour le CAPTCHA Turnstile sur POST /users/.

    On patche app.core.captcha.settings pour forcer TURNSTILE_ENABLED=True
    indépendamment du .env local, et on mocke httpx.AsyncClient pour éviter
    tout appel réseau réel vers Cloudflare (verify_turnstile est asynchrone
    pour ne pas bloquer la boucle d'événements le temps de l'appel réseau).
    """

    def _mock_async_client(self, success: bool | None = None, side_effect: Exception | None = None) -> MagicMock:
        resp = MagicMock()
        resp.json.return_value = {"success": success}
        mock_post = AsyncMock(side_effect=side_effect) if side_effect else AsyncMock(return_value=resp)
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=MagicMock(post=mock_post))
        mock_client.__aexit__ = AsyncMock(return_value=None)
        return mock_client

    @patch("app.core.captcha.settings")
    @patch("app.core.captcha.httpx.AsyncClient")
    def test_valid_captcha_token_creates_user(self, mock_async_client_cls, mock_settings):
        """Token validé par Cloudflare → inscription réussit (201)."""
        mock_settings.TURNSTILE_ENABLED = True
        mock_settings.TURNSTILE_SECRET_KEY = "test-secret"
        mock_async_client_cls.return_value = self._mock_async_client(success=True)

        r = client.post(f"{BASE}/", json={
            "email": "captcha_ok@example.com",
            "password": "Secret12!",
            "role": "regular",
            "captcha_token": "valid-token",
        })
        assert r.status_code == 201

    @patch("app.core.captcha.settings")
    @patch("app.core.captcha.httpx.AsyncClient")
    def test_rejected_captcha_token_returns_400(self, mock_async_client_cls, mock_settings):
        """Token rejeté par Cloudflare → 400 CAPTCHA validation failed."""
        mock_settings.TURNSTILE_ENABLED = True
        mock_settings.TURNSTILE_SECRET_KEY = "test-secret"
        mock_async_client_cls.return_value = self._mock_async_client(success=False)

        r = client.post(f"{BASE}/", json={
            "email": "captcha_fail@example.com",
            "password": "Secret12!",
            "role": "regular",
            "captcha_token": "invalid-token",
        })
        assert r.status_code == 400
        assert "captcha" in r.json()["detail"].lower()

    @patch("app.core.captcha.settings")
    @patch("app.core.captcha.httpx.AsyncClient")
    def test_captcha_network_error_returns_400(self, mock_async_client_cls, mock_settings):
        """Erreur réseau vers Cloudflare → fail-closed → 400."""
        mock_settings.TURNSTILE_ENABLED = True
        mock_settings.TURNSTILE_SECRET_KEY = "test-secret"
        mock_async_client_cls.return_value = self._mock_async_client(side_effect=Exception("network error"))

        r = client.post(f"{BASE}/", json={
            "email": "captcha_err@example.com",
            "password": "Secret12!",
            "role": "regular",
            "captcha_token": "any-token",
        })
        assert r.status_code == 400

    @patch("app.core.captcha.settings")
    @patch("app.core.captcha.httpx.AsyncClient")
    def test_login_rejects_invalid_captcha(self, mock_async_client_cls, mock_settings):
        """Token rejeté par Cloudflare au login → 400, pas de token émis."""
        mock_settings.TURNSTILE_ENABLED = True
        mock_settings.TURNSTILE_SECRET_KEY = "test-secret"
        mock_async_client_cls.return_value = self._mock_async_client(success=False)

        r = client.post(f"{BASE}/login", json={
            "email": "someone@example.com",
            "password": "Secret12!",
            "captcha_token": "invalid-token",
        })
        assert r.status_code == 400
