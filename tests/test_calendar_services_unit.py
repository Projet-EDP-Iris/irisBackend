"""
Unit tests for the Google Calendar and Apple CalDAV service functions.

External calls (Google API, iCloud CalDAV server) are mocked so these tests
run without credentials, internet access, or a calendar account.

What mocking means here: instead of calling the real Google or Apple servers,
we replace those calls with fake objects that return pre-defined responses.
This lets us verify that OUR code (argument building, error handling, return
values) is correct without depending on external infrastructure.
"""
import os
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet

_TEST_KEY = Fernet.generate_key().decode()
os.environ.setdefault("SECRET_ENCRYPTION_KEY", _TEST_KEY)


# ─────────────────────────────────────────────
# Google Calendar Service
# ─────────────────────────────────────────────

class TestGoogleCalendarService:
    """Tests for app/services/google_calendar_service.py"""

    START = datetime(2024, 10, 18, 10, 0, tzinfo=UTC)
    END   = datetime(2024, 10, 18, 11, 0, tzinfo=UTC)

    def _mock_creds(self, valid: bool = True, expired: bool = False):
        creds = MagicMock()
        creds.valid = valid
        creds.expired = expired
        creds.refresh_token = "fake-refresh-token" if expired else None
        return creds

    def test_creates_event_and_returns_id(self, tmp_path):
        """
        Happy path: valid token on disk → Google API called with correct
        arguments → event ID returned.
        """
        # Write a fake token file so _load_creds_for_user finds it
        token_file = tmp_path / "gmail_user_1.json"
        token_file.write_text('{"token": "fake"}')

        fake_event = {"id": "google_event_abc123"}

        with (
            patch("app.services.google_calendar_service.get_token_path_for_user",
                  return_value=str(token_file)),
            patch("app.services.google_calendar_service.Credentials.from_authorized_user_file",
                  return_value=self._mock_creds()),
            patch("app.services.google_calendar_service.build") as mock_build,
        ):
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            # Chain: service.events().insert(...).execute() → fake_event
            mock_service.events.return_value.insert.return_value.execute.return_value = fake_event

            from app.services.google_calendar_service import create_google_calendar_event
            event_id = create_google_calendar_event(
                user_id=1,
                summary="Réunion projet Q1",
                start_time=self.START,
                end_time=self.END,
                attendees=["alice@example.com"],
                description="Test meeting",
            )

        assert event_id == "google_event_abc123"

        # Verify the API was called with calendarId="primary" and sendUpdates="all"
        insert_call = mock_service.events.return_value.insert.call_args
        assert insert_call.kwargs["calendarId"] == "primary"
        assert insert_call.kwargs["sendUpdates"] == "all"

    def test_attendees_are_included_in_event_body(self, tmp_path):
        """Attendee emails must be formatted as [{'email': ...}] for the Google API."""
        token_file = tmp_path / "gmail_user_2.json"
        token_file.write_text('{"token": "fake"}')

        with (
            patch("app.services.google_calendar_service.get_token_path_for_user",
                  return_value=str(token_file)),
            patch("app.services.google_calendar_service.Credentials.from_authorized_user_file",
                  return_value=self._mock_creds()),
            patch("app.services.google_calendar_service.build") as mock_build,
        ):
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            mock_service.events.return_value.insert.return_value.execute.return_value = {"id": "x"}

            from app.services.google_calendar_service import create_google_calendar_event
            create_google_calendar_event(
                user_id=2,
                summary="Meeting",
                start_time=self.START,
                end_time=self.END,
                attendees=["a@x.com", "b@x.com"],
            )

        body = mock_service.events.return_value.insert.call_args.kwargs["body"]
        assert body["attendees"] == [{"email": "a@x.com"}, {"email": "b@x.com"}]

    def test_raises_when_no_token_file(self, tmp_path):
        """If the user has no OAuth token on disk, FileNotFoundError is raised."""
        with patch("app.services.google_calendar_service.get_token_path_for_user",
                   return_value=str(tmp_path / "nonexistent.json")):
            from app.services.google_calendar_service import create_google_calendar_event
            with pytest.raises(FileNotFoundError, match="No OAuth token"):
                create_google_calendar_event(
                    user_id=99,
                    summary="X",
                    start_time=self.START,
                    end_time=self.END,
                )

    def test_refreshes_expired_credentials(self, tmp_path):
        """Expired credentials should be refreshed before calling the API."""
        token_file = tmp_path / "gmail_user_3.json"
        token_file.write_text('{"token": "old"}')

        expired_creds = self._mock_creds(valid=True, expired=True)

        with (
            patch("app.services.google_calendar_service.get_token_path_for_user",
                  return_value=str(token_file)),
            patch("app.services.google_calendar_service.Credentials.from_authorized_user_file",
                  return_value=expired_creds),
            patch("app.services.google_calendar_service.Request"),
            patch("app.services.google_calendar_service.build") as mock_build,
        ):
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            mock_service.events.return_value.insert.return_value.execute.return_value = {"id": "y"}

            from app.services.google_calendar_service import create_google_calendar_event
            create_google_calendar_event(
                user_id=3, summary="X", start_time=self.START, end_time=self.END
            )

        # refresh() must have been called on the credentials object
        expired_creds.refresh.assert_called_once()


# ─────────────────────────────────────────────
# Apple CalDAV Service
# ─────────────────────────────────────────────

class TestAppleCalendarService:
    """Tests for app/services/apple_calendar_service.py"""

    START = datetime(2024, 10, 20, 15, 0, tzinfo=UTC)
    END   = datetime(2024, 10, 20, 16, 0, tzinfo=UTC)

    def _encrypted_password(self):
        from app.core.encryption import encrypt
        return encrypt("xxxx-xxxx-xxxx-xxxx")

    def test_creates_event_and_returns_uid(self):
        """
        Happy path: CalDAV client connects, finds a calendar, saves the event,
        and returns a UUID string as the event UID.
        """
        mock_calendar = MagicMock()
        mock_principal = MagicMock()
        mock_principal.calendars.return_value = [mock_calendar]

        with patch("app.services.apple_calendar_service.caldav.DAVClient") as mock_client_cls:
            mock_client_cls.return_value.principal.return_value = mock_principal

            from app.services.apple_calendar_service import create_apple_calendar_event
            uid = create_apple_calendar_event(
                apple_user="dan@icloud.com",
                encrypted_password=self._encrypted_password(),
                summary="Réunion démo",
                start_time=self.START,
                end_time=self.END,
            )

        # A UUID was returned
        import uuid
        uuid.UUID(uid)  # raises ValueError if not a valid UUID

        # The CalDAV client was instantiated with the correct URL and credentials
        mock_client_cls.assert_called_once_with(
            url="https://caldav.icloud.com",
            username="dan@icloud.com",
            password="xxxx-xxxx-xxxx-xxxx",
        )

        # save_event was called on the calendar
        mock_calendar.save_event.assert_called_once()

    def test_ics_content_contains_summary_and_times(self):
        """The generated .ics event must contain the correct SUMMARY, DTSTART, DTEND."""
        mock_calendar = MagicMock()
        captured_ics = {}

        def capture_ics(ics_str):
            captured_ics["ics"] = ics_str

        mock_calendar.save_event.side_effect = capture_ics
        mock_principal = MagicMock()
        mock_principal.calendars.return_value = [mock_calendar]

        with patch("app.services.apple_calendar_service.caldav.DAVClient") as mock_client_cls:
            mock_client_cls.return_value.principal.return_value = mock_principal

            from app.services.apple_calendar_service import create_apple_calendar_event
            create_apple_calendar_event(
                apple_user="dan@icloud.com",
                encrypted_password=self._encrypted_password(),
                summary="Démo produit",
                start_time=self.START,
                end_time=self.END,
            )

        ics = captured_ics["ics"]
        assert "SUMMARY:Démo produit" in ics
        assert "DTSTART:20241020T150000Z" in ics
        assert "DTEND:20241020T160000Z" in ics
        assert "BEGIN:VCALENDAR" in ics
        assert "BEGIN:VEVENT" in ics
        assert "END:VEVENT" in ics

    def test_raises_when_no_calendars_found(self):
        """If the iCloud account has no calendars, RuntimeError is raised."""
        mock_principal = MagicMock()
        mock_principal.calendars.return_value = []  # empty list

        with patch("app.services.apple_calendar_service.caldav.DAVClient") as mock_client_cls:
            mock_client_cls.return_value.principal.return_value = mock_principal

            from app.services.apple_calendar_service import create_apple_calendar_event
            with pytest.raises(RuntimeError, match="No iCloud calendars"):
                create_apple_calendar_event(
                    apple_user="dan@icloud.com",
                    encrypted_password=self._encrypted_password(),
                    summary="X",
                    start_time=self.START,
                    end_time=self.END,
                )

    def test_decrypts_password_before_connecting(self):
        """The service must decrypt the stored password before passing it to CalDAV."""
        from app.core.encryption import encrypt

        plain = "secret-app-password"
        encrypted = encrypt(plain)

        mock_calendar = MagicMock()
        mock_principal = MagicMock()
        mock_principal.calendars.return_value = [mock_calendar]

        with patch("app.services.apple_calendar_service.caldav.DAVClient") as mock_client_cls:
            mock_client_cls.return_value.principal.return_value = mock_principal

            from app.services.apple_calendar_service import create_apple_calendar_event
            create_apple_calendar_event(
                apple_user="user@icloud.com",
                encrypted_password=encrypted,
                summary="X",
                start_time=self.START,
                end_time=self.END,
            )

        # The plain-text password must have been passed to DAVClient, not the encrypted blob
        _, kwargs = mock_client_cls.call_args
        assert kwargs["password"] == plain
        assert kwargs["password"] != encrypted
