from fastapi import APIRouter

from app.schemas.detection import ExtractionResult
from app.schemas.prediction import (
    PredictionResponse,
    PredictionStatus,
    PredictSlotsFromDetectionRequest,
)
from app.services.prediction_service import get_suggested_slots

router = APIRouter()


def _resolve_extraction(body: PredictSlotsFromDetectionRequest) -> ExtractionResult:
    raw = body.extraction
    if isinstance(raw, list):
        return raw[0] if raw else ExtractionResult()
    return raw


@router.post("/predict/slots/from-detection", response_model=PredictionResponse)
async def predict_from_detection(body: PredictSlotsFromDetectionRequest) -> PredictionResponse:
    extraction = _resolve_extraction(body)
    suggestions = get_suggested_slots(
        extraction,
        preferences=body.preferences,
        calendar=body.calendar,
    )
    return PredictionResponse(
        suggested_slots=suggestions,
        status=PredictionStatus.READY_TO_SCHEDULE,
    )
