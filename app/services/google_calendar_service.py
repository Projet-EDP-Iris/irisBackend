import json
import os
from datetime import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.services.gmail_service import (
    SCOPES,
    _load_gmail_token_from_db,
    _save_gmail_token_to_db,
    get_token_path_for_user,
)


def _load_creds_for_user(user_id: int) -> Credentials:
    """Load and auto-refresh the user's stored Google OAuth credentials.
    Reads from DB (production) and falls back to legacy token file (local dev)."""
    record = _load_gmail_token_from_db(user_id)
    if record is not None:
        token_str, gmail_email = record
        creds = Credentials.from_authorized_user_info(json.loads(token_str), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _save_gmail_token_to_db(user_id, creds.to_json(), gmail_email)
        if not creds.valid:
            raise RuntimeError(
                f"Google credentials for user {user_id} are invalid and could not be refreshed."
            )
        return creds

    # Local dev fallback: token stored as a file
    token_path = get_token_path_for_user(user_id)
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_path, "w") as f:
                f.write(creds.to_json())
        if not creds.valid:
            raise RuntimeError(
                f"Google credentials for user {user_id} are invalid and could not be refreshed."
            )
        return creds

    raise FileNotFoundError(
        f"No OAuth token for user {user_id}. "
        "The user must complete the Gmail OAuth flow first."
    )


def create_google_calendar_event(
    user_id: int,
    summary: str,
    start_time: datetime,
    end_time: datetime,
    attendees: list[str] | None = None,
    description: str | None = None,
    timezone: str = "UTC",
) -> str:
    """
    Creates an event on the user's primary Google Calendar.

    Reuses the existing Gmail OAuth token (same credentials file, extended
    with the calendar scope). Returns the Google-assigned event ID, which
    should be stored in Email.calendar_event_id for later updates/deletes.

    sendUpdates="all" automatically emails calendar invites to all attendees.
    """
    creds = _load_creds_for_user(user_id)

    # Same build() pattern as gmail_service.py — just a different API name
    service = build("calendar", "v3", credentials=creds)

    event_body = {
        "summary": summary,
        "description": description or "",
        "start": {
            "dateTime": start_time.isoformat(),
            "timeZone": timezone,
        },
        "end": {
            "dateTime": end_time.isoformat(),
            "timeZone": timezone,
        },
        "attendees": [{"email": addr} for addr in (attendees or [])],
        "guestsCanSeeOtherGuests": True,
    }

    created_event = (
        service.events()
        .insert(
            calendarId="primary",  # user's default calendar
            body=event_body,
            sendUpdates="all",     # sends invite emails to attendees automatically
        )
        .execute()
    )

    return created_event["id"]
