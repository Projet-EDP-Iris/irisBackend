import os
import logging

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
from app.services.gmail_service import GmailService, get_token_path_for_user
from app.services.outlook_email_service import (
    fetch_outlook_emails,
    is_outlook_connected,
)
from app.services.prediction_service import get_suggested_slots

router = APIRouter(tags=["emails"])
logger = logging.getLogger(__name__)


def _get_gmail_emails(user_id: int, max_results: int = 10) -> list[EmailItem]:
    """Fetch emails from Gmail. Returns empty list if not connected or on error."""
    svc = GmailService()
    if not svc.authenticate_for_user(user_id):
        return []
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


def _get_outlook_emails(user_id: int, max_results: int = 10) -> list[EmailItem]:
    """Fetch emails from Outlook. Returns empty list if not connected or on error."""
    if not is_outlook_connected(user_id):
        return []
    try:
        return fetch_outlook_emails(user_id, n=max_results)
    except Exception as exc:
        logger.warning("Outlook email fetch failed for user %d: %s", user_id, exc)
        return []


def _get_all_emails_for_user(user_id: int, max_results: int = 10) -> list[EmailItem]:
    """
    Merge Gmail and Outlook emails for a user.
    - Returns 404 if neither Gmail nor Outlook is connected.
    - Silently skips a source that fails but returns results from the other.
    - Returns emails sorted by date (most recent first), capped at max_results.
    """
    gmail_connected = os.path.exists(get_token_path_for_user(user_id))
    outlook_connected = is_outlook_connected(user_id)

    if not gmail_connected and not outlook_connected:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No email provider connected. Please connect Gmail or Outlook.",
        )

    emails: list[EmailItem] = []

    if gmail_connected:
        gmail_emails = _get_gmail_emails(user_id, max_results)
        emails.extend(gmail_emails)
        logger.info("Gmail: %d emails fetched for user %d", len(gmail_emails), user_id)

    if outlook_connected:
        outlook_emails_list = _get_outlook_emails(user_id, max_results)
        emails.extend(outlook_emails_list)
        logger.info("Outlook: %d emails fetched for user %d", len(outlook_emails_list), user_id)

    if not emails and (gmail_connected or outlook_connected):
        # Both sources returned empty — can happen when inbox is empty
        return []

    # Sort by date descending (emails without date go last)
    emails.sort(key=lambda e: e.date or "", reverse=True)
    return emails[:max_results]


@router.get("/emails", response_model=list[EmailItem])
def get_emails(
    max_results: int = 10,
    current_user: User = Depends(get_current_active_user),
) -> list[EmailItem]:
    """
    Fetch recent emails for the authenticated user.

    Aggregates from all connected providers (Gmail and/or Outlook).
    Returns HTTP 404 if neither Gmail nor Outlook is connected.
    """
    return _get_all_emails_for_user(current_user.id, max_results=max_results)


@router.post("/emails/fetch-and-detect", response_model=FetchAndDetectResponse)
def post_fetch_and_detect(
    max_results: int = 10,
    current_user: User = Depends(get_current_active_user),
) -> FetchAndDetectResponse:
    """
    Fetch recent emails (Gmail + Outlook) and run NLP detection on each.
    Returns HTTP 404 if no email provider is connected.
    """
    email_items = _get_all_emails_for_user(current_user.id, max_results=max_results)

    # Build EmailInput objects for detection
    from app.schemas.detection import EmailInput  # local import to avoid circular
    email_inputs = [
        EmailInput(
            subject=e.subject,
            body=e.body,
            message_id=e.message_id or "",
        )
        for e in email_items
    ]
    extractions = detect_batch(email_inputs)
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
    """
    Fetch emails (Gmail + Outlook), run detection, then prediction.
    Returns HTTP 404 if no email provider is connected.
    """
    email_items = _get_all_emails_for_user(current_user.id, max_results=max_results)

    from app.schemas.detection import EmailInput
    email_inputs = [
        EmailInput(
            subject=e.subject,
            body=e.body,
            message_id=e.message_id or "",
        )
        for e in email_items
    ]
    extractions = detect_batch(email_inputs)
    extraction = extractions[0] if extractions else ExtractionResult()
    prefs = body.preferences if body else None
    cal = body.calendar if body else None
    suggested_slots = get_suggested_slots(extraction, preferences=prefs, calendar=cal)

    for i, e in enumerate(email_items):
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

    db.commit()
    return FetchDetectPredictResponse(
        emails=email_items,
        extractions=extractions,
        suggested_slots=suggested_slots,
        status=PredictionStatus.READY_TO_SCHEDULE,
    )
