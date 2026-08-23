import logging
import re as _re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed as _as_completed
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime as _parsedate

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func as _func
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.db.database import get_db
from app.models.email import Email
from app.models.user import User
from app.schemas.detection import EmailInput as DetectionEmailInput
from app.schemas.detection import ExtractionResult
from app.schemas.email import (
    EmailFeedResponse,
    EmailItem,
    FetchAndDetectResponse,
    FetchDetectPredictResponse,
)
from app.schemas.prediction import CalendarAvailability, PredictionStatus, UserPreferences
from app.services.detection import categorize_email, detect_batch, enrich_batch
from app.services.gmail_service import GmailService
from app.services.google_tasks_service import create_google_task
from app.services.outlook_tasks_service import create_outlook_task
from app.services.outlook_email_service import (
    fetch_outlook_delta,
    fetch_outlook_email_page,
    fetch_outlook_emails,
    is_outlook_connected,
)
from app.services.prediction_service import get_suggested_slots

router = APIRouter(tags=["emails"])
logger = logging.getLogger(__name__)

# Reverse of app.nlp.extractor.classification_to_category — used to build a cheap
# placeholder ExtractionResult for emails that already have a stored category, so
# fetch-and-detect / fetch-detect-predict can skip re-running NLP detection on them.
_CATEGORY_TO_CLASSIFICATION: dict[str, str] = {
    "rdv": "meeting_schedule",
    "action": "action",
    "attente": "attente",
    "bonsplans": "bonsplans",
    "info": "info",
}


def _sort_key(date_str: str | None) -> datetime:
    if not date_str:
        return datetime.min.replace(tzinfo=UTC)
    try:
        return _parsedate(date_str)
    except Exception:
        return datetime.min.replace(tzinfo=UTC)


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
            if item.category and (not existing.category or existing.category == "info"):
                existing.category = item.category
            if not existing.email_date and item.date:
                existing.email_date = item.date
            if not existing.provider and item.provider and item.provider != "unknown":
                existing.provider = item.provider
            if not existing.sender and item.sender:
                existing.sender = item.sender
            if not existing.rfc_message_id and item.rfc_message_id:
                existing.rfc_message_id = item.rfc_message_id
        else:
            db_email = Email(
                subject=item.subject,
                body=item.body,
                message_id=item.message_id,
                rfc_message_id=item.rfc_message_id,
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


def _load_existing_categories(db: Session, user_id: int) -> dict[str, str | None]:
    """Pre-load message_id -> stored category for a user, so callers can skip
    reclassifying emails that already have a stored category. "info" is a real
    classifier output (not a placeholder) so it counts as classified too --
    otherwise every Info email gets re-detected on every call, defeating the
    once-per-message idempotency guarantee."""
    return {
        row.message_id: row.category
        for row in db.query(Email.message_id, Email.category)
            .filter(Email.user_id == user_id)
            .all()
        if row.message_id
    }


def _hydrate_persisted_state(db: Session, items: list[EmailItem]) -> None:
    """After _upsert_email_items has populated item.db_id, copy each row's
    persisted is_done/is_read/status onto the response item. Without this,
    /emails and /emails/feed silently reset those badges/actions to their
    defaults on every refresh -- only /emails/cached applied them."""
    ids = [it.db_id for it in items if it.db_id]
    if not ids:
        return
    rows = db.query(Email.id, Email.is_done, Email.is_read, Email.status).filter(Email.id.in_(ids)).all()
    by_id = {row.id: row for row in rows}
    for it in items:
        row = by_id.get(it.db_id) if it.db_id else None
        if row:
            it.is_done = row.is_done
            it.is_read = row.is_read
            it.status = row.status


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
            rfc_message_id=r.get("rfc_message_id"),
            sender=r.get("sender"),
            date=r.get("date"),
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
    Emails that already have a stored category are not reclassified — only
    uncategorized/new ones run through NLP detection (mirrors /emails/feed).
    """
    items = _get_all_emails_for_user(current_user.id, max_results=max_results)
    existing_categories = _load_existing_categories(db, current_user.id)
    for it in items:
        it.category = existing_categories.get(it.message_id)

    uncategorized = [(i, it) for i, it in enumerate(items) if not it.category]
    if uncategorized:
        with ThreadPoolExecutor(max_workers=min(8, len(uncategorized))) as executor:
            futures = {
                executor.submit(
                    categorize_email,
                    DetectionEmailInput(subject=it.subject, body=it.body, sender=it.sender or ""),
                ): i
                for i, it in uncategorized
            }
            for future in _as_completed(futures):
                items[futures[future]].category = future.result()
    _upsert_email_items(db, current_user.id, items)
    _hydrate_persisted_state(db, items)
    return items


@router.post("/emails/fetch-and-detect", response_model=FetchAndDetectResponse)
def post_fetch_and_detect(
    max_results: int | None = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> FetchAndDetectResponse:
    """
    Fetch recent emails (Gmail + Outlook) and run NLP detection on each.
    Returns HTTP 404 if no email provider is connected.
    Emails that already have a stored category skip NLP detection — a cheap
    placeholder ExtractionResult derived from the stored category is returned
    instead (mirrors /emails/feed's existing-category skip).
    """
    email_items = _get_all_emails_for_user(current_user.id, max_results=max_results)
    existing_categories = _load_existing_categories(db, current_user.id)

    to_detect = [e for e in email_items if not existing_categories.get(e.message_id)]
    email_inputs = [
        DetectionEmailInput(
            subject=e.subject,
            body=e.body,
            message_id=e.message_id or "",
        )
        for e in to_detect
    ]
    detected = iter(detect_batch(email_inputs))

    extractions: list[ExtractionResult] = []
    for item in email_items:
        cached_category = existing_categories.get(item.message_id)
        if cached_category:
            item.category = cached_category
            extractions.append(ExtractionResult(
                classification=_CATEGORY_TO_CLASSIFICATION.get(cached_category, "other"),
                confidence=1.0,
            ))
        else:
            extractions.append(next(detected))

    return FetchAndDetectResponse(emails=email_items, extractions=extractions)


class FetchDetectPredictBody(BaseModel):
    """Optional body for fetch-detect-predict (preferences and calendar for prediction step)."""
    preferences: UserPreferences | None = None
    calendar: CalendarAvailability | None = None


@router.post("/emails/fetch-detect-predict", response_model=FetchDetectPredictResponse)
async def post_fetch_detect_predict(
    max_results: int | None = None,
    body: FetchDetectPredictBody | None = Body(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> FetchDetectPredictResponse:
    """
    Fetch emails (Gmail + Outlook), run detection + async enrichment, then prediction.
    Returns HTTP 404 if no email provider is connected.
    Emails that already have a stored category skip NLP detection (mirrors
    /emails/feed's existing-category skip) — only new/uncategorized emails
    run through the detect_batch pipeline.
    """
    import asyncio

    from app.nlp.extractor import classification_to_category

    email_items = await asyncio.to_thread(
        _get_all_emails_for_user, current_user.id, max_results
    )
    existing_categories = _load_existing_categories(db, current_user.id)

    to_detect = [e for e in email_items if not existing_categories.get(e.message_id)]
    email_inputs = [
        DetectionEmailInput(
            subject=e.subject,
            body=e.body,
            message_id=e.message_id or "",
            sender=e.sender or "",
        )
        for e in to_detect
    ]

    # Sync phase: regex + spaCy + sync LLM meeting-metadata enhance (new emails only)
    detected = iter(await asyncio.to_thread(detect_batch, email_inputs))
    extractions = [
        ExtractionResult(
            classification=_CATEGORY_TO_CLASSIFICATION.get(existing_categories[e.message_id], "other"),
            confidence=1.0,
        )
        if existing_categories.get(e.message_id)
        else next(detected)
        for e in email_items
    ]

    # Async enrichment: LLM category for ambiguous emails + auto-reply drafts
    await enrich_batch(email_items, extractions)

    # Propagate enriched classifications back to EmailItem.category
    for item, ext in zip(email_items, extractions):
        item.category = classification_to_category(ext.classification)

    extraction = extractions[0] if extractions else ExtractionResult()
    prefs = body.preferences if body else None
    cal = body.calendar if body else None
    suggested_slots = get_suggested_slots(extraction, preferences=prefs, calendar=cal)

    await asyncio.to_thread(_upsert_email_items, db, current_user.id, email_items)

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


@router.get("/emails/counts")
def get_email_counts(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return per-category email counts for tab badges."""
    rows = (
        db.query(Email.category, _func.count(Email.id))
        .filter(Email.user_id == current_user.id)
        .group_by(Email.category)
        .all()
    )
    valid = {"rdv", "action", "attente", "bonsplans", "info"}
    counts: dict[str, int] = {}
    for cat, n in rows:
        key = cat if cat in valid else "info"
        counts[key] = counts.get(key, 0) + n
    return {"counts": counts, "total": sum(counts.values())}


@router.get("/emails/cached", response_model=EmailFeedResponse)
def get_cached_emails(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    category: str | None = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> EmailFeedResponse:
    """
    Return emails already stored in the DB for this user — no external API calls.
    Used for instant first-paint before the background /emails/feed refresh completes.
    Optionally filter by category (for per-tab server-side filtering).
    """
    query = db.query(Email).filter(Email.user_id == current_user.id)
    if category:
        query = query.filter(Email.category == category)
    rows = (
        query
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
            rfc_message_id=row.rfc_message_id,
            sender=row.sender,
            db_id=row.id,
            category=row.category or "info",
            date=row.email_date,
            provider=row.provider or "unknown",
            is_done=row.is_done,
            is_read=row.is_read,
            status=row.status,
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
    # Pre-fetch known message IDs + stored categories to skip NLP for already-categorised emails.
    existing_categories = _load_existing_categories(db, current_user.id)
    gmail_emails: list[EmailItem] = []
    gmail_next_cursor: str | None = None

    svc = GmailService()
    try:
        gmail_ok = svc.authenticate_for_user(current_user.id)
    except Exception as exc:
        logger.warning("Gmail auth failed for user %d: %s", current_user.id, exc)
        gmail_ok = False
    if gmail_ok:
        raw_list, gmail_next_cursor = svc.fetch_email_page(page_token=gmail_cursor, limit=limit)
        gmail_emails = [
            EmailItem(
                subject=r["subject"],
                body=r["body"],
                message_id=r["message_id"],
                rfc_message_id=r.get("rfc_message_id"),
                sender=r.get("sender"),
                date=r.get("date"),
                category=existing_categories.get(r.get("message_id")),
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
            for it in outlook_page:
                it.category = existing_categories.get(it.message_id)
            outlook_emails = outlook_page
            if outlook_has_more:
                outlook_next_skip = outlook_skip + len(outlook_emails)
        except Exception as exc:
            logger.warning("Outlook feed fetch failed for user %d: %s", current_user.id, exc)

    all_emails = gmail_emails + outlook_emails
    all_emails.sort(key=lambda e: _sort_key(e.date), reverse=True)

    uncategorized = [(i, it) for i, it in enumerate(all_emails) if not it.category]
    if uncategorized:
        with ThreadPoolExecutor(max_workers=min(8, len(uncategorized))) as executor:
            futures = {
                executor.submit(categorize_email, DetectionEmailInput(subject=it.subject, body=it.body)): i
                for i, it in uncategorized
            }
            for future in _as_completed(futures):
                idx = futures[future]
                try:
                    all_emails[idx].category = future.result()
                except Exception as exc:
                    logger.warning("categorize_email failed for email %d: %s", idx, exc)
                    all_emails[idx].category = "info"

    has_more = (gmail_next_cursor is not None) or outlook_has_more

    _upsert_email_items(db, current_user.id, all_emails)
    _hydrate_persisted_state(db, all_emails)

    return EmailFeedResponse(
        emails=all_emails,
        has_more=has_more,
        gmail_next_cursor=gmail_next_cursor,
        outlook_next_skip=outlook_next_skip,
    )


def sync_user_emails_background(user_id: int) -> None:
    """Fetch new/changed emails from all connected providers and persist them.
    Called as a FastAPI BackgroundTask after OAuth so the DB is populated before
    the frontend's next /emails/cached or /emails/feed poll.

    This is the sync entry point wired to every login. Two things keep it cheap
    on repeat logins:
    - A persisted SyncState cursor (Gmail historyId / Outlook @odata.deltaLink)
      means repeat calls fetch only new/changed mail instead of re-listing the
      whole mailbox.
    - Emails that already have a stored category are never reclassified — only
      genuinely new message_ids run through categorize_email.
    """
    from app.db.database import SessionLocal  # local import — runs in background thread
    from app.models.sync_state import SyncState
    db = SessionLocal()
    try:
        existing_categories = _load_existing_categories(db, user_id)
        items: list[EmailItem] = []

        # --- Gmail ---
        svc = GmailService()
        if svc.authenticate_for_user(user_id):
            try:
                gmail_sync = (
                    db.query(SyncState)
                    .filter(SyncState.user_id == user_id, SyncState.provider == "gmail")
                    .first()
                )
                raw_list: list[dict] = []
                next_cursor: str | None = None
                if gmail_sync and gmail_sync.cursor:
                    try:
                        raw_list, next_cursor = svc.fetch_history_since(gmail_sync.cursor, limit=50)
                    except Exception:
                        logger.warning(
                            "Gmail history sync stale/failed for user_id=%d, falling back to full fetch",
                            user_id,
                        )
                        gmail_sync = None  # force full-fetch fallback below

                if not gmail_sync or not gmail_sync.cursor:
                    raw_list, _next_page_token = svc.fetch_email_page(page_token=None, limit=50)
                    next_cursor = svc.get_history_id()

                for r in raw_list:
                    category = existing_categories.get(r["message_id"])
                    if category is None:
                        category = categorize_email(DetectionEmailInput(subject=r["subject"], body=r["body"]))
                    items.append(EmailItem(
                        subject=r["subject"],
                        body=r["body"],
                        message_id=r["message_id"],
                        rfc_message_id=r.get("rfc_message_id"),
                        sender=r.get("sender"),
                        date=r.get("date"),
                        category=category,
                        provider="gmail",
                    ))
                logger.info("Background sync: fetched %d Gmail emails for user_id=%d", len(raw_list), user_id)

                if next_cursor:
                    if gmail_sync:
                        gmail_sync.cursor = next_cursor
                    else:
                        db.add(SyncState(user_id=user_id, provider="gmail", cursor=next_cursor))
            except Exception:
                logger.exception("Background Gmail sync failed for user_id=%d", user_id)

        # --- Outlook ---
        if is_outlook_connected(user_id):
            try:
                outlook_sync = (
                    db.query(SyncState)
                    .filter(SyncState.user_id == user_id, SyncState.provider == "outlook")
                    .first()
                )
                delta_link = outlook_sync.cursor if outlook_sync else None
                outlook_page, new_delta_link = fetch_outlook_delta(user_id, delta_link=delta_link, limit=50)

                for it in outlook_page:
                    category = existing_categories.get(it.message_id)
                    if category is None:
                        category = categorize_email(DetectionEmailInput(subject=it.subject, body=it.body))
                    it.category = category
                items.extend(outlook_page)
                logger.info("Background sync: fetched %d Outlook emails for user_id=%d", len(outlook_page), user_id)

                if new_delta_link:
                    if outlook_sync:
                        outlook_sync.cursor = new_delta_link
                    else:
                        db.add(SyncState(user_id=user_id, provider="outlook", cursor=new_delta_link))
            except Exception:
                logger.exception("Background Outlook sync failed for user_id=%d", user_id)

        if items:
            _upsert_email_items(db, user_id, items)
        else:
            db.commit()  # persist any SyncState cursor updates even if no new mail
    except Exception:
        logger.exception("Background email sync failed for user_id=%d", user_id)
    finally:
        db.close()


@router.get("/emails/body/{message_id}")
def get_email_body(
    message_id: str,
    provider: str = "gmail",
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict:
    """Fetch the full body of a single email. Used when opening a Gmail email from the feed.

    Opening an "Info" email is its natural terminal-state signal — the first time this
    endpoint is called for a given "Info" message, mark the stored Email row as done.
    Other categories have their own dedicated terminal action (confirm/dismiss,
    mark-done) and must not be silently marked done just by being opened.
    """
    if provider == "gmail":
        svc = GmailService()
        if not svc.authenticate_for_user(current_user.id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gmail not connected")
        body = svc.fetch_email_body(message_id)

        record = (
            db.query(Email)
            .filter(Email.user_id == current_user.id, Email.message_id == message_id)
            .first()
        )
        if record and record.category == "info" and not record.is_done:
            record.is_done = True
            db.commit()

        return {"body": body}
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown provider")


@router.post("/emails/{email_id}/mark-done")
def mark_email_done(
    email_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict:
    """Generic terminal-state endpoint for categories with no other natural
    "done" signal (Action / En attente / Bons plans)."""
    record = (
        db.query(Email)
        .filter(Email.id == email_id, Email.user_id == current_user.id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found")
    if record.category not in ("action", "attente", "bonsplans"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mark-done only applies to action, attente, or bonsplans categories",
        )

    record.is_done = True
    db.commit()

    return {"status": "done", "email_id": email_id}


@router.post("/emails/{email_id}/mark-read")
def mark_email_read(
    email_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict:
    """Mark an email as opened/read — persisted so the "Lu" badge (and per-category
    action state, via is_done) survive logout/login, unlike the old local-only
    frontend state.

    For "Info" category emails, opening is also the natural terminal-state signal
    (see get_email_body's Gmail-only equivalent above) — setting it here too makes
    that work uniformly for every provider, not just Gmail.
    """
    record = (
        db.query(Email)
        .filter(Email.id == email_id, Email.user_id == current_user.id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found")

    record.is_read = True
    # Only a *stored* "info" category counts — an unclassified email (category is
    # still None, detection hasn't run yet) must not be marked done just because
    # it happens to fall back to the "info" tab display-wise.
    if record.category == "info":
        record.is_done = True
    db.commit()

    return {"status": "read", "email_id": email_id, "is_done": record.is_done}


class _ReminderProviderResult(BaseModel):
    provider: str
    task_id: str | None = None
    error: str | None = None


class _ReminderResponse(BaseModel):
    status: str
    email_id: int
    providers: list[_ReminderProviderResult]


@router.post(
    "/emails/{email_id}/remind",
    response_model=_ReminderResponse,
    summary="Create a reminder task from an email",
)
def remind_email(
    email_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> _ReminderResponse:
    """Create a task reminder in every task service connected by the user.

    A reminder is a task rather than a calendar event because an email in
    the "En attente" category does not necessarily contain a reliable date.
    """
    record = (
        db.query(Email)
        .filter(Email.id == email_id, Email.user_id == current_user.id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found")
    if record.category != "attente":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reminders only apply to emails in the attente category",
        )

    providers = list(current_user.calendar_providers or [])
    if not providers and current_user.calendar_provider:
        providers = [current_user.calendar_provider]
    if not providers and current_user.gmail_oauth_token:
        providers = ["google"]
    if not providers and current_user.outlook_oauth_token:
        providers = ["outlook"]
    providers = [p for p in dict.fromkeys(providers) if p in {"google", "outlook"}]
    if not providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aucun service de tâches connecté. Connectez Google ou Outlook avant de créer un rappel.",
        )

    title = record.subject or "Rappel depuis un email"
    notes = record.body or ""
    results: list[_ReminderProviderResult] = []
    for provider in providers:
        result = _ReminderProviderResult(provider=provider)
        try:
            if provider == "google":
                result.task_id = create_google_task(current_user.id, title=title, notes=notes)
            else:
                result.task_id = create_outlook_task(current_user.id, title=title, notes=notes)
        except Exception as exc:
            result.error = "Impossible de créer le rappel avec ce service"
            logger.warning(
                "Reminder creation failed for provider=%s user=%s: %s",
                provider,
                current_user.id,
                exc,
            )
        results.append(result)

    if not any(result.task_id for result in results):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Le rappel n’a pas pu être créé auprès des services connectés. Vérifiez leur connexion puis réessayez.",
        )

    record.is_done = True
    db.commit()
    return _ReminderResponse(status="reminded", email_id=email_id, providers=results)


class _SummarizeRequest(BaseModel):
    subject: str = ""
    body: str = ""


class _SummarizeResponse(BaseModel):
    summary: str


@router.post("/emails/summarize", response_model=_SummarizeResponse)
async def summarize_email(
    req: _SummarizeRequest,
    _: User = Depends(get_current_active_user),
) -> _SummarizeResponse:
    """Generate a 2–3 sentence AI summary of an email.

    Detects the email language and writes the summary in that language.
    Requires OPENAI_API_KEY to be configured; returns an empty summary otherwise.
    """
    from app.services.openai_service import generate_summary
    summary = await generate_summary(req.subject, req.body)
    return _SummarizeResponse(summary=summary)


class _PlanRequest(BaseModel):
    subject: str = ""
    body: str = ""


class _PlanResponse(BaseModel):
    steps: list[str]


@router.post("/emails/plan", response_model=_PlanResponse)
async def plan_email_actions(
    req: _PlanRequest,
    _: User = Depends(get_current_active_user),
) -> _PlanResponse:
    """Generate a short list of suggested next steps for an 'action' category email.

    Detects the email language and writes the steps in that language.
    Requires OPENAI_API_KEY to be configured; returns an empty list otherwise.
    """
    from app.services.openai_service import generate_action_steps
    steps = await generate_action_steps(req.subject, req.body)
    return _PlanResponse(steps=steps)


@router.post("/emails/reply/{email_id}")
async def send_email_reply(
    email_id: int,
    reply_text: str = Form(...),
    attachments: list[UploadFile] = File(default=[]),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    Send a reply to an email via Resend.

    Accepts multipart/form-data with reply_text (required) and optional file attachments.
    Sets In-Reply-To and References headers from the stored rfc_message_id so the reply
    threads correctly in the recipient's mail client.
    """
    from app.services.resend_service import ReplyRequest, send_reply

    record = db.query(Email).filter(
        Email.id == email_id, Email.user_id == current_user.id
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Email not found")
    if not record.sender:
        raise HTTPException(status_code=400, detail="Original sender address unknown")

    addr_match = _re.search(r"<([^>]+)>", record.sender)
    to_address = addr_match.group(1) if addr_match else record.sender

    attachment_tuples: list[tuple[str, bytes]] = [
        (u.filename or "attachment", await u.read()) for u in attachments
    ]

    try:
        sent_id = send_reply(ReplyRequest(
            to=to_address,
            subject=record.subject or "",
            text=reply_text,
            rfc_message_id=record.rfc_message_id,
            attachments=attachment_tuples,
        ))
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Resend error for email_id=%d", email_id)
        raise HTTPException(status_code=502, detail=f"Email delivery failed: {exc}")

    return {"status": "sent", "resend_id": sent_id}
