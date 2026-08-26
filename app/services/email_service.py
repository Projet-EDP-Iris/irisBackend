import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


def _send_smtp(to_email: str, subject: str, html_body: str) -> None:
    """Send an email via SMTP (smtplib stdlib — zero external dependency)."""
    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        raise ValueError(
            "SMTP_USERNAME and SMTP_PASSWORD must be set in .env to send emails."
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM_EMAIL
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        if settings.SMTP_USE_TLS:
            server.starttls(context=context)
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_FROM_EMAIL, to_email, msg.as_string())

    logger.info("Email sent via SMTP to=%s subject=%r", to_email, subject)


def send_password_reset_email(to_email: str, token: str) -> None:
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
        _send_smtp(to_email, "Reset your Iris password", html)
    except Exception:
        logger.exception("Failed to send password reset email to %s", to_email)


def send_verification_email(to_email: str, token: str) -> None:
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
        _send_smtp(to_email, "Verify your Iris email address", html)
    except Exception:
        logger.exception("Failed to send verification email to %s", to_email)
