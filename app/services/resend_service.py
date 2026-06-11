import base64
import logging
from dataclasses import dataclass, field

import resend

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
    Send a reply email via Resend with RFC 2822 threading headers.

    Sets In-Reply-To and References headers from rfc_message_id so the reply
    appears as a thread in the recipient's mail client. If rfc_message_id is
    None (e.g. email was fetched before the column was added), the reply still
    sends but won't be grouped as a thread.

    Returns the Resend message ID on success.
    Raises ValueError if RESEND_API_KEY is not configured.
    """
    if not settings.RESEND_API_KEY:
        raise ValueError("RESEND_API_KEY is not configured.")

    resend.api_key = settings.RESEND_API_KEY

    threading_headers: dict[str, str] = {}
    if req.rfc_message_id:
        threading_headers["In-Reply-To"] = req.rfc_message_id
        threading_headers["References"] = req.rfc_message_id

    subject = req.subject if req.subject.lower().startswith("re:") else f"Re: {req.subject}"

    params: dict = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [req.to],
        "subject": subject,
        "text": req.text,
        "headers": threading_headers,
    }

    if req.attachments:
        params["attachments"] = [
            {"filename": name, "content": base64.b64encode(data).decode("ascii")}
            for name, data in req.attachments
        ]

    response = resend.Emails.send(params)  # type: ignore[arg-type]
    logger.info("Reply sent via Resend id=%s to=%s", response.get("id"), req.to)
    return response["id"]
