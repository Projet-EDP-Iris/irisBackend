from pydantic import BaseModel

from app.schemas.detection import ExtractionResult


class EmailItem(BaseModel):
    """One email as returned by GET /api/v1/emails (and used in fetch-and-detect)."""
    subject: str = ""
    body: str = ""
    message_id: str | None = None
    sender: str | None = None
    date: str | None = None


class FetchAndDetectResponse(BaseModel):
    emails: list[EmailItem]
    extractions: list[ExtractionResult]
