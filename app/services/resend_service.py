import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ReplyRequest:
    to: str
    subject: str
    text: str
    rfc_message_id: str | None
    attachments: list[tuple[str, bytes]] = field(default_factory=list)


def send_reply(req: ReplyRequest) -> str:
    """
    Send a reply email via SMTP with RFC 2822 threading headers.

    Sets In-Reply-To and References headers from rfc_message_id so the reply
    appears as a thread in the recipient's mail client. If rfc_message_id is
    None (e.g. email was fetched before the column was added), the reply still
    sends but won't be grouped as a thread.

    Returns a synthetic message ID on success (SMTP does not expose the server-side ID).
    Raises ValueError if SMTP credentials are not configured.
    """
    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be set to send replies.")

    subject = req.subject if req.subject.lower().startswith("re:") else f"Re: {req.subject}"

    msg = MIMEMultipart("mixed")
    msg["From"] = settings.SMTP_FROM_EMAIL
    msg["To"] = req.to
    msg["Subject"] = subject

    if req.rfc_message_id:
        msg["In-Reply-To"] = req.rfc_message_id
        msg["References"] = req.rfc_message_id

    msg.attach(MIMEText(req.text, "plain", "utf-8"))

    for filename, data in req.attachments:
        part = MIMEApplication(data)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)

    context = ssl.create_default_context()
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        if settings.SMTP_USE_TLS:
            server.starttls(context=context)
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_FROM_EMAIL, req.to, msg.as_string())

    synthetic_id = f"<smtp-reply-{id(req)}@iris>"
    logger.info("Reply sent via SMTP to=%s subject=%r", req.to, subject)
    return synthetic_id
