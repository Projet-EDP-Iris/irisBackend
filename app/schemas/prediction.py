from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from app.schemas.detection import (
    ExtractionResult,
    TimeWindow,
    WorkingHours,
)


class PredictionStatus(str, Enum):
    READY_TO_SCHEDULE = "READY_TO_SCHEDULE"


class UserPreferences(BaseModel):
    working_hours: WorkingHours | None = None
    preferred_duration_minutes: int | None = None
    timezone: str | None = None


class CalendarAvailability(BaseModel):
    busy_slots: list[TimeWindow] | None = None
    free_slots: list[TimeWindow] | None = None


class PredictSlotsFromDetectionRequest(BaseModel):
    extraction: ExtractionResult | list[ExtractionResult]
    preferences: UserPreferences | None = None
    calendar: CalendarAvailability | None = None


class RecommendedSlot(BaseModel):
    start_time: datetime
    end_time: datetime
    score: float
    label: str


class PredictionResponse(BaseModel):
    suggested_slots: list[RecommendedSlot]
    status: PredictionStatus = PredictionStatus.READY_TO_SCHEDULE
    message: str | None = None
    summary: str | None = None