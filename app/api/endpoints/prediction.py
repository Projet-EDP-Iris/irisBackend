from fastapi import APIRouter
import pendulum
from datetime import datetime
from enum import Enum
from typing import List

from pydantic import BaseModel


class DetectionResult(BaseModel):
    duration_minutes: int = 30
    classification: str = "meeting"


class DetectionData(BaseModel):
    results: List[DetectionResult] = []


class RecommendedSlot(BaseModel):
    start_time: datetime
    end_time: datetime
    score: float
    label: str


class PredictionStatus(str, Enum):
    READY_TO_SCHEDULE = "READY_TO_SCHEDULE"


class PredictionResponse(BaseModel):
    suggested_slots: List[RecommendedSlot]
    status: PredictionStatus


router = APIRouter()

@router.post("/predict/slots/from-detection", response_model=PredictionResponse)
async def predict_from_detection(detection_data: DetectionData):
    
    if detection_data.results:
        result = detection_data.results[0]
    else:
        result = DetectionResult()

    duration = result.duration_minutes
    intent = result.classification
    
    
    now = pendulum.now('Europe/Paris')
    start_base = now.add(days=1).at(9, 0) 
    
    suggestions = [
        RecommendedSlot(
            start_time=start_base.add(hours=i),
            end_time=start_base.add(hours=i).add(minutes=duration),
            score=0.9,
            label=f"Créneau pour {intent}",
        )
        for i in range(3)
    ]
    
    return PredictionResponse(
        suggested_slots=suggestions,
        status=PredictionStatus.READY_TO_SCHEDULE,
    )