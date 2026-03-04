from fastapi import APIRouter
from app.schemas.prediction import DetectionData, PredictionResponse
import pendulum

router = APIRouter()

@router.post("/predict/slots", response_model=PredictionResponse)
async def predict_slots(data: DetectionData):
    # 1. On récupère l'heure actuelle (timezone locale)
    now = pendulum.now('Europe/Paris')
    
    # 2. Logique simplifiée pour l'exemple :
    # Si "entity_time" contient "demain", on décale au jour suivant
    start_base = now.add(days=1).at(9, 0) if "demain" in (data.entity_time or "").lower() else now.add(hours=1)
    
    # 3. On génère 3 suggestions de créneaux
    suggestions = []
    for i in range(3):
        start = start_base.add(hours=i)
        end = start.add(minutes=data.duration_minutes)
        
        suggestions.append({
            "start_time": start,
            "end_time": end,
            "score": 0.95 - (i * 0.1), # Le premier est le "meilleur"
            "label": f"Option {i+1}"
        })

    return {
        "suggested_slots": suggestions,
        "status": "READY_TO_SCHEDULE",
        "message": f"J'ai trouvé {len(suggestions)} créneaux pour votre {data.intent}."
    }