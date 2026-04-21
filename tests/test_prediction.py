from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

def test_predict_slots():
    payload = {
        "extraction": {"duration_minutes": 30, "classification": "meeting_schedule"}
    }
    response = client.post("/api/v1/predict/slots/from-detection", json=payload)
    assert response.status_code == 200
    assert "suggested_slots" in response.json()
