from typing import Any, Literal

from pydantic import BaseModel

Classification = Literal[
    "meeting_schedule",
    "meeting_cancel",
    "meeting_reschedule",
    "other",
]
ThreadStatusLiteral = Literal["pending", "confirmed", "cancelled", "unknown"]


class WorkingHours(BaseModel):
    start: str | None = None
    end: str | None = None
    timezone: str | None = None


class TimeWindow(BaseModel):
    start: str | None = None
    end: str | None = None
    timezone: str | None = None


class Participant(BaseModel):
    email: str | None = None
    name: str | None = None


class Constraint(BaseModel):
    type: str
    value: str | None = None


class EmailInput(BaseModel):
    subject: str = ""
    body: str = ""
    message_id: str | None = None


class EmailBatchInput(BaseModel):
    emails: list[EmailInput]


class ThreadInput(BaseModel):
    messages: list[EmailInput]


class ValidationInput(BaseModel):
    extraction: dict[str, Any]


class FeedbackInput(BaseModel):
    message_id: str
    original_extraction: dict[str, Any]
    corrections: dict[str, Any]


class ExtractionResult(BaseModel):
    classification: Classification = "other"
    proposed_times: list[TimeWindow] = []
    duration_minutes: int | None = None
    timezone: str | None = None
    modality: str | None = None
    meeting_link: str | None = None
    participants: list[Participant] = []
    organizer: Participant | None = None
    constraints: list[Constraint] = []
    thread_status: ThreadStatusLiteral = "unknown"
    needs_clarification: bool = False
    confidence: float = 0.0


class ThreadExtractionResult(BaseModel):
    merged: ExtractionResult
    message_results: list[ExtractionResult] = []


class ValidationResult(BaseModel):
    valid: bool = False
    missing_fields: list[str] = []
    clarifying_questions: list[str] = []


class FeedbackResult(BaseModel):
    feedback_id: int


class DetectResponse(BaseModel):
    results: list[ExtractionResult]
