import logging

import resend

from app.core.config import settings

logger = logging.getLogger(__name__)


def _send_resend(to_email: str, subject: str, html_body: str) -> None:
    if not settings.RESEND_API_KEY:
        raise ValueError("RESEND_API_KEY is not configured.")
    resend.api_key = settings.RESEND_API_KEY
    response = resend.Emails.send({
        "from": settings.RESEND_FROM_EMAIL,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    })
    logger.info("Email sent via Resend id=%s to=%s", response.get("id"), to_email)


async def send_password_reset_email(to_email: str, token: str) -> None:
    if not settings.EMAIL_ENABLED:
        logger.info("EMAIL_ENABLED=False — skipping password reset email to %s", to_email)
        return
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    html = (
        "<p>You requested a password reset for your Iris account.</p>"
        f'<p><a href="{reset_url}">Reset your password</a>'
        f" (expires in {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes)</p>"
        "<p>If you did not request this, you can safely ignore this email.</p>"
    )
    try:
        _send_resend(to_email, "Reset your Iris password", html)
    except Exception:
        logger.exception("Failed to send password reset email to %s", to_email)


async def send_verification_email(to_email: str, token: str) -> None:
    if not settings.EMAIL_ENABLED:
        logger.info("EMAIL_ENABLED=False — skipping verification email to %s", to_email)
        return
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    html = (
        "<p>Welcome to Iris! Please verify your email address to activate your account.</p>"
        f'<p><a href="{verify_url}">Verify my email</a>'
        f" (expires in {settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS} hours)</p>"
        "<p>If you did not create an Iris account, you can safely ignore this email.</p>"
    )
    try:
        _send_resend(to_email, "Verify your Iris email address", html)
    except Exception:
        logger.exception("Failed to send verification email to %s", to_email)
