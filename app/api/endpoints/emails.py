import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime as _parsedate

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.db.database import get_db
from app.models.email import Email
from app.models.user import User
from app.schemas.detection import ExtractionResult
from app.schemas.email import EmailItem, EmailFeedResponse, FetchAndDetectResponse, FetchDetectPredictResponse
from app.schemas.prediction import CalendarAvailability, PredictionStatus, UserPreferences
from app.services.detection import categorize_email, detect_batch
from app.schemas.detection import EmailInput as DetectionEmailInput
from app.services.gmail_service import GmailService
from app.services.outlook_email_service import (
    fetch_outlook_emails,
    fetch_outlook_email_page,
    is_outlook_connected,
)
from app.services.prediction_service import get_suggested_slots

router = APIRouter(tags=["emails"])
logger = logging.getLogger(__name__)


def _sort_key(date_str: str | None) -> datetime:
    if not date_str:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return _parsedate(date_str)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def _upsert_email_items(db: Session, user_id: int, items: list[EmailItem]) -> None:
    """Insert or update each email in the DB and populate db_id on the item."""
    for item in items:
        if not item.message_id:
            continue
        existing = (
            db.query(Email)
            .filter(Email.message_id == item.message_id, Email.user_id == user_id)
            .first()
        )
        if existing:
            item.db_id = existing.id
            # Backfill metadata that may have been missing on first insert
            if not existing.category and item.category:
                existing.category = item.category
            if not existing.email_date and item.date:
                existing.email_date = item.date
            if not existing.provider and item.provider and item.provider != "unknown":
                existing.provider = item.provider
            if not existing.sender and item.sender:
                existing.sender = item.sender
        else:
            db_email = Email(
                subject=item.subject,
                body=item.body,
                message_id=item.message_id,
                user_id=user_id,
                status="fetched",
                sender=item.sender,
                category=item.category,
                email_date=item.date,
                provider=item.provider if item.provider != "unknown" else None,
            )
            db.add(db_email)
            db.flush()
            item.db_id = db_email.id
    db.commit()


def _get_gmail_emails(user_id: int, max_results: int | None = None) -> list[EmailItem]:
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
            category=categorize_email(
                DetectionEmailInput(subject=r["subject"], body=r["body"])
            ),
            provider="gmail",
        )
        for r in raw
    ]


def _get_outlook_emails(user_id: int, max_results: int | None = None) -> list[EmailItem]:
    """Fetch emails from Outlook. Returns empty list if not connected or on error."""
    if not is_outlook_connected(user_id):
        return []
    try:
        return fetch_outlook_emails(user_id, n=max_results)
    except Exception as exc:
        logger.warning("Outlook email fetch failed for user %d: %s", user_id, exc)
        return []


def _get_all_emails_for_user(user_id: int, max_results: int | None = None) -> list[EmailItem]:
    """
    Merge Gmail and Outlook emails for a user.
    - Returns 404 if neither Gmail nor Outlook is connected.
    - Silently skips a source that fails but returns results from the other.
    - Returns emails sorted by date (most recent first). max_results=None fetches all.
    """
    from app.services.gmail_service import _load_gmail_token_from_db
    gmail_connected = _load_gmail_token_from_db(user_id) is not None
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
    return emails if max_results is None else emails[:max_results]


@router.get("/emails", response_model=list[EmailItem])
def get_emails(
    max_results: int | None = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> list[EmailItem]:
    """
    Fetch recent emails for the authenticated user.

    Aggregates from all connected providers (Gmail and/or Outlook).
    Returns HTTP 404 if neither Gmail nor Outlook is connected.
    """
    items = _get_all_emails_for_user(current_user.id, max_results=max_results)
    _upsert_email_items(db, current_user.id, items)
    return items


@router.post("/emails/fetch-and-detect", response_model=FetchAndDetectResponse)
def post_fetch_and_detect(
    max_results: int | None = None,
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
    max_results: int | None = None,
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

    _upsert_email_items(db, current_user.id, email_items)

    # Store predicted slots on the first email's DB record
    if email_items and email_items[0].db_id and suggested_slots:
        first_record = db.query(Email).filter(Email.id == email_items[0].db_id).first()
        if first_record:
            first_record.predicted_slots = [s.model_dump(mode="json") for s in suggested_slots]
            first_record.status = "predicted"
            db.commit()

    return FetchDetectPredictResponse(
        emails=email_items,
        extractions=extractions,
        suggested_slots=suggested_slots,
        status=PredictionStatus.READY_TO_SCHEDULE,
    )


@router.get("/emails/cached", response_model=EmailFeedResponse)
def get_cached_emails(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> EmailFeedResponse:
    """
    Return emails already stored in the DB for this user — no external API calls.
    Used for instant first-paint before the background /emails/feed refresh completes.
    """
    rows = (
        db.query(Email)
        .filter(Email.user_id == current_user.id)
        .order_by(Email.received_at.desc())
        .offset(offset)
        .limit(limit + 1)
        .all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [
        EmailItem(
            subject=row.subject or "",
            body=row.body or "",
            message_id=row.message_id,
            sender=row.sender,
            db_id=row.id,
            category=row.category or "info",
            date=row.email_date,
            provider=row.provider or "unknown",
        )
        for row in rows
    ]
    return EmailFeedResponse(emails=items, has_more=has_more)


@router.get("/emails/feed", response_model=EmailFeedResponse)
def get_email_feed(
    limit: int = 50,
    gmail_cursor: str | None = None,
    outlook_skip: int = 0,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> EmailFeedResponse:
    """
    Paginated email feed for infinite scroll.
    Fetches one page from Gmail (batch, metadata + snippet) and one page from Outlook.
    """
    from app.schemas.detection import EmailInput as _DetectionInput

    # Pre-fetch known message IDs + stored categories to skip NLP for already-categorised emails.
    existing_categories: dict[str, str] = {
        row.message_id: (row.category or "info")
        for row in db.query(Email.message_id, Email.category)
            .filter(Email.user_id == current_user.id)
            .all()
        if row.message_id
    }
    existing_ids = set(existing_categories.keys())

    gmail_emails: list[EmailItem] = []
    gmail_next_cursor: str | None = None

    svc = GmailService()
    if svc.authenticate_for_user(current_user.id):
        raw_list, gmail_next_cursor = svc.fetch_email_page(page_token=gmail_cursor, limit=limit)
        gmail_emails = [
            EmailItem(
                subject=r["subject"],
                body=r["body"],
                message_id=r["message_id"],
                sender=r.get("sender"),
                date=r.get("date"),
                category=(
                    categorize_email(_DetectionInput(subject=r["subject"], body=r["body"]))
                    if r.get("message_id") not in existing_ids
                    else existing_categories.get(r.get("message_id"), "info")
                ),
                provider="gmail",
            )
            for r in raw_list
        ]

    outlook_emails: list[EmailItem] = []
    outlook_has_more = False
    outlook_next_skip = outlook_skip

    if is_outlook_connected(current_user.id):
        try:
            outlook_page, outlook_has_more = fetch_outlook_email_page(
                current_user.id, skip=outlook_skip, limit=limit
            )
            outlook_emails = outlook_page
            if outlook_has_more:
                outlook_next_skip = outlook_skip + len(outlook_emails)
        except Exception as exc:
            logger.warning("Outlook feed fetch failed for user %d: %s", current_user.id, exc)

    all_emails = gmail_emails + outlook_emails
    all_emails.sort(key=lambda e: _sort_key(e.date), reverse=True)

    has_more = (gmail_next_cursor is not None) or outlook_has_more

    _upsert_email_items(db, current_user.id, all_emails)

    return EmailFeedResponse(
        emails=all_emails,
        has_more=has_more,
        gmail_next_cursor=gmail_next_cursor,
        outlook_next_skip=outlook_next_skip,
    )


def sync_user_emails_background(user_id: int) -> None:
    """Fetch the first page of emails from all connected providers and persist them.
    Called as a FastAPI BackgroundTask after OAuth so the DB is populated before
    the frontend's next /emails/cached or /emails/feed poll."""
    from app.db.database import SessionLocal  # local import — runs in background thread
    from app.schemas.detection import EmailInput as _DI
    db = SessionLocal()
    try:
        items: list[EmailItem] = []
        svc = GmailService()
        if svc.authenticate_for_user(user_id):
            try:
                raw_list, _ = svc.fetch_email_page(page_token=None, limit=50)
                items.extend([
                    EmailItem(
                        subject=r["subject"],
                        body=r["body"],
                        message_id=r["message_id"],
                        sender=r.get("sender"),
                        date=r.get("date"),
                        category=categorize_email(_DI(subject=r["subject"], body=r["body"])),
                        provider="gmail",
                    )
                    for r in raw_list
                ])
                logger.info("Background sync: fetched %d Gmail emails for user_id=%d", len(raw_list), user_id)
            except Exception:
                logger.exception("Background Gmail sync failed for user_id=%d", user_id)
        if is_outlook_connected(user_id):
            try:
                outlook_page, _ = fetch_outlook_email_page(user_id, skip=0, limit=50)
                items.extend(outlook_page)
                logger.info("Background sync: fetched %d Outlook emails for user_id=%d", len(outlook_page), user_id)
            except Exception:
                logger.exception("Background Outlook sync failed for user_id=%d", user_id)
        if items:
            _upsert_email_items(db, user_id, items)
    except Exception:
        logger.exception("Background email sync failed for user_id=%d", user_id)
    finally:
        db.close()


@router.get("/emails/body/{message_id}")
def get_email_body(
    message_id: str,
    provider: str = "gmail",
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """Fetch the full body of a single email. Used when opening a Gmail email from the feed."""
    if provider == "gmail":
        svc = GmailService()
        if not svc.authenticate_for_user(current_user.id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gmail not connected")
        body = svc.fetch_email_body(message_id)
        return {"body": body}
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown provider")
