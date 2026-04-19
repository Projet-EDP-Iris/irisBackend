from datetime import datetime

import httpx

from app.services.microsoft_oauth_service import get_valid_token

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def create_outlook_calendar_event(
    user_id: int,
    summary: str,
    start_time: datetime,
    end_time: datetime,
    attendees: list[str] | None = None,
    description: str | None = None,
    timezone: str = "UTC",
) -> str:
    """
    Creates an event on the user's primary Outlook/Microsoft 365 calendar
    via the Microsoft Graph API.

    Uses the stored OAuth token from microsoft_oauth_service.
    sendInvitationsOrCancellations="sendToAllAndSaveCopy" automatically
    emails calendar invites to all attendees.

    Returns the Graph API event ID (store in Email.calendar_event_ids["outlook"]).
    """
    access_token = get_valid_token(user_id)

    # Microsoft Graph uses ISO 8601 without timezone suffix — timezone is a separate field
    def _fmt(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%dT%H:%M:%S")

    event_body = {
        "subject": summary,
        "body": {
            "contentType": "Text",
            "content": description or "",
        },
        "start": {
            "dateTime": _fmt(start_time),
            "timeZone": timezone,
        },
        "end": {
            "dateTime": _fmt(end_time),
            "timeZone": timezone,
        },
        "attendees": [
            {"emailAddress": {"address": addr}, "type": "required"}
            for addr in (attendees or [])
        ],
    }

    resp = httpx.post(
        f"{_GRAPH_BASE}/me/events",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=event_body,
        params={"$sendInvitationsOrCancellations": "sendToAllAndSaveCopy"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["id"]
