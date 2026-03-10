from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

# données venant l'api de détection
class DetectionData(BaseModel):
    intent: str
    entity_time: Optional[str] = None
    duration_minutes: int = 30
    participants: List[str] = []
    context_user_id: str


# créneau
class RecommendedSlot(BaseModel):
    start_time: datetime
    end_time: datetime
    score: float
    label: str

# le renvoie finale
class PredictionResponse(BaseModel):
    suggested_slots: List[RecommendedSlot]
    status: str = "READY_TO_SCHEDULE"
    message: Optional[str] = None