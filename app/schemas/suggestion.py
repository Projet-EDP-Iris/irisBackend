from pydantic import BaseModel


class SuggestionResponse(BaseModel):
    email_id: int
    suggested_content: str
    status: str = "READY"


class SuggestionCreate(BaseModel):
    tone: str | None = "professional"


# ── Inline suggestion (no DB required) ─────────────────────────────────────

class InlineSuggestionRequest(BaseModel):
    subject: str
    body: str


class SuggestionVariant(BaseModel):
    label: str
    content: str


class InlineSuggestionResponse(BaseModel):
    variants: list[SuggestionVariant]
    status: str = "READY"
