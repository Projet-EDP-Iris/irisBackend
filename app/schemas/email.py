from pydantic import BaseModel

from app.schemas.detection import ExtractionResult
from app.schemas.prediction import PredictionStatus, RecommendedSlot


class EmailItem(BaseModel):
    """One email as returned by GET /api/v1/emails (and used in fetch-and-detect)."""
    subject: str = ""
    body: str = ""
    message_id: str | None = None
    sender: str | None = None
    date: str | None = None
    category: str = "info"  # UI tab: rdv | action | attente | bonsplans | info
    db_id: int | None = None  # DB primary key — populated after upsert
    provider: str = "unknown"  # "gmail" | "outlook" | "unknown"


class EmailFeedResponse(BaseModel):
    """Paginated response for GET /emails/feed (infinite scroll)."""
    emails: list[EmailItem]
    has_more: bool
    gmail_next_cursor: str | None = None
    outlook_next_skip: int = 0


class FetchAndDetectResponse(BaseModel):
    emails: list[EmailItem]
    extractions: list[ExtractionResult]


class FetchDetectPredictResponse(BaseModel):
    """Response for POST /api/v1/emails/fetch-detect-predict (Gmail to detection to prediction)."""
    emails: list[EmailItem]
    extractions: list[ExtractionResult]
    suggested_slots: list[RecommendedSlot]
    status: PredictionStatus
