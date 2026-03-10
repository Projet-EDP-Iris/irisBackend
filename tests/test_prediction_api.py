from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

ENDPOINT = "/api/v1/predict/slots/from-detection"


def test_predict_from_detection_status_code():
    """POST with a valid payload returns HTTP 200."""
    payload = {"results": [{"classification": "meeting", "duration_minutes": 30}]}
    response = client.post(ENDPOINT, json=payload)
    assert response.status_code == 200


def test_predict_from_detection_response_schema():
    """Response contains 'suggested_slots' list and 'status' string."""
    payload = {"results": [{"classification": "meeting", "duration_minutes": 30}]}
    response = client.post(ENDPOINT, json=payload)
    data = response.json()

    assert "suggested_slots" in data
    assert "status" in data
    assert isinstance(data["suggested_slots"], list)
    assert isinstance(data["status"], str)
    assert data["status"] == "READY_TO_SCHEDULE"


def test_predict_from_detection_returns_three_slots():
    """Endpoint always returns exactly 3 suggested slots."""
    payload = {"results": [{"classification": "review", "duration_minutes": 60}]}
    response = client.post(ENDPOINT, json=payload)
    slots = response.json()["suggested_slots"]
    assert len(slots) == 3


def test_predict_from_detection_slot_schema():
    """Each slot has the required keys with correct types."""
    payload = {"results": [{"classification": "standup", "duration_minutes": 15}]}
    response = client.post(ENDPOINT, json=payload)
    slots = response.json()["suggested_slots"]

    for slot in slots:
        assert "start_time" in slot
        assert "end_time" in slot
        assert "score" in slot
        assert "label" in slot
        assert isinstance(slot["score"], float)
        assert isinstance(slot["label"], str)


def test_predict_from_detection_datetime_serialization():
    """start_time and end_time are serialized as valid ISO-8601 datetime strings."""
    payload = {"results": [{"classification": "sync", "duration_minutes": 45}]}
    response = client.post(ENDPOINT, json=payload)
    slots = response.json()["suggested_slots"]

    for slot in slots:
        # fromisoformat raises ValueError if the string is not a valid datetime
        start = datetime.fromisoformat(slot["start_time"])
        end = datetime.fromisoformat(slot["end_time"])
        assert end > start


def test_predict_from_detection_duration_applied():
    """end_time - start_time equals the requested duration_minutes."""
    duration = 45
    payload = {"results": [{"classification": "meeting", "duration_minutes": duration}]}
    response = client.post(ENDPOINT, json=payload)
    slots = response.json()["suggested_slots"]

    for slot in slots:
        start = datetime.fromisoformat(slot["start_time"])
        end = datetime.fromisoformat(slot["end_time"])
        diff_minutes = (end - start).total_seconds() / 60
        assert diff_minutes == duration


def test_predict_from_detection_label_contains_intent():
    """Each slot label mentions the intent from the request."""
    intent = "retrospective"
    payload = {"results": [{"classification": intent, "duration_minutes": 60}]}
    response = client.post(ENDPOINT, json=payload)
    slots = response.json()["suggested_slots"]

    for slot in slots:
        assert intent in slot["label"]


def test_predict_from_detection_score_value():
    """Each slot has a score of 0.9."""
    payload = {"results": [{"classification": "meeting", "duration_minutes": 30}]}
    response = client.post(ENDPOINT, json=payload)
    slots = response.json()["suggested_slots"]

    for slot in slots:
        assert slot["score"] == pytest.approx(0.9)


def test_predict_from_detection_empty_results_uses_defaults():
    """When 'results' is an empty list, defaults (30 min, 'meeting') are used."""
    response = client.post(ENDPOINT, json={"results": []})
    assert response.status_code == 200
    data = response.json()
    slots = data["suggested_slots"]
    assert len(slots) == 3

    for slot in slots:
        start = datetime.fromisoformat(slot["start_time"])
        end = datetime.fromisoformat(slot["end_time"])
        diff_minutes = (end - start).total_seconds() / 60
        assert diff_minutes == 30
        assert "meeting" in slot["label"]


def test_predict_from_detection_missing_results_key_uses_defaults():
    """When the payload has no 'results' key, defaults are applied."""
    response = client.post(ENDPOINT, json={})
    assert response.status_code == 200
    slots = response.json()["suggested_slots"]
    assert len(slots) == 3

    for slot in slots:
        start = datetime.fromisoformat(slot["start_time"])
        end = datetime.fromisoformat(slot["end_time"])
        diff_minutes = (end - start).total_seconds() / 60
        assert diff_minutes == 30


def test_predict_from_detection_slots_are_one_hour_apart():
    """Consecutive slots are exactly 1 hour apart (i increments by 1 hour)."""
    payload = {"results": [{"classification": "meeting", "duration_minutes": 30}]}
    response = client.post(ENDPOINT, json=payload)
    slots = response.json()["suggested_slots"]

    starts = [datetime.fromisoformat(s["start_time"]) for s in slots]
    for i in range(1, len(starts)):
        gap_minutes = (starts[i] - starts[i - 1]).total_seconds() / 60
        assert gap_minutes == 60
