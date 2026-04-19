"""
Microsoft OAuth 2.0 flow for Outlook Calendar + Tasks integration.

Two endpoints:
  GET /api/v1/auth/microsoft          — initiate login (redirect user to Microsoft)
  GET /api/v1/auth/microsoft/callback — handle the redirect back, exchange code for token

How it works:
  1. Frontend calls GET /api/v1/auth/microsoft?user_id=42
     → Backend builds the Microsoft login URL and returns it (or redirects directly)
  2. User logs in on Microsoft's page
  3. Microsoft redirects to /callback?code=...&state=...
  4. Backend exchanges the code for an access + refresh token, stores it in tokens/
  5. User is now connected — confirm endpoint can create Outlook events

The `state` parameter is an HMAC-signed string containing the user_id, which
prevents CSRF attacks (a third party can't inject a foreign token for a victim user).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.core.auth import get_current_active_user
from app.models.user import User
from app.services.microsoft_oauth_service import exchange_code_for_token, get_auth_url

router = APIRouter(tags=["auth"])


@router.get(
    "/auth/microsoft",
    summary="Initiate Microsoft OAuth — returns the login URL",
)
def initiate_microsoft_oauth(
    current_user: User = Depends(get_current_active_user),
):
    """
    Returns the Microsoft login URL for the authenticated user.
    The frontend should open this URL in a browser/webview.
    After the user logs in, Microsoft redirects to /auth/microsoft/callback.
    """
    try:
        url = get_auth_url(current_user.id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"auth_url": url}


@router.get(
    "/auth/microsoft/callback",
    summary="Microsoft OAuth callback — exchanges code for token",
)
def microsoft_oauth_callback(
    code: str = Query(..., description="Authorization code from Microsoft"),
    state: str = Query(..., description="HMAC-signed state containing user_id"),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
):
    """
    Microsoft redirects here after the user logs in.
    Exchanges the one-time `code` for access + refresh tokens and stores them.

    On success, returns the user_id that was connected.
    On error (user denied, misconfigured app), returns the error description.
    """
    if error:
        raise HTTPException(
            status_code=400,
            detail=f"Microsoft OAuth error: {error} — {error_description}",
        )
    try:
        user_id = exchange_code_for_token(state=state, code=code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to exchange Microsoft authorization code: {exc}",
        ) from exc

    return {
        "status": "connected",
        "user_id": user_id,
        "message": (
            "Outlook connected. You can now add 'outlook' as a calendar provider "
            "via PATCH /api/v1/user/users/me/calendar-setup."
        ),
    }
