from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.models.user import User
from app.services.gmail_service import GmailService
from app.db.database import get_db

router = APIRouter(prefix="/emails", tags=["emails"])
gmail_service = GmailService()

@router.get("/", response_model=List[Dict[str, Any]])
async def get_recent_emails(
    current_user: User = Depends(get_current_user),
    n: int = 10
):
    """
    GET /api/v1/emails
    Returns the 10 last emails. Error 404 if no Gmail token for the user.
    """
    service = gmail_service.authenticate_for_user(current_user.id)
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Gmail token found for this user. Please connect your Gmail account."
        )
    
    emails = gmail_service.fetch_recent_emails(service, n=n)
    return emails

@router.post("/fetch-and-detect", response_model=Dict[str, Any])
async def fetch_and_detect_emails(
    current_user: User = Depends(get_current_user),
    n: int = 5
):
    """
    POST /api/v1/emails/fetch-and-detect
    Fetches emails and performs auto-detection/NLP extraction.
    Currently returns the emails and a placeholder for extractions.
    """
    service = gmail_service.authenticate_for_user(current_user.id)
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Gmail token found for this user."
        )
    
    emails = gmail_service.fetch_recent_emails_as_inputs(service, n=n)
    
    # Placeholder for NLP processing
    # In a real scenario, this would call app.nlp.processing.analyze_emails(emails)
    extractions = []
    for email in emails:
        # Simple extraction simulation
        extractions.append({
            "message_id": email["message_id"],
            "detected_intent": "meeting" if "réunion" in email["subject"].lower() or "reunion" in email["subject"].lower() else "info",
            "entities": [] # Future: names, dates, locations
        })
        
    return {
        "status": "success",
        "emails_count": len(emails),
        "emails": emails,
        "extractions": extractions
    }
