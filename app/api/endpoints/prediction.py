from fastapi import APIRouter, HTTPException
import pendulum


router = APIRouter()

@router.post("/predict/slots/from-detection")
async def predict_from_detection(detection_result: dict):
    
    result = detection_result.get("results", [{}])[0]
    duration = result.get("duration_minutes", 30)
    intent = result.get("classification", "meeting")
    
    
    now = pendulum.now('Europe/Paris')
    start_base = now.add(days=1).at(9, 0) 
    
    suggestions = [
        {
            "start_time": start_base.add(hours=i),
            "end_time": start_base.add(hours=i).add(minutes=duration),
            "score": 0.9,
            "label": f"Créneau pour {intent}"
        } 
        for i in range(3)
    ]
    
    return {"suggested_slots": suggestions, "status": "READY_TO_SCHEDULE"}