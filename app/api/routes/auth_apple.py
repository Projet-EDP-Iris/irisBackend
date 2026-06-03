from fastapi import APIRouter, Depends

from app.core.auth import get_current_active_user
from app.models.user import User

router = APIRouter(prefix="/auth/apple", tags=["auth"])


@router.get("/status")
def apple_calendar_status(
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """
    Return the Apple Calendar connection status for the authenticated user.

    Response:
        connected (bool) — True if Apple ID + App Password are stored
        email (str | None) — The connected Apple ID email address
    """
    providers = current_user.calendar_providers or []
    connected = (
        "apple" in providers
        and bool(current_user.apple_caldav_user)
        and bool(current_user.apple_caldav_password)
    )
    return {
        "connected": connected,
        "email": current_user.apple_caldav_user if connected else None,
    }
