from fastapi import APIRouter
import pendulum


router = APIRouter()

@router.post("/predict/slots/from-detection")
async def predict_from_detection(detection_result: dict):
    
    results = detection_result.get("results", [{}])
    result = results[0] if results else {}
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