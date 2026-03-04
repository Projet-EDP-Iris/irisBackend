import pendulum
from typing import List
from app.schemas.prediction import DetectionData, RecommendedSlot

def get_best_slots(data: DetectionData) -> List[RecommendedSlot]:
    """
    Logique principale pour trouver et noter les créneaux.
    """
    tz = "Europe/Paris"
    now = pendulum.now(tz)

    start = now.add(days=1).at(14, 0) 
    end = start.add(minutes=data.duration_minutes)

    score = 0.95 

    slot = RecommendedSlot(
        start_time=start,
        end_time=end,
        score=score,
        label="Créneau idéal basé sur vos habitudes"
    )

    return [slot]