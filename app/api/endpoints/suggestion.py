from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.email import Email  # On utilise toujours notre classe avec Majuscule
from app.schemas.suggestion import SuggestionResponse # Assure-toi que ce schéma existe
from app.services.suggestion_service import generate_email_suggestion # Ton service IA

router = APIRouter(tags=["suggestion"])

@router.post("/suggest/{email_id}", response_model=SuggestionResponse)
async def create_suggestion(
    email_id: int, 
    db: Session = Depends(get_db)
) -> SuggestionResponse:
    """Lit les données en base et génère la réponse finale."""
    
    # 1. RÉCUPÉRATION : On va chercher tout ce qu'on a stocké
    email_record = db.query(Email).filter(Email.id == email_id).first()
    
    if not email_record:
        raise HTTPException(status_code=404, detail="Email introuvable")

    # On vérifie qu'on a bien des créneaux, sinon l'IA ne peut pas proposer de date
    if not email_record.predicted_slots:
        raise HTTPException(
            status_code=400, 
            detail="Aucun créneau disponible. Lancez d'abord la planification (/predict)."
        )

    # 2. GÉNÉRATION : On appelle ton service IA (OpenAI/LLM)
    # On lui donne le contenu de l'email + les créneaux qu'on a récupérés en base
    suggestion_text = generate_email_suggestion(
        email_content=email_record.body,
        slots=email_record.predicted_slots
    )

    # 3. SAUVEGARDE : On enregistre la plume de l'IA
    email_record.generated_suggestion = suggestion_text
    email_record.status = "completed"
    
    db.commit()
    db.refresh(email_record)

    # 4. RÉPONSE : On renvoie le texte final
    return SuggestionResponse(
        email_id=email_id,
        suggested_content=suggestion_text,
        status="READY"
    )