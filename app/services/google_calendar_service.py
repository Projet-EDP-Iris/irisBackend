import json
from datetime import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.services.gmail_service import (
    SCOPES,
    _load_gmail_token_from_db,
    _save_gmail_token_to_db,
)


def _load_creds_for_user(user_id: int) -> Credentials:
    """Load and auto-refresh the user's stored Google OAuth credentials from DB."""
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


def list_google_calendar_events(
    user_id: int,
    start: datetime,
    end: datetime,
) -> list[dict]:
    """Return events on the user's primary Google Calendar that overlap [start, end).

    Each entry: {"title": str, "start": str, "end": str}
    Returns an empty list on any error so callers can treat failures as no-conflict.
    """
    try:
        creds = _load_creds_for_user(user_id)
        service = build("calendar", "v3", credentials=creds)
        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=start.isoformat() + ("Z" if start.tzinfo is None else ""),
                timeMax=end.isoformat() + ("Z" if end.tzinfo is None else ""),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = []
        for item in result.get("items", []):
            start_str = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date", "")
            end_str = item.get("end", {}).get("dateTime") or item.get("end", {}).get("date", "")
            events.append({
                "title": item.get("summary", "Événement"),
                "start": start_str,
                "end": end_str,
            })
        return events
    except Exception:
        return []
