from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

URL = "/api/v1/predict/slots/from-detection"


def _extraction_payload(
    classification: str = "meeting_schedule",
    duration_minutes: int = 30,
    timezone: str = "Europe/Paris",
    proposed_times: list | None = None,
) -> dict:
    payload: dict = {
        "classification": classification,
        "duration_minutes": duration_minutes,
        "timezone": timezone,
        "proposed_times": proposed_times or [],
    }
    return payload


def test_predict_single_extraction_returns_200_and_slots():
    body = {"extraction": _extraction_payload(duration_minutes=45)}
    r = client.post(URL, json=body)
    assert r.status_code == 200
    data = r.json()
    assert "suggested_slots" in data
    assert "status" in data
    assert data["status"] == "READY_TO_SCHEDULE"
    slots = data["suggested_slots"]
    assert isinstance(slots, list)
    assert len(slots) > 0
    for slot in slots:
        assert "start_time" in slot
        assert "end_time" in slot
        assert "score" in slot
        assert "label" in slot


def test_predict_list_extraction_uses_first():
    first = _extraction_payload(duration_minutes=60, timezone="Europe/Paris")
    second = _extraction_payload(duration_minutes=90, timezone="UTC")
    body = {"extraction": [first, second]}
    r = client.post(URL, json=body)
    assert r.status_code == 200
    data = r.json()
    slots = data["suggested_slots"]
    assert len(slots) > 0
    assert data["status"] == "READY_TO_SCHEDULE"


def test_predict_with_preferences_returns_200():
    body = {
        "extraction": _extraction_payload(),
        "preferences": {
            "working_hours": {"start": "09:00", "end": "17:00", "timezone": "Europe/Paris"},
            "preferred_duration_minutes": 45,
            "timezone": "Europe/Paris",
        },
    }
    r = client.post(URL, json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "READY_TO_SCHEDULE"
    assert len(data["suggested_slots"]) >= 0


def test_predict_with_calendar_busy_slots_returns_200():
    body = {
        "extraction": _extraction_payload(),
        "calendar": {
            "busy_slots": [
                {"start": "2026-03-11T10:00:00", "end": "2026-03-11T11:00:00", "timezone": "Europe/Paris"},
            ],
        },
    }
    r = client.post(URL, json=body)
    assert r.status_code == 200
    data = r.json()
    assert "suggested_slots" in data


def test_predict_empty_extraction_list_returns_200():
    body = {"extraction": []}
    r = client.post(URL, json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "READY_TO_SCHEDULE"
    assert "suggested_slots" in data
    assert isinstance(data["suggested_slots"], list)


def test_predict_minimal_extraction_returns_200():
    body = {"extraction": {"classification": "meeting_schedule"}}
    r = client.post(URL, json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "READY_TO_SCHEDULE"
    assert "suggested_slots" in data
