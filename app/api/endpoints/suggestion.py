from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.email import Email
from app.schemas.suggestion import (
    InlineSuggestionRequest,
    InlineSuggestionResponse,
    SuggestionResponse,
    SuggestionVariant,
)
from app.services.openai_service import generate_mail_suggestions
from app.services.suggestion_service import generate_email_suggestion

router = APIRouter(tags=["suggestion"])


@router.post("/suggest/{email_id}", response_model=SuggestionResponse)
async def create_suggestion(
    email_id: int,
    db: Session = Depends(get_db),
) -> SuggestionResponse:
    """Lit les donnees en base et genere la reponse finale."""
    email_record = db.query(Email).filter(Email.id == email_id).first()
    if not email_record:
        raise HTTPException(status_code=404, detail="Email introuvable")
    if not email_record.predicted_slots:
        raise HTTPException(
            status_code=400,
            detail="Aucun creneau disponible. Lancez d abord la planification (/predict).",
        )
    suggested = generate_email_suggestion(
        email_record.body or email_record.subject or "",
        email_record.predicted_slots,
    )
    return SuggestionResponse(
        email_id=email_id,
        suggested_content=suggested,
        status="READY",
    )


@router.post("/suggest-inline", response_model=InlineSuggestionResponse)
async def create_inline_suggestion(
    request: InlineSuggestionRequest,
) -> InlineSuggestionResponse:
    """Genere 3 variantes de reponse email directement depuis subject + body.

    Aucune entree en base requise — ideal pour le frontend one-click.
    """
    summary = f"{request.subject}: {request.body[:300]}"
    raw_variants = await generate_mail_suggestions(summary)
    variants = [
        SuggestionVariant(label=v["label"], content=v["content"])
        for v in raw_variants
    ]
    return InlineSuggestionResponse(variants=variants, status="READY")
