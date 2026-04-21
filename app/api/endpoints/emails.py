from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.db.database import get_db
from app.models.email import Email
from app.models.user import User
from app.schemas.detection import ExtractionResult
from app.schemas.email import EmailItem, FetchAndDetectResponse, FetchDetectPredictResponse
from app.schemas.prediction import CalendarAvailability, PredictionStatus, UserPreferences
from app.services.detection import detect_batch
from app.services.gmail_service import GmailService
from app.services.prediction_service import get_suggested_slots

router = APIRouter(tags=["emails"])


def _get_emails_for_user(user_id: int, max_results: int = 10) -> list[EmailItem]:
    svc = GmailService()
    if not svc.authenticate_for_user(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gmail not connected for this user",
        )
    raw = svc.fetch_recent_emails(n=max_results)
    return [
        EmailItem(
            subject=r["subject"],
            body=r["body"],
            message_id=r["message_id"],
            sender=r.get("sender"),
            date=r.get("date"),
        )
        for r in raw
    ]


@router.get("/emails", response_model=list[EmailItem])
def get_emails(
    max_results: int = 10,
    current_user: User = Depends(get_current_active_user),
) -> list[EmailItem]:
    """Fetch recent Gmail emails for the authenticated user. Returns 404 if Gmail is not connected."""
    return _get_emails_for_user(current_user.id, max_results=max_results)


@router.post("/emails/fetch-and-detect", response_model=FetchAndDetectResponse)
def post_fetch_and_detect(
    max_results: int = 10,
    current_user: User = Depends(get_current_active_user),
) -> FetchAndDetectResponse:
    """Fetch recent Gmail emails and run detection on each. Returns 404 if Gmail is not connected."""
    svc = GmailService()
    if not svc.authenticate_for_user(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gmail not connected for this user",
        )
    emails = svc.fetch_recent_emails_as_inputs(n=max_results)
    extractions = detect_batch(emails)
    email_items = [
        EmailItem(
            subject=e.subject,
            body=e.body,
            message_id=e.message_id,
        )
        for e in emails
    ]
    return FetchAndDetectResponse(emails=email_items, extractions=extractions)


class FetchDetectPredictBody(BaseModel):
    """Optional body for fetch-detect-predict (preferences and calendar for prediction step)."""
    preferences: UserPreferences | None = None
    calendar: CalendarAvailability | None = None


@router.post("/emails/fetch-detect-predict", response_model=FetchDetectPredictResponse)
def post_fetch_detect_predict(
    max_results: int = 10,
    body: FetchDetectPredictBody | None = Body(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> FetchDetectPredictResponse:
    """Fetch Gmail emails, run detection, then prediction. Returns 404 if Gmail is not connected."""
    svc = GmailService()
    if not svc.authenticate_for_user(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gmail not connected for this user",
        )
    emails = svc.fetch_recent_emails_as_inputs(n=max_results)
    extractions = detect_batch(emails)
    extraction = extractions[0] if extractions else ExtractionResult()
    prefs = body.preferences if body else None
    cal = body.calendar if body else None
    suggested_slots = get_suggested_slots(extraction, preferences=prefs, calendar=cal)

    for i, e in enumerate(emails):
        # On crée l'objet pour la base de données
        db_email = Email(
            subject=e.subject,
            body=e.body,
            message_id=e.message_id,
            user_id=current_user.id,
            summary=None,
            predicted_slots=[s.model_dump(mode="json") for s in suggested_slots] if i == 0 else None,
            status="predicted"
        )
        db.add(db_email)

    db.commit() # On valide l'enregistrement
    email_items = [
        EmailItem(subject=e.subject, body=e.body, message_id=e.message_id)
        for e in emails
    ]
    return FetchDetectPredictResponse(
        emails=email_items,
        extractions=extractions,
        suggested_slots=suggested_slots,
        status=PredictionStatus.READY_TO_SCHEDULE,
    )
