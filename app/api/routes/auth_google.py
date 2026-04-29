"""
Google OAuth 2.0 endpoints for Gmail + Calendar connection.

  GET /api/v1/auth/google          — returns the Google consent URL (requires Bearer token)
  GET /api/v1/auth/google/callback — exchanges the code, saves token, redirects to frontend
"""
import logging
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.core.auth import get_current_active_user
from app.models.user import User
from app.services.google_oauth_service import (
    GoogleOAuthExchangeError,
    exchange_code_for_token,
    get_auth_url,
    get_google_oauth_runtime_diagnostics,
)

router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)

_FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")


def _build_frontend_redirect(gmail_status: str, reason: str | None = None) -> str:
    parsed = urlsplit(_FRONTEND_URL)
    path = parsed.path or ("/" if parsed.scheme in {"http", "https"} else parsed.path)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["gmail"] = gmail_status
    if reason and os.getenv("ENVIRONMENT") != "production":
        query["gmail_reason"] = reason
    return urlunsplit(parsed._replace(path=path, query=urlencode(query), fragment="/emails"))


@router.get(
    "/auth/google/status",
    summary="Check if Gmail is connected for the current user",
)
def google_connection_status(
    current_user: User = Depends(get_current_active_user),
):
    """Returns whether the authenticated user has saved a Gmail OAuth token."""
    if not current_user.gmail_oauth_token:
        return {"connected": False, "gmail_email": None}
    return {"connected": True, "gmail_email": current_user.gmail_email}


@router.get(
    "/auth/google",
    summary="Initiate Google OAuth — returns the consent URL",
)
def initiate_google_oauth(
    current_user: User = Depends(get_current_active_user),
):
    """
    Returns the Google OAuth consent URL for the authenticated user.
    The frontend should redirect the browser to this URL.
    After the user grants access, Google redirects to /auth/google/callback.
    """
    try:
        url = get_auth_url(current_user.id)
    except GoogleOAuthExchangeError as exc:
        logger.exception(
            "Failed to generate Google OAuth URL for user_id=%s reason=%s diagnostics=%s",
            current_user.id,
            exc.reason,
            get_google_oauth_runtime_diagnostics(),
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "Unexpected Google OAuth URL generation failure for user_id=%s diagnostics=%s",
            current_user.id,
            get_google_oauth_runtime_diagnostics(),
        )
        raise HTTPException(status_code=503, detail="Google OAuth URL generation failed.") from exc
    return {"auth_url": url}


@router.get(
    "/auth/google/callback",
    summary="Google OAuth callback — exchanges code for token",
    include_in_schema=True,
)
def google_oauth_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="HMAC-signed state containing user_id"),
    error: str | None = Query(default=None),
):
    """
    Google redirects here after the user grants (or denies) access.
    Exchanges the one-time code for tokens, persists them, and redirects to the frontend.
    """
    if error:
        logger.warning("Google OAuth callback returned provider error=%s", error)
        return RedirectResponse(url=_build_frontend_redirect("error", reason="provider_error"))

    try:
        exchange_code_for_token(state=state, code=code)
    except GoogleOAuthExchangeError as exc:
        logger.exception(
            "Google OAuth callback failed reason=%s diagnostics=%s",
            exc.reason,
            get_google_oauth_runtime_diagnostics(),
        )
        return RedirectResponse(url=_build_frontend_redirect("error", reason=exc.reason))
    except Exception:
        logger.exception(
            "Unexpected Google OAuth callback failure diagnostics=%s",
            get_google_oauth_runtime_diagnostics(),
        )
        return RedirectResponse(url=_build_frontend_redirect("error", reason="unexpected_callback_error"))

    return RedirectResponse(url=_build_frontend_redirect("connected"))
