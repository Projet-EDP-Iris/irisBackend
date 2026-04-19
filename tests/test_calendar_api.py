"""
API integration tests for the calendar endpoints:
  PATCH /api/v1/user/users/me/calendar-setup  — save provider + Apple credentials
  POST  /api/v1/calendar/confirm/{email_id}   — create event in one click

These tests use an in-memory SQLite database and mock out all external
calendar API calls (Google, Apple), so no real credentials are needed.

How the mocking works:
  @patch("app.api.endpoints.calendar.create_google_calendar_event", return_value="evt_id")
  replaces the real function with a fake that returns "evt_id" immediately.
  This lets us verify OUR endpoint logic (auth, DB writes, error handling)
  without actually calling Google's servers.
"""
import os
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_TEST_KEY = Fernet.generate_key().decode()
os.environ.setdefault("SECRET_ENCRYPTION_KEY", _TEST_KEY)

from app.db.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.email import Email  # noqa: E402, F401 — needed to register the table
from app.models.user import User  # noqa: E402, F401

TEST_DB_URL = "sqlite:///./test_calendar.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

USER_EMAIL    = "caltest@example.com"
USER_PASSWORD = "CalTest1!"


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _create_and_login():
    """Create a test user and return their Bearer token."""
    client.post(
        "/api/v1/user/users/",
        json={"email": USER_EMAIL, "password": USER_PASSWORD, "role": "regular"},
    )
    r = client.post(
        "/api/v1/user/users/login",
        json={"email": USER_EMAIL, "password": USER_PASSWORD},
    )
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _seed_email_with_slots(token: str) -> int:
    """Insert a minimal Email row with predicted_slots and return its id."""
    db = TestSession()
    try:
        # Get user id from token (easier to just query by email)
        user = db.query(User).filter(User.email == USER_EMAIL).first()
        email = Email(
            message_id="msg_test_001",
            user_id=user.id,
            subject="Réunion projet Q1",
            body="Bonjour, disponible le 18 oct ?",
            status="predicted",
            extraction_data={"participants": ["alice@example.com"]},
            predicted_slots=[
                {"start_time": "2024-10-18T10:00:00", "end_time": "2024-10-18T11:00:00", "score": 0.9, "label": "Proposed"},
                {"start_time": "2024-10-19T14:00:00", "end_time": "2024-10-19T15:00:00", "score": 0.7, "label": "Alternative"},
            ],
        )
        db.add(email)
        db.commit()
        db.refresh(email)
        return email.id
    finally:
        db.close()


# ─────────────────────────────────────────────
# Calendar Setup endpoint tests
# ─────────────────────────────────────────────

class TestCalendarSetup:

    def test_setup_google_provider(self):
        """Saving 'google' as provider succeeds with no extra credentials."""
        token = _create_and_login()
        r = client.patch(
            "/api/v1/user/users/me/calendar-setup",
            headers=_auth(token),
            json={"calendar_provider": "google"},
        )
        assert r.status_code == 200
        assert "google" in r.json()["calendar_providers"]

    def test_setup_apple_provider_with_credentials(self):
        """Saving 'apple' with user + password succeeds."""
        token = _create_and_login()
        r = client.patch(
            "/api/v1/user/users/me/calendar-setup",
            headers=_auth(token),
            json={
                "calendar_provider": "apple",
                "apple_caldav_user": "dan@icloud.com",
                "apple_caldav_password": "xxxx-xxxx-xxxx-xxxx",
            },
        )
        assert r.status_code == 200
        assert "apple" in r.json()["calendar_providers"]

    def test_setup_apple_without_credentials_returns_400(self):
        """'apple' provider with missing credentials must return 400."""
        token = _create_and_login()
        r = client.patch(
            "/api/v1/user/users/me/calendar-setup",
            headers=_auth(token),
            json={"calendar_provider": "apple"},  # no apple_caldav_user / password
        )
        assert r.status_code == 400
        assert "required" in r.json()["detail"].lower()

    def test_setup_invalid_provider_returns_400(self):
        """An unknown provider name must return 400."""
        token = _create_and_login()
        r = client.patch(
            "/api/v1/user/users/me/calendar-setup",
            headers=_auth(token),
            json={"calendar_provider": "yahoo"},
        )
        assert r.status_code == 400

    def test_setup_unauthenticated_returns_403(self):
        """Calendar setup requires authentication."""
        r = client.patch(
            "/api/v1/user/users/me/calendar-setup",
            json={"calendar_provider": "google"},
        )
        assert r.status_code == 403

    def test_apple_password_is_not_stored_in_plain_text(self):
        """The raw App Password must never appear in plain text in the DB."""
        from app.core.encryption import decrypt

        token = _create_and_login()
        plain_password = "xxxx-xxxx-xxxx-xxxx"
        client.patch(
            "/api/v1/user/users/me/calendar-setup",
            headers=_auth(token),
            json={
                "calendar_provider": "apple",
                "apple_caldav_user": "dan@icloud.com",
                "apple_caldav_password": plain_password,
            },
        )

        db = TestSession()
        user = db.query(User).filter(User.email == USER_EMAIL).first()
        stored = user.apple_caldav_password
        db.close()

        # Stored value must NOT be the plain password
        assert stored != plain_password
        # But must decrypt back to the original
        assert decrypt(stored) == plain_password


# ─────────────────────────────────────────────
# Confirm & Add to Calendar endpoint tests
# ─────────────────────────────────────────────

class TestConfirmCalendar:

    def test_confirm_google_event_created(self):
        """
        Confirm with Google provider: Google service is called, email.status
        becomes 'confirmed', and the event ID is returned.
        """
        token = _create_and_login()
        # Set user's calendar provider to Google
        client.patch(
            "/api/v1/user/users/me/calendar-setup",
            headers=_auth(token),
            json={"calendar_provider": "google"},
        )
        email_id = _seed_email_with_slots(token)

        with patch(
            "app.api.endpoints.calendar.create_google_calendar_event",
            return_value="google_event_xyz",
        ):
            r = client.post(
                f"/api/v1/calendar/confirm/{email_id}",
                headers=_auth(token),
                json={"slot_index": 0},
            )

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "confirmed"
        assert body["providers"][0]["provider"] == "google"
        assert body["providers"][0]["event_id"] == "google_event_xyz"

    def test_confirm_apple_event_created(self):
        """Confirm with Apple provider: Apple service is called, returns UID."""
        token = _create_and_login()
        client.patch(
            "/api/v1/user/users/me/calendar-setup",
            headers=_auth(token),
            json={
                "calendar_provider": "apple",
                "apple_caldav_user": "dan@icloud.com",
                "apple_caldav_password": "xxxx-xxxx-xxxx-xxxx",
            },
        )
        email_id = _seed_email_with_slots(token)

        with patch(
            "app.api.endpoints.calendar.create_apple_calendar_event",
            return_value="apple-uid-abc-def",
        ):
            r = client.post(
                f"/api/v1/calendar/confirm/{email_id}",
                headers=_auth(token),
                json={"slot_index": 0},
            )

        assert r.status_code == 200
        assert r.json()["providers"][0]["event_id"] == "apple-uid-abc-def"
        assert r.json()["providers"][0]["provider"] == "apple"

    def test_confirm_picks_correct_slot_by_index(self):
        """slot_index=1 must book the second slot, not the first."""
        token = _create_and_login()
        client.patch(
            "/api/v1/user/users/me/calendar-setup",
            headers=_auth(token),
            json={"calendar_provider": "google"},
        )
        email_id = _seed_email_with_slots(token)

        with patch(
            "app.api.endpoints.calendar.create_google_calendar_event",
            return_value="evt_slot1",
        ) as mock_create:
            client.post(
                f"/api/v1/calendar/confirm/{email_id}",
                headers=_auth(token),
                json={"slot_index": 1},
            )

        # The start_time passed to the service must match slot index 1
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["start_time"].isoformat().startswith("2024-10-19")

    def test_confirm_persists_event_id_and_status_in_db(self):
        """After confirm, Email.calendar_event_id and Email.status must be updated in DB."""
        token = _create_and_login()
        client.patch(
            "/api/v1/user/users/me/calendar-setup",
            headers=_auth(token),
            json={"calendar_provider": "google"},
        )
        email_id = _seed_email_with_slots(token)

        with patch(
            "app.api.endpoints.calendar.create_google_calendar_event",
            return_value="persisted_event_id",
        ):
            client.post(
                f"/api/v1/calendar/confirm/{email_id}",
                headers=_auth(token),
                json={"slot_index": 0},
            )

        db = TestSession()
        email = db.query(Email).filter(Email.id == email_id).first()
        db.close()

        assert email.calendar_event_id == "persisted_event_id"
        assert email.status == "confirmed"

    def test_confirm_invalid_slot_index_returns_400(self):
        """Requesting slot_index=99 when only 2 slots exist must return 400."""
        token = _create_and_login()
        client.patch(
            "/api/v1/user/users/me/calendar-setup",
            headers=_auth(token),
            json={"calendar_provider": "google"},
        )
        email_id = _seed_email_with_slots(token)

        r = client.post(
            f"/api/v1/calendar/confirm/{email_id}",
            headers=_auth(token),
            json={"slot_index": 99},
        )
        assert r.status_code == 400
        assert "out of range" in r.json()["detail"]

    def test_confirm_email_not_found_returns_404(self):
        """Confirming a non-existent email ID must return 404."""
        token = _create_and_login()
        client.patch(
            "/api/v1/user/users/me/calendar-setup",
            headers=_auth(token),
            json={"calendar_provider": "google"},
        )

        r = client.post(
            "/api/v1/calendar/confirm/99999",
            headers=_auth(token),
            json={"slot_index": 0},
        )
        assert r.status_code == 404

    def test_confirm_no_slots_returns_400(self):
        """If the email has no predicted slots yet, return 400."""
        token = _create_and_login()
        client.patch(
            "/api/v1/user/users/me/calendar-setup",
            headers=_auth(token),
            json={"calendar_provider": "google"},
        )

        # Insert email WITHOUT predicted_slots
        db = TestSession()
        user = db.query(User).filter(User.email == USER_EMAIL).first()
        email = Email(
            message_id="msg_no_slots",
            user_id=user.id,
            subject="No slots yet",
            status="detected",
        )
        db.add(email)
        db.commit()
        email_id = email.id
        db.close()

        r = client.post(
            f"/api/v1/calendar/confirm/{email_id}",
            headers=_auth(token),
            json={"slot_index": 0},
        )
        assert r.status_code == 400
        assert "prediction" in r.json()["detail"].lower()

    def test_confirm_no_provider_configured_returns_400(self):
        """If the user has no calendar_provider set, return 400 with a helpful message."""
        token = _create_and_login()
        # Do NOT call calendar-setup — user has no provider
        email_id = _seed_email_with_slots(token)

        r = client.post(
            f"/api/v1/calendar/confirm/{email_id}",
            headers=_auth(token),
            json={"slot_index": 0},
        )
        assert r.status_code == 400
        assert "calendar-setup" in r.json()["detail"]

    def test_confirm_unauthenticated_returns_403(self):
        """Confirm endpoint requires authentication."""
        r = client.post(
            "/api/v1/calendar/confirm/1",
            json={"slot_index": 0},
        )
        assert r.status_code == 403

    def test_confirm_apple_missing_credentials_returns_error_in_provider(self):
        """If provider is 'apple' but credentials were never saved, the provider
        result must contain an error (partial-failure tolerance)."""
        token = _create_and_login()

        # Manually set providers to ['apple'] without storing credentials
        db = TestSession()
        user = db.query(User).filter(User.email == USER_EMAIL).first()
        user.calendar_providers = ["apple"]
        user.calendar_provider = "apple"
        db.commit()
        db.close()

        email_id = _seed_email_with_slots(token)

        r = client.post(
            f"/api/v1/calendar/confirm/{email_id}",
            headers=_auth(token),
            json={"slot_index": 0},
        )
        assert r.status_code == 200
        providers = r.json()["providers"]
        assert len(providers) == 1
        assert providers[0]["provider"] == "apple"
        assert providers[0]["error"] is not None
        assert "credentials" in providers[0]["error"].lower()

    def test_confirm_google_api_error_reported_in_providers(self):
        """If the Google Calendar API raises an error, the response still returns 200
        (partial-failure tolerance) but the provider entry contains the error."""
        token = _create_and_login()
        client.patch(
            "/api/v1/user/users/me/calendar-setup",
            headers=_auth(token),
            json={"calendar_provider": "google"},
        )
        email_id = _seed_email_with_slots(token)

        with patch(
            "app.api.endpoints.calendar.create_google_calendar_event",
            side_effect=Exception("API quota exceeded"),
        ):
            r = client.post(
                f"/api/v1/calendar/confirm/{email_id}",
                headers=_auth(token),
                json={"slot_index": 0},
            )

        assert r.status_code == 200
        providers = r.json()["providers"]
        assert len(providers) == 1
        assert providers[0]["provider"] == "google"
        assert "quota exceeded" in providers[0]["error"].lower()
