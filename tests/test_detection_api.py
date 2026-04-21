import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.database import get_db
from app.main import app
from app.models import Base

TEST_DATABASE_URL = "sqlite:///./test.db"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def no_openai_calls(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)


@pytest.fixture(scope="module")
def db_override():
    prev = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    yield
    if prev is not None:
        app.dependency_overrides[get_db] = prev
    else:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client_with_db(db_override):
    return TestClient(app)


@pytest.fixture
def setup_database(client_with_db):
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def auth_headers(client_with_db, setup_database):
    client_with_db.post(
        "/api/v1/user/users/",
        json={"email": "detect@example.com", "password": "Secret12!", "role": "regular"},
    )
    login = client_with_db.post(
        "/api/v1/user/users/login",
        json={"email": "detect@example.com", "password": "Secret12!"},
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_detect_unauthorized(client_with_db, setup_database):
    for path in ["/detect", "/detect/thread", "/validate", "/feedback"]:
        if path == "/detect":
            body = {"emails": [{"subject": "x", "body": "y"}]}
        elif path == "/detect/thread":
            body = {"messages": [{"subject": "x", "body": "y"}]}
        elif path == "/validate":
            body = {"extraction": {}}
        else:
            body = {"message_id": "m1", "original_extraction": {}, "corrections": {}}
        r = client_with_db.post(path, json=body)
        assert r.status_code == 403


def test_detect_english_meeting(client_with_db, setup_database, auth_headers):
    r = client_with_db.post(
        "/detect",
        headers=auth_headers,
        json={"emails": [{"subject": "Meeting tomorrow", "body": "Can we schedule a call tomorrow at 3pm?"}]},
    )
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert len(data["results"]) == 1
    assert data["results"][0]["classification"] == "meeting_schedule"


def test_detect_french_meeting(client_with_db, setup_database, auth_headers):
    r = client_with_db.post(
        "/detect",
        headers=auth_headers,
        json={"emails": [{"subject": "Réunion", "body": "Réunion mardi prochain à 10h."}]},
    )
    assert r.status_code == 200
    assert r.json()["results"][0]["classification"] == "meeting_schedule"


def test_detect_cancellation(client_with_db, setup_database, auth_headers):
    r = client_with_db.post(
        "/detect",
        headers=auth_headers,
        json={"emails": [{"subject": "Cancelled", "body": "The meeting is cancelled."}]},
    )
    assert r.status_code == 200
    assert r.json()["results"][0]["classification"] == "meeting_cancel"


def test_detect_batch(client_with_db, setup_database, auth_headers):
    r = client_with_db.post(
        "/detect",
        headers=auth_headers,
        json={
            "emails": [
                {"subject": "Meeting", "body": "Schedule a call."},
                {"subject": "Cancel", "body": "Meeting cancelled."},
            ]
        },
    )
    assert r.status_code == 200
    assert len(r.json()["results"]) == 2


def test_detect_thread_confirmed(client_with_db, setup_database, auth_headers):
    r = client_with_db.post(
        "/detect/thread",
        headers=auth_headers,
        json={
            "messages": [
                {"subject": "Meeting", "body": "Can we meet Tuesday?"},
                {"subject": "Re: Meeting", "body": "Confirmed, see you Tuesday."},
            ]
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert "merged" in data
    assert data["merged"]["thread_status"] == "confirmed"


def test_validate_missing_timezone(client_with_db, setup_database, auth_headers):
    r = client_with_db.post(
        "/validate",
        headers=auth_headers,
        json={
            "extraction": {
                "classification": "meeting_schedule",
                "proposed_times": [],
                "timezone": None,
                "duration_minutes": None,
            }
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert "timezone" in data["missing_fields"]
    assert any("timezone" in q.lower() or "time" in q.lower() for q in data["clarifying_questions"])


def test_feedback_creates_row(client_with_db, setup_database, auth_headers):
    r = client_with_db.post(
        "/feedback",
        headers=auth_headers,
        json={
            "message_id": "msg-123",
            "original_extraction": {"classification": "meeting_schedule"},
            "corrections": {"timezone": "UTC"},
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert "feedback_id" in data
    fid = data["feedback_id"]
    db = next(override_get_db())
    try:
        from app.models.feedback import DetectionFeedback
        row = db.query(DetectionFeedback).filter(DetectionFeedback.id == fid).first()
        assert row is not None
        assert row.message_id == "msg-123"
    finally:
        db.close()
