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
    raw = body.extraction
    if isinstance(raw, list):
        return raw[0] if raw else ExtractionResult()
    return raw


@router.post("/predict/slots/{email_id}", response_model=PredictionResponse)
async def predict_from_detection(
    email_id: int,
    body: PredictSlotsFromDetectionRequest,
    db: Session = Depends(get_db)
) -> PredictionResponse:
    """Take detection output and return suggested meeting slots + summary."""
    email_record = db.query(Email).filter(Email.id == email_id).first()
    if not email_record:
        raise HTTPException(status_code=404, detail="Email non trouvé en base")
    extraction = email_record.extraction_data

    suggestions = get_suggested_slots(
        extraction,
        preferences=body.preferences,
        calendar=body.calendar,
    )
    email_record.predicted_slots = [s.dict() for s in suggestions]
    db.commit()
    db.refresh(email_record)
    return PredictionResponse(
        suggested_slots=suggestions,
        status=PredictionStatus.READY_TO_SCHEDULE,
        summary=email_record.summary or "Résumé en cours de génération........"
    )
