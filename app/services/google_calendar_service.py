import os
from datetime import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.services.gmail_service import SCOPES, get_token_path_for_user


def _load_creds_for_user(user_id: int) -> Credentials:
    """Load and auto-refresh the user's stored Google OAuth credentials."""
    token_path = get_token_path_for_user(user_id)
    if not os.path.exists(token_path):
        raise FileNotFoundError(
            f"No OAuth token for user {user_id}. "
            "The user must complete the Gmail OAuth flow first."
        )

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
