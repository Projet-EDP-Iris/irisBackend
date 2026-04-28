"""
One-click calendar confirm endpoint.

POST /api/v1/calendar/confirm/{email_id}

What happens in one call:
  1. Read the chosen predicted slot from the Email record
  2. Loop over ALL of the user's connected calendar providers (Google, Apple, Outlook)
     — partial failures are logged but don't abort the whole request
  3. Create a task reminder in each connected task service (Google Tasks, Outlook Tasks)
  4. Auto-prepare a reply email (stored in Email.generated_suggestion)
  5. Persist all event IDs and mark Email.status = "confirmed"
  6. Return a summary of everything that was created
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.db.database import get_db
from app.models.email import Email
from app.models.user import User
from app.services.apple_calendar_service import create_apple_calendar_event
from app.services.google_calendar_service import create_google_calendar_event
from app.services.google_tasks_service import create_google_task
from app.services.outlook_calendar_service import create_outlook_calendar_event
from app.services.outlook_tasks_service import create_outlook_task
from app.services.suggestion_service import generate_email_suggestion

logger = logging.getLogger(__name__)

router = APIRouter(tags=["calendar"])


class ConfirmCalendarRequest(BaseModel):
    slot_index: int = 0
    # Index into Email.predicted_slots[]. 0 = best/first slot.
    provider: str | None = None
    # Deprecated — kept for backwards compatibility. Ignored when the user has
    # calendar_providers configured. If calendar_providers is empty, falls back
    # to this single provider value.
    timezone: str = "UTC"
    # IANA timezone name from the user's browser (e.g. "Europe/Paris"). Used when
    # creating calendar events so times are correct in the user's local calendar.


class ProviderResult(BaseModel):
    provider: str
    event_id: str | None = None
    task_id: str | None = None
    error: str | None = None


class ConfirmCalendarResponse(BaseModel):
    status: str
    slot: dict
    providers: list[ProviderResult]
    calendar_event_ids: dict
    prepared_reply: str | None = None


@router.post(
    "/calendar/confirm/{email_id}",
    response_model=ConfirmCalendarResponse,
    summary="One-click: confirm a slot and sync to all connected calendars",
)
def confirm_and_add_to_calendar(
    email_id: int,
    body: ConfirmCalendarRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ConfirmCalendarResponse:
    """
    Confirms a predicted meeting slot and:
    - Creates the event in ALL connected calendars (Google, Apple, Outlook)
    - Creates a task reminder in Google Tasks and/or Microsoft To Do
    - Prepares a reply email draft
    - Marks the email as confirmed in the database

    Partial failures (e.g. one provider is down) are reported in the response
    but don't prevent the other providers from being processed.
    """
    # 1. Load the email record
    email_record = (
        db.query(Email)
        .filter(Email.id == email_id, Email.user_id == current_user.id)
        .first()
    )
    if not email_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found")

    if not email_record.predicted_slots:
        # Run detection + prediction on-demand so confirm works without prior fetch-detect-predict
        from app.services.detection import detect_single  # noqa: PLC0415
        from app.services.prediction_service import get_suggested_slots  # noqa: PLC0415
        from app.schemas.detection import EmailInput  # noqa: PLC0415

        ext = detect_single(EmailInput(
            subject=email_record.subject or "",
            body=email_record.body or "",
        ))
        slots = get_suggested_slots(ext)
        if slots:
            email_record.predicted_slots = [s.model_dump(mode="json") for s in slots]
            db.flush()

    if not email_record.predicted_slots:
        # Last-resort fallback: tomorrow at 10:00 UTC for 1 hour
        t = (
            datetime.now(timezone.utc)
            .replace(hour=10, minute=0, second=0, microsecond=0)
            + timedelta(days=1)
        )
        email_record.predicted_slots = [{
            "start_time": t.isoformat(),
            "end_time": (t + timedelta(hours=1)).isoformat(),
            "score": 0.5,
            "label": "default",
        }]
        db.flush()

    # 2. Pick the requested slot
    slots: list[dict] = email_record.predicted_slots
    if body.slot_index >= len(slots):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"slot_index {body.slot_index} is out of range — only {len(slots)} slot(s) available.",
        )
    chosen_slot = slots[body.slot_index]
    start = datetime.fromisoformat(chosen_slot["start_time"])
    end = datetime.fromisoformat(chosen_slot["end_time"])

    # 3. Determine providers to use
    providers: list[str] = list(current_user.calendar_providers or [])
    if not providers:
        # Backwards compatibility: fall back to legacy single provider
        single = body.provider or current_user.calendar_provider
        if not single:
            # Auto-detect: if a Google OAuth token exists for this user the Gmail
            # OAuth already includes the calendar scope, so register Google now
            # rather than forcing the user through a separate setup step.
            from app.services.gmail_service import get_token_path_for_user  # noqa: PLC0415
            import os  # noqa: PLC0415
            if os.path.exists(get_token_path_for_user(current_user.id)):
                single = "google"
                current_user.calendar_providers = ["google"]
                current_user.calendar_provider = "google"
                db.flush()
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "No calendar provider configured. "
                        "Call PATCH /api/v1/user/users/me/calendar-setup first."
                    ),
                )
        providers = [single]

    # 4. Extract event metadata from detection results
    extraction: dict = email_record.extraction_data or {}
    attendees: list[str] = extraction.get("participants", [])
    subject: str = email_record.subject or "Meeting"
    description = f"Scheduled by Iris from email: {subject}"

    # 5. Loop over all providers — collect results, don't abort on partial failure
    provider_results: list[ProviderResult] = []
    event_ids: dict = dict(email_record.calendar_event_ids or {})

    for provider in providers:
        result = ProviderResult(provider=provider)

        # --- Calendar event ---
        try:
            if provider == "google":
                result.event_id = create_google_calendar_event(
                    user_id=current_user.id,
                    summary=subject,
                    start_time=start,
                    end_time=end,
                    attendees=attendees,
                    description=description,
                    timezone=body.timezone,
                )
            elif provider == "apple":
                if not current_user.apple_caldav_user or not current_user.apple_caldav_password:
                    raise ValueError("Apple credentials not configured — call /me/calendar-setup with provider='apple'")
                result.event_id = create_apple_calendar_event(
                    apple_user=current_user.apple_caldav_user,
                    encrypted_password=current_user.apple_caldav_password,
                    summary=subject,
                    start_time=start,
                    end_time=end,
                    description=description,
                    timezone=body.timezone,
                )
            elif provider == "outlook":
                result.event_id = create_outlook_calendar_event(
                    user_id=current_user.id,
                    summary=subject,
                    start_time=start,
                    end_time=end,
                    attendees=attendees,
                    description=description,
                    timezone=body.timezone,
                )
            if result.event_id:
                event_ids[provider] = result.event_id
        except Exception as exc:
            logger.warning("Calendar creation failed for provider=%s: %s", provider, exc)
            result.error = str(exc)

        # --- Task reminder (best-effort, never blocks) ---
        try:
            task_title = f"Follow up: {subject}"
            if provider == "google" and result.event_id:
                result.task_id = create_google_task(
                    user_id=current_user.id,
                    title=task_title,
                    due=start,
                    notes=description,
                )
            elif provider == "outlook" and result.event_id:
                result.task_id = create_outlook_task(
                    user_id=current_user.id,
                    title=task_title,
                    due=start,
                    notes=description,
                )
        except Exception as exc:
            logger.warning("Task creation failed for provider=%s: %s", provider, exc)
            # Don't set result.error — a missing task is not a critical failure

        provider_results.append(result)

    # Check if ALL calendar providers failed — if so, raise an explicit error
    # (instead of returning 200 silently with all errors inside providers[])
    calendar_successes = [r for r in provider_results if r.event_id and not r.error]
    if providers and not calendar_successes:
        errors = "; ".join(r.error or "unknown error" for r in provider_results)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Échec de création du RDV dans le calendrier : {errors}",
        )

    # 6. Auto-prepare a reply email
    prepared_reply: str | None = None
    try:
        prepared_reply = generate_email_suggestion(
            email_content=email_record.body or subject,
            slots=[chosen_slot],
        )
        email_record.generated_suggestion = prepared_reply
    except Exception as exc:
        logger.warning("Suggestion generation failed: %s", exc)

    # 7. Persist results
    email_record.calendar_event_ids = event_ids
    # Keep legacy field pointing to the first successful event
    if event_ids and not email_record.calendar_event_id:
        email_record.calendar_event_id = next(iter(event_ids.values()))
    email_record.status = "confirmed"
    db.commit()

    return ConfirmCalendarResponse(
        status="confirmed",
        slot=chosen_slot,
        providers=provider_results,
        calendar_event_ids=event_ids,
        prepared_reply=prepared_reply,
    )
