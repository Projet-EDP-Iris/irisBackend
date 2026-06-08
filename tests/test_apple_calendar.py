"""
Tests for Apple Calendar integration:
  - app/services/apple_calendar_service.py — test_connection, list_calendars,
    create_apple_calendar_event, update_apple_calendar_event, delete_apple_calendar_event
  - GET /api/v1/auth/apple/status
  - PATCH /api/v1/users/me/calendar-setup with apple provider (bad credentials → 400)

All CalDAV calls are mocked — no real Apple ID or app-specific password is needed.
"""
import os
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_TEST_KEY = Fernet.generate_key().decode()
os.environ.setdefault("SECRET_ENCRYPTION_KEY", _TEST_KEY)

from app.core.config import settings as _settings  # noqa: E402

_settings.SECRET_ENCRYPTION_KEY = _TEST_KEY

from app.core.encryption import encrypt  # noqa: E402
from app.db.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.user import User  # noqa: E402, F401

TEST_DB_URL = "sqlite:///./test_apple.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

APPLE_USER = "user@icloud.com"
APPLE_APP_SPECIFIC_PW = "xxxx-yyyy-zzzz-test"
USER_EMAIL = "appletest@example.com"
USER_PASSWORD = "CiTestUser1!"

# Computed fresh in the autouse fixture so Fernet key is always current.
ENCRYPTED_PW: str = ""


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_db():
    # Re-apply the encryption key each test — other modules may overwrite it.
    global ENCRYPTED_PW
    _settings.SECRET_ENCRYPTION_KEY = _TEST_KEY
    ENCRYPTED_PW = encrypt(APPLE_APP_SPECIFIC_PW)
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _verify_user(email: str) -> None:
    db = TestSession()
    try:
        user = db.query(User).filter_by(email=email).first()
        if user:
            user.is_email_verified = True
            db.commit()
    finally:
        db.close()


def _create_and_login() -> str:
    client.post("/api/v1/users/", json={"email": USER_EMAIL, "password": USER_PASSWORD})
    _verify_user(USER_EMAIL)
    r = client.post("/api/v1/users/login", json={"email": USER_EMAIL, "password": USER_PASSWORD})
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _mock_caldav(calendars=None, raise_on_connect=None):
    """Return a patch context for caldav.DAVClient that simulates a CalDAV server."""
    mock_client = MagicMock()
    mock_principal = MagicMock()

    if raise_on_connect:
        mock_client.principal.side_effect = raise_on_connect
    else:
        mock_client.principal.return_value = mock_principal
        cals = calendars if calendars is not None else [MagicMock(name="Home", url="https://caldav.icloud.com/cal1/")]
        mock_principal.calendars.return_value = cals

    return patch("app.services.apple_calendar_service.caldav.DAVClient", return_value=mock_client)


# ---------------------------------------------------------------------------
# test_connection
# ---------------------------------------------------------------------------

class TestConnection:
    def test_succeeds_with_valid_credentials(self):
        with _mock_caldav():
            from app.services.apple_calendar_service import test_connection
            test_connection(APPLE_USER, ENCRYPTED_PW)  # should not raise

    def test_raises_on_auth_failure(self):
        import caldav.lib.error
        with _mock_caldav(raise_on_connect=caldav.lib.error.AuthorizationError("401")):
            from app.services.apple_calendar_service import test_connection
            with pytest.raises(caldav.lib.error.AuthorizationError):
                test_connection(APPLE_USER, ENCRYPTED_PW)

    def test_raises_when_no_calendars_found(self):
        with _mock_caldav(calendars=[]):
            from app.services.apple_calendar_service import test_connection
            with pytest.raises(RuntimeError, match="No iCloud calendars"):
                test_connection(APPLE_USER, ENCRYPTED_PW)


# ---------------------------------------------------------------------------
# list_calendars
# ---------------------------------------------------------------------------

class TestListCalendars:
    def test_returns_list_of_calendars(self):
        cal1 = MagicMock()
        cal1.name = "Home"
        cal1.url = "https://caldav.icloud.com/cal1/"
        cal2 = MagicMock()
        cal2.name = "Work"
        cal2.url = "https://caldav.icloud.com/cal2/"

        with _mock_caldav(calendars=[cal1, cal2]):
            from app.services.apple_calendar_service import list_calendars
            result = list_calendars(APPLE_USER, ENCRYPTED_PW)

        assert len(result) == 2
        assert result[0]["name"] == "Home"
        assert "url" in result[0]
        assert result[1]["name"] == "Work"


# ---------------------------------------------------------------------------
# update_apple_calendar_event
# ---------------------------------------------------------------------------

class TestUpdateEvent:
    def test_updates_event_and_calls_save(self):
        from datetime import UTC, datetime

        mock_calendar = MagicMock()
        mock_event = MagicMock()
        mock_vevent = MagicMock()
        mock_event.vobject_instance.vevent = mock_vevent
        mock_calendar.search.return_value = [mock_event]

        with _mock_caldav(calendars=[mock_calendar]):
            from app.services.apple_calendar_service import update_apple_calendar_event
            update_apple_calendar_event(
                apple_user=APPLE_USER,
                encrypted_password=ENCRYPTED_PW,
                uid="test-uid-1234",
                summary="Updated Meeting",
                start_time=datetime(2024, 10, 18, 10, 0, tzinfo=UTC),
                end_time=datetime(2024, 10, 18, 11, 0, tzinfo=UTC),
                description="Updated description",
            )

        mock_event.save.assert_called_once()

    def test_raises_when_event_not_found(self):
        from datetime import UTC, datetime

        mock_calendar = MagicMock()
        mock_calendar.search.return_value = []

        with _mock_caldav(calendars=[mock_calendar]):
            from app.services.apple_calendar_service import update_apple_calendar_event
            with pytest.raises(RuntimeError, match="not found"):
                update_apple_calendar_event(
                    apple_user=APPLE_USER,
                    encrypted_password=ENCRYPTED_PW,
                    uid="nonexistent-uid",
                    summary="X",
                    start_time=datetime(2024, 10, 18, 10, 0, tzinfo=UTC),
                    end_time=datetime(2024, 10, 18, 11, 0, tzinfo=UTC),
                )


# ---------------------------------------------------------------------------
# delete_apple_calendar_event
# ---------------------------------------------------------------------------

class TestDeleteEvent:
    def test_deletes_event_and_calls_delete(self):
        mock_calendar = MagicMock()
        mock_event = MagicMock()
        mock_calendar.search.return_value = [mock_event]

        with _mock_caldav(calendars=[mock_calendar]):
            from app.services.apple_calendar_service import delete_apple_calendar_event
            delete_apple_calendar_event(APPLE_USER, ENCRYPTED_PW, uid="test-uid-5678")

        mock_event.delete.assert_called_once()

    def test_raises_when_event_not_found(self):
        mock_calendar = MagicMock()
        mock_calendar.search.return_value = []

        with _mock_caldav(calendars=[mock_calendar]):
            from app.services.apple_calendar_service import delete_apple_calendar_event
            with pytest.raises(RuntimeError, match="not found"):
                delete_apple_calendar_event(APPLE_USER, ENCRYPTED_PW, uid="ghost-uid")


# ---------------------------------------------------------------------------
# GET /auth/apple/status
# ---------------------------------------------------------------------------

class TestAppleStatus:
    def test_returns_not_connected_by_default(self):
        token = _create_and_login()
        r = client.get("/api/v1/auth/apple/status", headers=_auth(token))
        assert r.status_code == 200
        assert r.json()["connected"] is False
        assert r.json()["email"] is None

    def test_returns_connected_after_setup(self):
        token = _create_and_login()
        with patch("app.services.apple_calendar_service.test_connection"):
            client.patch(
                "/api/v1/users/me/calendar-setup",
                headers=_auth(token),
                json={
                    "calendar_provider": "apple",
                    "apple_caldav_user": APPLE_USER,
                    "apple_caldav_password": APPLE_APP_SPECIFIC_PW,
                },
            )
        r = client.get("/api/v1/auth/apple/status", headers=_auth(token))
        assert r.status_code == 200
        assert r.json()["connected"] is True
        assert r.json()["email"] == APPLE_USER

    def test_returns_not_connected_after_disconnect(self):
        token = _create_and_login()
        with patch("app.services.apple_calendar_service.test_connection"):
            client.patch(
                "/api/v1/users/me/calendar-setup",
                headers=_auth(token),
                json={
                    "calendar_provider": "apple",
                    "apple_caldav_user": APPLE_USER,
                    "apple_caldav_password": APPLE_APP_SPECIFIC_PW,
                },
            )
        client.delete("/api/v1/users/me/calendar-disconnect?provider=apple", headers=_auth(token))
        r = client.get("/api/v1/auth/apple/status", headers=_auth(token))
        assert r.status_code == 200
        assert r.json()["connected"] is False

    def test_requires_authentication(self):
        r = client.get("/api/v1/auth/apple/status")
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# calendar-setup validation — bad Apple credentials → 400
# ---------------------------------------------------------------------------

class TestCalendarSetupValidation:
    def test_returns_400_on_invalid_apple_credentials(self):
        import caldav.lib.error

        token = _create_and_login()
        with _mock_caldav(raise_on_connect=caldav.lib.error.AuthorizationError("Bad password")):
            r = client.patch(
                "/api/v1/users/me/calendar-setup",
                headers=_auth(token),
                json={
                    "calendar_provider": "apple",
                    "apple_caldav_user": APPLE_USER,
                    "apple_caldav_password": "wrong-password",
                },
            )
        assert r.status_code == 400
        assert "apple calendar" in r.json()["detail"].lower()

    def test_credentials_not_saved_on_failed_connection(self):
        import caldav.lib.error

        token = _create_and_login()
        with _mock_caldav(raise_on_connect=caldav.lib.error.AuthorizationError("Bad password")):
            client.patch(
                "/api/v1/users/me/calendar-setup",
                headers=_auth(token),
                json={
                    "calendar_provider": "apple",
                    "apple_caldav_user": APPLE_USER,
                    "apple_caldav_password": "wrong-password",
                },
            )
        db = TestSession()
        user = db.query(User).filter_by(email=USER_EMAIL).first()
        db.close()
        assert user.apple_caldav_user is None
        assert user.apple_caldav_password is None
