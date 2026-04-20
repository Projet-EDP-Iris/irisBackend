from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.email import Email
from app.schemas.detection import ExtractionResult
from app.schemas.prediction import (
    PredictionResponse,
    PredictionStatus,
    PredictSlotsFromDetectionRequest,
)
from app.services.prediction_service import get_suggested_slots

router = APIRouter(tags=["prediction"])


def _resolve_extraction(body: PredictSlotsFromDetectionRequest) -> ExtractionResult:
    """Return a single ExtractionResult from body (list or single)."""
    raw = body.extraction
    if isinstance(raw, list):
        return raw[0] if raw else ExtractionResult()
    return raw


@router.post("/predict/slots/from-detection", response_model=PredictionResponse)
async def predict_from_detection_inline(
    body: PredictSlotsFromDetectionRequest,
) -> PredictionResponse:
    """Generate meeting slots directly from a detection payload (no DB required).

    This is the endpoint used by the frontend and the test suite.
    """
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


@router.post("/predict/slots/{email_id}", response_model=PredictionResponse)
async def predict_from_email_record(
    email_id: int,
    body: PredictSlotsFromDetectionRequest,
    db: Session = Depends(get_db),
) -> PredictionResponse:
    """Generate meeting slots from a stored email record and persist results.

    Reads extraction_data from the DB, runs prediction, and saves predicted_slots.
    """
    email_record = db.query(Email).filter(Email.id == email_id).first()
    if not email_record:
        raise HTTPException(status_code=404, detail="Email non trouve en base")

    raw_extraction = email_record.extraction_data
    if raw_extraction is None:
        raise HTTPException(
            status_code=400,
            detail="Aucune donnee d extraction. Lancez d abord la detection (/detect).",
        )

    # Fix: parse JSON dict back into ExtractionResult before calling service
    extraction = ExtractionResult.model_validate(raw_extraction)

    suggestions = get_suggested_slots(
        extraction,
        preferences=body.preferences,
        calendar=body.calendar,
    )

    email_record.predicted_slots = [s.model_dump() for s in suggestions]
    db.commit()
    db.refresh(email_record)

    return PredictionResponse(
        suggested_slots=suggestions,
        status=PredictionStatus.READY_TO_SCHEDULE,
        summary=email_record.summary or "Resume en cours de generation...",
    )
