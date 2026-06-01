from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limiter import forgot_password_limiter
from app.core.security import hash_password
from app.db.database import get_db
from app.models.auth_token import TokenType
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    MessageResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
)
from app.services.auth_token_service import consume_token, create_token
from app.services.email_service import send_password_reset_email, send_verification_email

router = APIRouter(prefix="/auth", tags=["auth"])

_RESET_LINK_SENT = "If that email is registered, a password reset link has been sent."
_VERIFY_LINK_SENT = "If that email is registered and unverified, a verification link has been sent."
_INVALID_TOKEN = "Invalid or expired token."


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    body: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
) -> MessageResponse:
    client_ip = request.client.host if request.client else "unknown"  # type: ignore[union-attr]
    if not forgot_password_limiter.is_allowed(client_ip):
        retry_after = forgot_password_limiter.seconds_until_reset(client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    user = db.query(User).filter(User.email == body.email).first()
    if user:
        token = create_token(
            db=db,
            user_id=user.id,
            token_type=TokenType.password_reset,
            expires_minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
        )
        db.commit()
        background_tasks.add_task(send_password_reset_email, user.email, token)

    return MessageResponse(message=_RESET_LINK_SENT)


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    record = consume_token(
        db=db,
        raw_token=body.token,
        token_type=TokenType.password_reset,
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_INVALID_TOKEN)

    user = db.query(User).filter(User.id == record.user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_INVALID_TOKEN)

    user.password_hash = hash_password(body.new_password)
    user.require_password_reset = False
    record.used = True
    db.commit()

    return MessageResponse(message="Password updated successfully.")


@router.post("/verify-email", response_model=MessageResponse)
def verify_email(
    body: VerifyEmailRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    record = consume_token(
        db=db,
        raw_token=body.token,
        token_type=TokenType.email_verification,
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_INVALID_TOKEN)

    user = db.query(User).filter(User.id == record.user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_INVALID_TOKEN)

    user.is_email_verified = True
    record.used = True
    db.commit()

    return MessageResponse(message="Email verified successfully.")


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(
    body: ResendVerificationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> MessageResponse:
    user = db.query(User).filter(User.email == body.email).first()
    if user and not user.is_email_verified:
        token = create_token(
            db=db,
            user_id=user.id,
            token_type=TokenType.email_verification,
            expires_minutes=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS * 60,
        )
        db.commit()
        background_tasks.add_task(send_verification_email, user.email, token)

    return MessageResponse(message=_VERIFY_LINK_SENT)
