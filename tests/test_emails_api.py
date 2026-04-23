from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.database import get_db
from app.main import app
from app.models import Base
from app.schemas.detection import EmailInput

TEST_DATABASE_URL = "sqlite:///./test_emails.db"
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
        "/api/v1/users/",
        json={"email": "emails@example.com", "password": "Secret12!", "role": "regular"},
    )
    login = client_with_db.post(
        "/api/v1/users/login",
        json={"email": "emails@example.com", "password": "Secret12!"},
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_get_emails_unauthorized(client_with_db, setup_database):
    r = client_with_db.get("/api/v1/emails")
    assert r.status_code == 403


def test_get_emails_not_connected_returns_404(client_with_db, setup_database, auth_headers):
    r = client_with_db.get("/api/v1/emails", headers=auth_headers)
    assert r.status_code == 404
    assert "Gmail not connected" in r.json().get("detail", "")


@patch("app.api.endpoints.emails.GmailService")
def test_get_emails_returns_list_with_subject_body_message_id(mock_gmail, client_with_db, setup_database, auth_headers):
    mock_svc = MagicMock()
    mock_gmail.return_value = mock_svc
    mock_svc.authenticate_for_user.return_value = True
    mock_svc.fetch_recent_emails.return_value = [
        {"subject": "Test", "body": "Body text", "message_id": "msg_1", "sender": "a@b.com", "date": "1"},
    ]
    r = client_with_db.get("/api/v1/emails", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["subject"] == "Test"
    assert data[0]["body"] == "Body text"
    assert data[0]["message_id"] == "msg_1"


@patch("app.api.endpoints.emails.get_token_path_for_user")
@patch("app.api.endpoints.emails.GmailService")
def test_get_emails_invalid_stored_connection_returns_503(
    mock_gmail, mock_token_path, client_with_db, setup_database, auth_headers, tmp_path
):
    token_file = tmp_path / "gmail_user_1.json"
    token_file.write_text('{"gmail_email":"broken@example.com"}')
    mock_token_path.return_value = str(token_file)
    mock_svc = MagicMock()
    mock_svc.authenticate_for_user.return_value = False
    mock_gmail.return_value = mock_svc

    r = client_with_db.get("/api/v1/emails", headers=auth_headers)

    assert r.status_code == 503
    assert "Please reconnect Gmail" in r.json().get("detail", "")


def test_fetch_and_detect_unauthorized(client_with_db, setup_database):
    r = client_with_db.post("/api/v1/emails/fetch-and-detect")
    assert r.status_code == 403


def test_fetch_and_detect_not_connected_returns_404(client_with_db, setup_database, auth_headers):
    r = client_with_db.post("/api/v1/emails/fetch-and-detect", headers=auth_headers)
    assert r.status_code == 404


@patch("app.api.endpoints.emails.GmailService")
def test_fetch_and_detect_returns_emails_and_extractions(mock_gmail, client_with_db, setup_database, auth_headers):
    mock_svc = MagicMock()
    mock_gmail.return_value = mock_svc
    mock_svc.authenticate_for_user.return_value = True
    mock_svc.fetch_recent_emails_as_inputs.return_value = [
        EmailInput(subject="Meeting", body="Can we meet tomorrow at 3pm?", message_id="m1"),
    ]
    r = client_with_db.post("/api/v1/emails/fetch-and-detect", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "emails" in data
    assert "extractions" in data
    assert len(data["emails"]) == 1
    assert len(data["extractions"]) == 1
    assert data["emails"][0]["subject"] == "Meeting"
    assert data["emails"][0]["message_id"] == "m1"
    ext = data["extractions"][0]
    assert "classification" in ext
    assert ext["classification"] == "meeting_schedule"


def test_fetch_detect_predict_unauthorized(client_with_db, setup_database):
    r = client_with_db.post("/api/v1/emails/fetch-detect-predict")
    assert r.status_code == 403


def test_fetch_detect_predict_not_connected_returns_404(client_with_db, setup_database, auth_headers):
    r = client_with_db.post("/api/v1/emails/fetch-detect-predict", headers=auth_headers)
    assert r.status_code == 404


@patch("app.api.endpoints.emails.GmailService")
def test_fetch_detect_predict_returns_emails_extractions_and_suggested_slots(
    mock_gmail, client_with_db, setup_database, auth_headers
):
    mock_svc = MagicMock()
    mock_gmail.return_value = mock_svc
    mock_svc.authenticate_for_user.return_value = True
    mock_svc.fetch_recent_emails_as_inputs.return_value = [
        EmailInput(subject="Meeting", body="Can we meet tomorrow at 3pm?", message_id="m1"),
    ]
    r = client_with_db.post("/api/v1/emails/fetch-detect-predict", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "emails" in data
    assert "extractions" in data
    assert "suggested_slots" in data
    assert "status" in data
    assert data["status"] == "READY_TO_SCHEDULE"
    assert len(data["emails"]) == 1
    assert len(data["extractions"]) == 1
    assert isinstance(data["suggested_slots"], list)
    assert data["extractions"][0]["classification"] == "meeting_schedule"
