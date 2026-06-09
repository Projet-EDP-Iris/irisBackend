import json

from app.core.config import settings

_CATEGORY_CONTEXT = {
    "rdv": "scheduling, cancelling, or rescheduling a meeting",
    "action": "requesting an action or decision from the reader",
    "attente": "following up or waiting for a reply",
}

_AUTO_REPLY_SYSTEM = (
    "You are a professional email assistant. Write a short, polite, natural reply.\n"
    "1. Detect the language of the incoming email and reply in THAT SAME language.\n"
    "2. Be warm and human — avoid stiff corporate language.\n"
    "3. For meeting emails: acknowledge and propose confirming availability or suggest next steps.\n"
    "4. For action emails: confirm receipt and indicate you will act, or ask for clarification if the request is vague.\n"
    "5. For follow-up/attente emails: apologise for the delay and provide a concrete update or timeline.\n"
    "6. Keep the reply to 3–5 sentences. No subject line. No placeholder text like [Your Name]."
)


async def generate_auto_reply(
    subject: str,
    body_truncated: str,
    sender_name: str,
    category: str,
) -> str:
    """Draft a contextual auto-reply for rdv / action / attente emails.

    Detects the language of the email and replies in kind.
    Returns empty string if OpenAI is unavailable or on any error.
    """
    if not settings.OPENAI_API_KEY:
        return ""

    context = _CATEGORY_CONTEXT.get(category, "general inquiry")
    user_content = (
        f"Email context: this is a '{context}' email.\n"
        f"From: {sender_name or 'the sender'}\n"
        f"Subject: {subject[:200]}\n"
        f"Body: {body_truncated[:600]}\n\n"
        "Write a reply:"
    )

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _AUTO_REPLY_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            max_tokens=300,
            temperature=0.7,
        )
        text = resp.choices[0].message.content
        return text.strip() if text else ""
    except Exception:
        return ""


_SUGGESTIONS_SYSTEM = (
    "You are an email reply assistant. Given a summary of an email, generate exactly "
    "three reply variants as a JSON array. Each object must have keys 'label' and 'content'.\n"
    "Labels must be exactly: 'Amical', 'Formel', 'Court'.\n"
    "- Amical: warm and friendly tone, conversational.\n"
    "- Formel: professional and formal tone, business-appropriate.\n"
    "- Court: very short (1–2 sentences), direct.\n"
    "Detect the language from the summary and reply in that language.\n"
    "Return ONLY the JSON array, no other text."
)

_EMPTY_VARIANTS = [
    {"label": "Amical", "content": ""},
    {"label": "Formel", "content": ""},
    {"label": "Court", "content": ""},
]


async def generate_summary(subject: str, body: str) -> str:
    """Summarize an email in 2–3 sentences in its original language.

    Detects the language of the email and writes the summary in that language.
    Focuses on: what the sender wants, any deadlines or dates, and required action.
    Returns empty string if OpenAI is unavailable or on any error.
    """
    if not settings.OPENAI_API_KEY:
        return ""

    system = (
        "You are an email summarizer. Summarize the email in 2–3 concise sentences. "
        "Detect the language of the email and write the summary in THAT SAME language. "
        "Focus on: what the sender wants, any deadlines or dates, and the required action (if any). "
        "Return ONLY the summary text — no labels, no intro phrase."
    )

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Subject: {subject[:200]}\n\n{body[:1500]}"},
            ],
            max_tokens=150,
            temperature=0.3,
        )
        text = resp.choices[0].message.content
        return text.strip() if text else ""
    except Exception:
        return ""


async def generate_mail_suggestions(summary: str) -> list[dict]:
    """Generate three reply variants (Amical / Formel / Court) for an email summary.

    Falls back to empty variants if OpenAI is unavailable.
    """
    if not settings.OPENAI_API_KEY:
        return _EMPTY_VARIANTS

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SUGGESTIONS_SYSTEM},
                {"role": "user", "content": f"Email summary: {summary[:500]}"},
            ],
            max_tokens=500,
            temperature=0.8,
        )
        content = resp.choices[0].message.content
        if not content:
            return _EMPTY_VARIANTS
        variants = json.loads(content)
        if isinstance(variants, list) and len(variants) == 3:
            return variants
    except Exception:
        pass

    return _EMPTY_VARIANTS
