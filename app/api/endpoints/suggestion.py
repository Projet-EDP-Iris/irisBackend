from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.email import Email
from app.schemas.suggestion import SuggestionResponse
from app.services.suggestion_service import generate_email_suggestion

router = APIRouter(tags=["suggestion"])

@router.post("/suggest/{email_id}", response_model=SuggestionResponse)
async def create_suggestion(
    email_id: int,
    db: Session = Depends(get_db)
) -> SuggestionResponse:
    """Lit les données en base et génère la réponse finale."""

    # 1. RÉCUPÉRATION
    email_record = db.query(Email).filter(Email.id == email_id).first()

    if not email_record:
        raise HTTPException(status_code=404, detail="Email introuvable")

    # On vérifie qu'on a bien des créneaux
    if not email_record.predicted_slots:
        raise HTTPException(
            status_code=400,
            detail="Aucun créneau disponible. Lancez d'abord la planification (/predict)."
        )

    # 2. GÉNÉRATION : On appelle le service OpenAI
    suggestion_text = generate_email_suggestion(
        email_content=email_record.body,
        slots=email_record.predicted_slots
    )

    # 3. SAUVEGARDE
    email_record.generated_suggestion = suggestion_text
    email_record.status = "completed"

    db.commit()
    db.refresh(email_record)

    # 4. RÉPONSE
    return SuggestionResponse(
        email_id=email_id,
        suggested_content=suggestion_text,
        status="READY"
    )
