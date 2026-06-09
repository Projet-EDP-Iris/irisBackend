import re

_NOREPLY_RE = re.compile(
    r"\b(noreply|no-reply|donotreply|do-not-reply)\b",
    re.IGNORECASE,
)
_PROMO_SUBJECT_RE = re.compile(
    r"\b(promo|promotion|offre|deal|discount|soldes?|r[eé]duction|bon\s+plan|cashback|"
    r"code\s+promo|black\s+friday|cyber\s+monday|vente\s+priv[eé]e|flash\s+sale)\b",
    re.IGNORECASE,
)
_UNSUBSCRIBE_BODY_RE = re.compile(
    r"\b(manage\s+preferences|unsubscribe|opt.out|se\s+d[eé]sabonner)\b",
    re.IGNORECASE,
)


def truncate_email(subject: str, body: str) -> str:
    """Return subject + first 800 chars of body as a single string."""
    return f"{subject}\n{body[:800]}".strip()


def zero_shot_classify(
    sender: str,
    subject: str,
    body_snippet: str,
    headers: dict[str, str] | None = None,
) -> str | None:
    """
    Fast pre-classifier that short-circuits the full pipeline for obvious automated emails.

    Signals checked (any one is sufficient):
      - noreply / no-reply / donotreply in the sender address
      - List-Unsubscribe header present
      - unsubscribe / manage preferences / opt-out footer in body_snippet

    Returns:
        "bonsplans" — automated email with promo keywords in the subject
        "info"      — automated email without promo signals
        None        — cannot determine; caller should proceed with full pipeline
    """
    headers = headers or {}
    is_automated = bool(
        _NOREPLY_RE.search(sender or "")
        or "List-Unsubscribe" in headers
        or _UNSUBSCRIBE_BODY_RE.search(body_snippet or "")
    )
    if not is_automated:
        return None
    return "bonsplans" if _PROMO_SUBJECT_RE.search(subject or "") else "info"
