from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import get_current_active_user
from app.models.user import User
from app.schemas.email import EmailItem, FetchAndDetectResponse
from app.services.detection import detect_batch
from app.services.gmail_service import GmailService

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
