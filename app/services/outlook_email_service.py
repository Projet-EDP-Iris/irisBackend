"""
Outlook email reading via Microsoft Graph API.

This module lets Iris fetch emails from a user's Outlook/Microsoft 365 inbox,
following the same pattern as gmail_service.py but using the Microsoft Graph REST API.

Pre-requisite: the user must have completed the Microsoft OAuth flow
(GET /api/v1/auth/microsoft) which now requests the Mail.Read scope.

Usage:
    from app.services.outlook_email_service import fetch_outlook_emails, is_outlook_connected

    if is_outlook_connected(user_id):
        emails = fetch_outlook_emails(user_id, n=10)
"""
import os
import logging

import httpx

from app.schemas.email import EmailItem
from app.schemas.detection import EmailInput as DetectionEmailInput
from app.services.microsoft_oauth_service import TOKENS_DIR, _token_path, get_valid_token

logger = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# Fields we request from the Graph API (minimise payload)
_SELECT = "id,subject,body,from,receivedDateTime,isRead,isDraft"


def is_outlook_connected(user_id: int) -> bool:
    """Return True if the user has a stored Outlook OAuth token."""
    return os.path.exists(_token_path(user_id))


def _parse_email_item(msg: dict) -> EmailItem:
    """Convert a Microsoft Graph message object into an EmailItem."""
    subject = msg.get("subject") or "(Sans objet)"

    # Body — we request plain text via the Prefer header; fall back to HTML content
    body_obj = msg.get("body") or {}
    body = body_obj.get("content") or ""

    # Sender
    from_obj = (msg.get("from") or {}).get("emailAddress", {})
    sender_name = from_obj.get("name")
    sender_email = from_obj.get("address")
    if sender_name and sender_email:
        sender = f"{sender_name} <{sender_email}>"
    else:
        sender = sender_email or sender_name or None

    # Date — Graph returns ISO 8601 with trailing 'Z'
    date = msg.get("receivedDateTime")

    # Use the Graph message id as our message_id (stable per message)
    message_id = msg.get("id")

    # Import here to avoid circular import (detection → extractor, not outlook → detection)
    from app.services.detection import categorize_email  # noqa: PLC0415
    category = categorize_email(DetectionEmailInput(subject=subject, body=body))

    return EmailItem(
        subject=subject,
        body=body,
        message_id=message_id,
        sender=sender,
        date=date,
        category=category,
        provider="outlook",
    )


def fetch_outlook_emails(user_id: int, n: int | None = None) -> list[EmailItem]:
    """
    Fetch Outlook emails for a user, paginating through all results.

    Args:
        n: Maximum number of emails to return. None (default) fetches all.

    Raises:
        FileNotFoundError — if the user has not connected Outlook yet.
        httpx.HTTPStatusError — if the Graph API returns a non-2xx status.
    """
    access_token = get_valid_token(user_id)  # auto-refreshes if expired

    next_url: str | None = f"{_GRAPH_BASE}/me/messages"
    params: dict | None = {
        "$select": _SELECT,
        "$top": "1000",  # Graph API max per page
        "$orderby": "receivedDateTime desc",
        "$filter": "isDraft eq false",
    }

    all_messages: list[dict] = []
    while next_url:
        resp = httpx.get(
            next_url,
            params=params,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Prefer": 'outlook.body-content-type="text"',
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        all_messages.extend(data.get("value", []))

        # nextLink already contains all query params — don't pass params again
        next_url = data.get("@odata.nextLink")
        params = None

        if n is not None and len(all_messages) >= n:
            all_messages = all_messages[:n]
            break

    logger.info("Fetched %d Outlook messages for user_id=%d", len(all_messages), user_id)
    return [_parse_email_item(m) for m in all_messages]


def fetch_outlook_email_page(
    user_id: int, skip: int = 0, limit: int = 50
) -> tuple[list[EmailItem], bool]:
    """
    Fetch one page of Outlook emails using $skip offset.
    Returns (emails, has_more).
    """
    access_token = get_valid_token(user_id)
    resp = httpx.get(
        f"{_GRAPH_BASE}/me/messages",
        params={
            "$select": _SELECT,
            "$top": str(limit),
            "$skip": str(skip),
            "$orderby": "receivedDateTime desc",
            "$filter": "isDraft eq false",
        },
        headers={
            "Authorization": f"Bearer {access_token}",
            "Prefer": 'outlook.body-content-type="text"',
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    messages = data.get("value", [])
    has_more = "@odata.nextLink" in data or len(messages) == limit
    return [_parse_email_item(m) for m in messages], has_more


def get_outlook_connection_status(user_id: int) -> dict:
    """
    Return connection status for the given user.

    Returns a dict with:
        connected (bool)   — whether a valid token file exists
        email (str | None) — the Outlook email address (fetched from /me if connected)
    """
    if not is_outlook_connected(user_id):
        return {"connected": False, "email": None}

    try:
        access_token = get_valid_token(user_id)
        resp = httpx.get(
            f"{_GRAPH_BASE}/me",
            params={"$select": "mail,userPrincipalName"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        resp.raise_for_status()
        profile = resp.json()
        email = profile.get("mail") or profile.get("userPrincipalName")
        return {"connected": True, "email": email}
    except Exception as exc:
        logger.warning("Could not fetch Outlook profile for user %d: %s", user_id, exc)
        return {"connected": True, "email": None}
