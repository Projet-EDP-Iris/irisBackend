from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

ENDPOINT = "/api/v1/predict/slots/from-detection"


def test_predict_from_detection_status_code():
    """Test that the endpoint returns HTTP 200."""
    response = client.post(
        ENDPOINT,
        json={"results": [{"duration_minutes": 30, "classification": "meeting"}]},
    )
    assert response.status_code == 200


def test_predict_from_detection_response_schema():
    """Test that the response contains the expected top-level keys."""
    response = client.post(
        ENDPOINT,
        json={"results": [{"duration_minutes": 30, "classification": "meeting"}]},
    )
    data = response.json()
    assert "suggested_slots" in data
    assert "status" in data
    assert data["status"] == "READY_TO_SCHEDULE"


def test_predict_from_detection_slot_count():
    """Test that exactly 3 slot suggestions are returned."""
    response = client.post(
        ENDPOINT,
        json={"results": [{"duration_minutes": 30, "classification": "meeting"}]},
    )
    slots = response.json()["suggested_slots"]
    assert len(slots) == 3


def test_predict_from_detection_slot_schema():
    """Test that each slot contains the required fields."""
    response = client.post(
        ENDPOINT,
        json={"results": [{"duration_minutes": 30, "classification": "meeting"}]},
    )
    for slot in response.json()["suggested_slots"]:
        assert "start_time" in slot
        assert "end_time" in slot
        assert "score" in slot
        assert "label" in slot


def test_predict_from_detection_datetime_serialization():
    """Test that start_time and end_time are valid ISO 8601 datetime strings."""
    response = client.post(
        ENDPOINT,
        json={"results": [{"duration_minutes": 30, "classification": "meeting"}]},
    )
    for slot in response.json()["suggested_slots"]:
        # Should not raise ValueError if they are valid ISO datetime strings
        start = datetime.fromisoformat(slot["start_time"])
        end = datetime.fromisoformat(slot["end_time"])
        assert end > start


def test_predict_from_detection_custom_duration():
    """Test that the custom duration_minutes is reflected in slot end times."""
    duration = 60
    response = client.post(
        ENDPOINT,
        json={"results": [{"duration_minutes": duration, "classification": "meeting"}]},
    )
    for slot in response.json()["suggested_slots"]:
        start = datetime.fromisoformat(slot["start_time"])
        end = datetime.fromisoformat(slot["end_time"])
        diff_minutes = (end - start).total_seconds() / 60
        assert diff_minutes == duration


def test_predict_from_detection_custom_classification():
    """Test that the classification appears in each slot label."""
    classification = "workshop"
    response = client.post(
        ENDPOINT,
        json={"results": [{"duration_minutes": 30, "classification": classification}]},
    )
    for slot in response.json()["suggested_slots"]:
        assert classification in slot["label"]


def test_predict_from_detection_default_values():
    """Test that missing fields fall back to sensible defaults."""
    response = client.post(ENDPOINT, json={})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "READY_TO_SCHEDULE"
    assert len(data["suggested_slots"]) == 3
    # Default label uses "meeting"
    for slot in data["suggested_slots"]:
        assert "meeting" in slot["label"]


def test_predict_from_detection_slot_score():
    """Test that each slot has a score of 0.9."""
    response = client.post(
        ENDPOINT,
        json={"results": [{"duration_minutes": 30, "classification": "meeting"}]},
    )
    for slot in response.json()["suggested_slots"]:
        assert slot["score"] == 0.9
