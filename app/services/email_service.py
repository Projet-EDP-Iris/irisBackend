import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


def _send_smtp(to_email: str, subject: str, html_body: str) -> None:
    """Blocking SMTP send — called via asyncio.to_thread to avoid blocking the event loop."""
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        if settings.SMTP_USE_TLS:
            server.starttls()
        if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM_EMAIL
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))
        server.sendmail(settings.SMTP_FROM_EMAIL, to_email, msg.as_string())


async def send_password_reset_email(to_email: str, token: str) -> None:
    if not settings.EMAIL_ENABLED:
        logger.info("EMAIL_ENABLED=False — skipping password reset email to %s", to_email)
        return
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    html = (
        "<p>You requested a password reset for your Iris account.</p>"
        f'<p><a href="{reset_url}">Reset your password</a> (expires in {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes)</p>'
        "<p>If you did not request this, you can safely ignore this email.</p>"
    )
    try:
        await asyncio.to_thread(_send_smtp, to_email, "Reset your Iris password", html)
    except Exception:
        logger.exception("Failed to send password reset email to %s", to_email)


async def send_verification_email(to_email: str, token: str) -> None:
    if not settings.EMAIL_ENABLED:
        logger.info("EMAIL_ENABLED=False — skipping verification email to %s", to_email)
        return
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    html = (
        "<p>Welcome to Iris! Please verify your email address to activate your account.</p>"
        f'<p><a href="{verify_url}">Verify my email</a> (expires in {settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS} hours)</p>'
        "<p>If you did not create an Iris account, you can safely ignore this email.</p>"
    )
    try:
        await asyncio.to_thread(_send_smtp, to_email, "Verify your Iris email address", html)
    except Exception:
        logger.exception("Failed to send verification email to %s", to_email)
