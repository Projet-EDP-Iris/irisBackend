from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.detection import (
    DetectResponse,
    EmailBatchInput,
    FeedbackInput,
    FeedbackResult,
    ThreadExtractionResult,
    ThreadInput,
    ValidationInput,
    ValidationResult,
)
from app.services.detection import (
    detect_batch,
    detect_thread,
    save_feedback,
    validate_extraction,
)

router = APIRouter(tags=["detection"])


@router.post("/detect", response_model=DetectResponse)
def post_detect(
    body: EmailBatchInput,
    current_user: User = Depends(get_current_active_user),
) -> DetectResponse:
    results = detect_batch(body.emails)
    return DetectResponse(results=results)


@router.post("/detect/thread", response_model=ThreadExtractionResult)
def post_detect_thread(
    body: ThreadInput,
    current_user: User = Depends(get_current_active_user),
) -> ThreadExtractionResult:
    return detect_thread(body.messages)


@router.post("/validate", response_model=ValidationResult)
def post_validate(
    body: ValidationInput,
    current_user: User = Depends(get_current_active_user),
) -> ValidationResult:
    return validate_extraction(body.extraction)


@router.post("/feedback", status_code=status.HTTP_201_CREATED, response_model=FeedbackResult)
def post_feedback(
    body: FeedbackInput,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> FeedbackResult:
    return save_feedback(body, db, user_id=current_user.id)
