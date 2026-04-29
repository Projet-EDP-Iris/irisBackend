"""
Microsoft OAuth 2.0 token management — file-based storage, same pattern as gmail_service.py.

Flow:
  1. Frontend redirects user to get_auth_url(user_id)
  2. Microsoft redirects back to /api/v1/auth/microsoft/callback?code=...&state=...
  3. exchange_code_for_token() stores the token
  4. get_valid_token() is used by Outlook services to get a fresh access token

Scopes granted:
  Mail.Read            — read inbox emails (Outlook email fetching)
  Calendars.ReadWrite  — create/update calendar events
  Tasks.ReadWrite      — create tasks in Microsoft To Do
  offline_access       — enables refresh tokens
  User.Read            — read basic profile info
"""
import hashlib
import hmac
import json
import os
import time

import httpx

from app.core.config import settings
from app.core.encryption import decrypt, encrypt

_SCOPES = "Mail.Read Calendars.ReadWrite Tasks.ReadWrite offline_access User.Read"
_AUTHORITY = "https://login.microsoftonline.com/{tenant}"
_GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _token_path(user_id: int) -> str:
    """Legacy helper — kept so existing imports don't break."""
    return os.path.join("tokens", f"outlook_user_{user_id}.json")


def _save_outlook_token_to_db(user_id: int, token_data: dict) -> None:
    from app.db.database import SessionLocal
    from app.models.user import User as UserModel
    db = SessionLocal()
    try:
        user = db.get(UserModel, user_id)
        if user:
            user.outlook_oauth_token = encrypt(json.dumps(token_data))
            user.outlook_email = token_data.get("email") or user.outlook_email
            db.commit()
    finally:
        db.close()


def _load_outlook_token_from_db(user_id: int) -> dict | None:
    from app.db.database import SessionLocal
    from app.models.user import User as UserModel
    db = SessionLocal()
    try:
        user = db.get(UserModel, user_id)
        if user and user.outlook_oauth_token:
            return json.loads(decrypt(user.outlook_oauth_token))
        return None
    finally:
        db.close()


def _sign_state(user_id: int) -> str:
    """Create an HMAC-signed state parameter that encodes the user_id."""
    payload = str(user_id)
    sig = hmac.new(settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _verify_state(state: str) -> int:
    """Verify the HMAC signature and return the user_id, or raise ValueError."""
    parts = state.split(".", 1)
    if len(parts) != 2:
        raise ValueError("Invalid state parameter")
    payload, sig = parts
    expected = hmac.new(settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise ValueError("State signature mismatch — possible CSRF")
    return int(payload)


def get_auth_url(user_id: int) -> str:
    """Build the Microsoft login URL to redirect the user to."""
    if not settings.MICROSOFT_CLIENT_ID:
        raise RuntimeError("MICROSOFT_CLIENT_ID is not configured in .env")
    authority = _AUTHORITY.format(tenant=settings.MICROSOFT_TENANT_ID)
    state = _sign_state(user_id)
    params = {
        "client_id": settings.MICROSOFT_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
        "scope": _SCOPES,
        "state": state,
        "response_mode": "query",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{authority}/oauth2/v2.0/authorize?{query}"


def exchange_code_for_token(state: str, code: str) -> int:
    """
    Exchange an authorization code for tokens and persist them.
    Returns the user_id extracted from the state parameter.
    """
    user_id = _verify_state(state)
    authority = _AUTHORITY.format(tenant=settings.MICROSOFT_TENANT_ID)
    resp = httpx.post(
        f"{authority}/oauth2/v2.0/token",
        data={
            "client_id": settings.MICROSOFT_CLIENT_ID,
            "client_secret": settings.MICROSOFT_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
            "scope": _SCOPES,
        },
        timeout=15,
    )
    resp.raise_for_status()
    token_data = resp.json()
    token_data["stored_at"] = time.time()
    _save_outlook_token_to_db(user_id, token_data)
    return user_id


def _refresh_token(user_id: int, token_data: dict) -> dict:
    """Use the refresh_token to get a new access_token and persist it."""
    authority = _AUTHORITY.format(tenant=settings.MICROSOFT_TENANT_ID)
    resp = httpx.post(
        f"{authority}/oauth2/v2.0/token",
        data={
            "client_id": settings.MICROSOFT_CLIENT_ID,
            "client_secret": settings.MICROSOFT_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": token_data["refresh_token"],
            "scope": _SCOPES,
        },
        timeout=15,
    )
    resp.raise_for_status()
    new_data = resp.json()
    new_data["stored_at"] = time.time()
    # Keep refresh_token if the new response doesn't include one (MS sometimes omits it)
    if "refresh_token" not in new_data:
        new_data["refresh_token"] = token_data["refresh_token"]
    _save_outlook_token_to_db(user_id, new_data)
    return new_data


def get_valid_token(user_id: int) -> str:
    """
    Load the stored token for a user from DB, refresh if expired, and return a valid access_token.
    Raises FileNotFoundError if the user has not connected Outlook yet.
    """
    token_data = _load_outlook_token_from_db(user_id)
    if token_data is None:
        raise FileNotFoundError(
            f"No Outlook token for user {user_id}. "
            "User must complete the Microsoft OAuth flow via GET /api/v1/auth/microsoft"
        )

    stored_at = token_data.get("stored_at", 0)
    expires_in = token_data.get("expires_in", 3600)
    # Refresh 60 seconds early to avoid race conditions
    if time.time() > stored_at + expires_in - 60:
        token_data = _refresh_token(user_id, token_data)

    return token_data["access_token"]
