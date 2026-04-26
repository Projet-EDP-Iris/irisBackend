"""
Microsoft OAuth 2.0 flow for Outlook emails + Calendar + Tasks integration.

Endpoints:
  GET /api/v1/auth/microsoft          — initiate login (returns login URL)
  GET /api/v1/auth/microsoft/callback — handle redirect back, exchange code for token
  GET /api/v1/auth/microsoft/status   — check if the current user has Outlook connected

How it works:
  1. Frontend calls GET /api/v1/auth/microsoft
     → Backend builds the Microsoft login URL and returns {"auth_url": "..."}
  2. Frontend redirects the user to that URL
  3. User logs in on Microsoft's page
  4. Microsoft redirects to /callback?code=...&state=...
  5. Backend exchanges the code for an access + refresh token, stores it in tokens/
  6. Backend redirects the user to the frontend with ?outlook=success or ?outlook=error
  7. User can now access Outlook emails via GET /api/v1/emails

The `state` parameter is an HMAC-signed string containing the user_id, which
prevents CSRF attacks.
"""
import os
import logging
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.core.auth import get_current_active_user
from app.models.user import User
from app.services.microsoft_oauth_service import exchange_code_for_token, get_auth_url, _token_path
from app.services.outlook_email_service import get_outlook_connection_status

router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)

_FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")


def _build_frontend_redirect(outlook_status: str, reason: str | None = None) -> str:
    """Build the redirect URL back to the frontend after Microsoft OAuth."""
    parsed = urlsplit(_FRONTEND_URL)
    path = parsed.path or "/"
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["outlook"] = outlook_status
    if reason and os.getenv("ENVIRONMENT") != "production":
        query["outlook_reason"] = reason
    return urlunsplit(parsed._replace(path=path, query=urlencode(query), fragment="/emails"))


@router.get(
    "/auth/microsoft",
    summary="Initiate Microsoft OAuth — returns the login URL",
)
def initiate_microsoft_oauth(
    current_user: User = Depends(get_current_active_user),
):
    """
    Returns the Microsoft login URL for the authenticated user.
    The frontend should redirect the user to this URL.
    After the user logs in, Microsoft redirects to /auth/microsoft/callback.
    """
    try:
        url = get_auth_url(current_user.id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"auth_url": url}


@router.get(
    "/auth/microsoft/status",
    summary="Check if Outlook is connected for the current user",
)
def microsoft_connection_status(
    current_user: User = Depends(get_current_active_user),
):
    """
    Returns whether the authenticated user has a valid Outlook OAuth token,
    and the associated Microsoft email address (if reachable).
    """
    status = get_outlook_connection_status(current_user.id)
    return {
        "connected": status["connected"],
        "outlook_email": status.get("email"),
        "enabled": status["connected"],  # symmetry with Gmail status endpoint
    }


@router.get(
    "/auth/microsoft/callback",
    summary="Microsoft OAuth callback — exchanges code for token and redirects to frontend",
)
def microsoft_oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
):
    """
    Microsoft redirects here after the user logs in.
    Exchanges the one-time `code` for access + refresh tokens, stores them,
    and redirects the browser back to the frontend with ?outlook=success or ?outlook=error.
    """
    if error or not code or not state:
        reason = error_description or error or "missing_code_or_state"
        logger.warning("Microsoft OAuth callback error: %s — %s", error, error_description)
        return RedirectResponse(url=_build_frontend_redirect("error", reason))

    try:
        user_id = exchange_code_for_token(state=state, code=code)
        logger.info("Microsoft Outlook connected for user_id=%d", user_id)
    except ValueError as exc:
        return RedirectResponse(url=_build_frontend_redirect("error", str(exc)))
    except Exception as exc:
        logger.error("Microsoft OAuth token exchange failed: %s", exc)
        return RedirectResponse(url=_build_frontend_redirect("error", "token_exchange_failed"))

    return RedirectResponse(url=_build_frontend_redirect("success"))
