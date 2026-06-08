import logging

import resend

from app.core.config import settings

logger = logging.getLogger(__name__)


def _iris_email_html(title: str, body_html: str) -> str:
    """Wrap content in the shared Iris email shell."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="520" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,#f97316,#ea580c);padding:32px 40px;text-align:center;">
              <span style="font-size:28px;font-weight:800;color:#ffffff;letter-spacing:-0.5px;">iris</span>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding:40px;">
              {body_html}
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="background:#f9f9f9;padding:24px 40px;text-align:center;border-top:1px solid #eee;">
              <p style="margin:0;font-size:12px;color:#999;">
                You received this email because you have an Iris account.<br />
                If you didn't request this, you can safely ignore it.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _send(to_email: str, subject: str, html: str) -> None:
    resend.api_key = settings.RESEND_API_KEY
    resend.Emails.send({
        "from": settings.RESEND_FROM_EMAIL,
        "to": [to_email],
        "subject": subject,
        "html": html,
    })


async def send_password_reset_email(to_email: str, token: str) -> None:
    if not settings.EMAIL_ENABLED:
        logger.info("EMAIL_ENABLED=False — skipping password reset email to %s", to_email)
        return

    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    body = f"""
      <h2 style="margin:0 0 8px;font-size:22px;font-weight:700;color:#111;">Reset your password</h2>
      <p style="margin:0 0 24px;font-size:15px;color:#555;line-height:1.6;">
        We received a request to reset the password for your Iris account.
        Click the button below — this link expires in <strong>{settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes</strong>.
      </p>
      <table cellpadding="0" cellspacing="0" style="margin:0 0 24px;">
        <tr>
          <td style="background:linear-gradient(135deg,#f97316,#ea580c);border-radius:10px;padding:14px 32px;">
            <a href="{reset_url}" style="color:#fff;font-size:15px;font-weight:600;text-decoration:none;">
              Reset my password →
            </a>
          </td>
        </tr>
      </table>
      <p style="margin:0;font-size:13px;color:#888;">
        Or copy this link into your browser:<br />
        <span style="color:#f97316;word-break:break-all;">{reset_url}</span>
      </p>
    """
    html = _iris_email_html("Reset your Iris password", body)
    try:
        _send(to_email, "Reset your Iris password", html)
    except Exception:
        logger.exception("Failed to send password reset email to %s", to_email)


async def send_verification_email(to_email: str, token: str) -> None:
    if not settings.EMAIL_ENABLED:
        logger.info("EMAIL_ENABLED=False — skipping verification email to %s", to_email)
        return

    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    body = f"""
      <h2 style="margin:0 0 8px;font-size:22px;font-weight:700;color:#111;">Verify your email</h2>
      <p style="margin:0 0 24px;font-size:15px;color:#555;line-height:1.6;">
        Welcome to Iris! Please verify your email address to activate your account.
        This link expires in <strong>{settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS} hours</strong>.
      </p>
      <table cellpadding="0" cellspacing="0" style="margin:0 0 24px;">
        <tr>
          <td style="background:linear-gradient(135deg,#f97316,#ea580c);border-radius:10px;padding:14px 32px;">
            <a href="{verify_url}" style="color:#fff;font-size:15px;font-weight:600;text-decoration:none;">
              Verify my email →
            </a>
          </td>
        </tr>
      </table>
      <p style="margin:0;font-size:13px;color:#888;">
        Or copy this link into your browser:<br />
        <span style="color:#f97316;word-break:break-all;">{verify_url}</span>
      </p>
    """
    html = _iris_email_html("Verify your Iris email", body)
    try:
        _send(to_email, "Verify your Iris email address", html)
    except Exception:
        logger.exception("Failed to send verification email to %s", to_email)


async def send_welcome_email(to_email: str, name: str | None = None) -> None:
    if not settings.EMAIL_ENABLED:
        logger.info("EMAIL_ENABLED=False — skipping welcome email to %s", to_email)
        return

    greeting = f"Welcome, {name}!" if name else "Welcome to Iris!"
    body = f"""
      <h2 style="margin:0 0 8px;font-size:22px;font-weight:700;color:#111;">{greeting}</h2>
      <p style="margin:0 0 20px;font-size:15px;color:#555;line-height:1.6;">
        Your account is all set. Iris helps you manage your emails, calendar, and tasks — all in one place, powered by AI.
      </p>
      <table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 24px;">
        {"".join(f'''
        <tr>
          <td style="padding:10px 0;border-bottom:1px solid #f0f0f0;">
            <table cellpadding="0" cellspacing="0">
              <tr>
                <td style="width:36px;height:36px;background:#fff3e6;border-radius:8px;text-align:center;vertical-align:middle;font-size:18px;">{icon}</td>
                <td style="padding-left:12px;">
                  <p style="margin:0;font-size:14px;font-weight:600;color:#111;">{feature}</p>
                  <p style="margin:2px 0 0;font-size:12px;color:#888;">{desc}</p>
                </td>
              </tr>
            </table>
          </td>
        </tr>''' for icon, feature, desc in [
            ("✉️", "Smart Inbox", "AI sorts and summarises your emails"),
            ("📅", "Calendar Sync", "Connect Gmail, Outlook, or Apple Calendar"),
            ("✅", "Task Management", "Turn emails into tasks automatically"),
        ])}
      </table>
      <table cellpadding="0" cellspacing="0">
        <tr>
          <td style="background:linear-gradient(135deg,#f97316,#ea580c);border-radius:10px;padding:14px 32px;">
            <a href="{settings.FRONTEND_URL}" style="color:#fff;font-size:15px;font-weight:600;text-decoration:none;">
              Open Iris →
            </a>
          </td>
        </tr>
      </table>
    """
    html = _iris_email_html("Welcome to Iris", body)
    try:
        _send(to_email, "Welcome to Iris 👋", html)
    except Exception:
        logger.exception("Failed to send welcome email to %s", to_email)
