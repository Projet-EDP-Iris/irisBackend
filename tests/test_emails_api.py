from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.database import get_db
from app.main import app
from app.models import Base
from app.models.user import User

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


def _verify_user(email: str) -> None:
    """Mark user as email-verified directly in test DB."""
    db = TestSessionLocal()
    try:
        user = db.query(User).filter_by(email=email).first()
        if user:
            user.is_email_verified = True
            db.commit()
    finally:
        db.close()


@pytest.fixture
def auth_headers(client_with_db, setup_database):
    client_with_db.post(
        "/api/v1/users/",
        json={"email": "emails@example.com", "password": "Secret12!", "role": "regular"},
    )
    _verify_user("emails@example.com")
    login = client_with_db.post(
        "/api/v1/users/login",
        json={"email": "emails@example.com", "password": "Secret12!"},
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_get_emails_unauthorized(client_with_db, setup_database):
    r = client_with_db.get("/api/v1/emails")
    assert r.status_code == 403


@patch("app.services.gmail_service._load_gmail_token_from_db", return_value=None)
@patch("app.services.outlook_email_service._load_outlook_token_from_db", return_value=None)
def test_get_emails_not_connected_returns_404(mock_outlook, mock_gmail, client_with_db, setup_database, auth_headers):
    r = client_with_db.get("/api/v1/emails", headers=auth_headers)
    assert r.status_code == 404
    assert "email provider" in r.json().get("detail", "").lower()


@patch("app.api.endpoints.emails.is_outlook_connected", return_value=False)
@patch("app.services.gmail_service._load_gmail_token_from_db")
@patch("app.api.endpoints.emails.GmailService")
def test_get_emails_returns_list_with_subject_body_message_id(mock_gmail, mock_load_token, _mock_outlook, client_with_db, setup_database, auth_headers):
    mock_load_token.return_value = ("fake_token", "user@gmail.com")
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


@patch("app.api.endpoints.emails.is_outlook_connected", return_value=False)
@patch("app.services.gmail_service._load_gmail_token_from_db")
@patch("app.api.endpoints.emails.GmailService")
def test_get_emails_invalid_stored_connection_returns_503(
    mock_gmail, mock_load_token, _mock_outlook, client_with_db, setup_database, auth_headers
):
    mock_load_token.return_value = ("fake_token", "user@gmail.com")
    mock_svc = MagicMock()
    mock_svc.authenticate_for_user.return_value = False
    mock_gmail.return_value = mock_svc

    r = client_with_db.get("/api/v1/emails", headers=auth_headers)
    # authenticate_for_user returns False → _get_gmail_emails returns [] → endpoint returns []
    assert r.status_code == 200
    assert r.json() == []


def test_fetch_and_detect_unauthorized(client_with_db, setup_database):
    r = client_with_db.post("/api/v1/emails/fetch-and-detect")
    assert r.status_code == 403


@patch("app.services.gmail_service._load_gmail_token_from_db", return_value=None)
@patch("app.services.outlook_email_service._load_outlook_token_from_db", return_value=None)
def test_fetch_and_detect_not_connected_returns_404(mock_outlook, mock_gmail, client_with_db, setup_database, auth_headers):
    r = client_with_db.post("/api/v1/emails/fetch-and-detect", headers=auth_headers)
    assert r.status_code == 404


@patch("app.api.endpoints.emails.is_outlook_connected", return_value=False)
@patch("app.services.gmail_service._load_gmail_token_from_db")
@patch("app.api.endpoints.emails.GmailService")
def test_fetch_and_detect_returns_emails_and_extractions(mock_gmail, mock_load_token, _mock_outlook, client_with_db, setup_database, auth_headers):
    mock_load_token.return_value = ("fake_token", "user@gmail.com")
    mock_svc = MagicMock()
    mock_gmail.return_value = mock_svc
    mock_svc.authenticate_for_user.return_value = True
    mock_svc.fetch_recent_emails.return_value = [
        {"subject": "Meeting", "body": "Can we meet tomorrow at 3pm?", "message_id": "m1", "sender": "a@b.com", "date": "1"},
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


@patch("app.services.gmail_service._load_gmail_token_from_db", return_value=None)
@patch("app.services.outlook_email_service._load_outlook_token_from_db", return_value=None)
def test_fetch_detect_predict_not_connected_returns_404(mock_outlook, mock_gmail, client_with_db, setup_database, auth_headers):
    r = client_with_db.post("/api/v1/emails/fetch-detect-predict", headers=auth_headers)
    assert r.status_code == 404


@patch("app.api.endpoints.emails.is_outlook_connected", return_value=False)
@patch("app.services.gmail_service._load_gmail_token_from_db")
@patch("app.api.endpoints.emails.GmailService")
def test_fetch_detect_predict_returns_emails_extractions_and_suggested_slots(
    mock_gmail, mock_load_token, _mock_outlook, client_with_db, setup_database, auth_headers
):
    mock_load_token.return_value = ("fake_token", "user@gmail.com")
    mock_svc = MagicMock()
    mock_gmail.return_value = mock_svc
    mock_svc.authenticate_for_user.return_value = True
    mock_svc.fetch_recent_emails.return_value = [
        {"subject": "Meeting", "body": "Can we meet tomorrow at 3pm?", "message_id": "m1", "sender": "a@b.com", "date": "1"},
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


# ─────────────────────────────────────────────
# /emails/feed category filter tests
# ─────────────────────────────────────────────

@patch("app.api.endpoints.emails.is_outlook_connected", return_value=False)
@patch("app.api.endpoints.emails.categorize_email")
@patch("app.services.gmail_service._load_gmail_token_from_db")
@patch("app.api.endpoints.emails.GmailService")
def test_feed_category_filter_returns_only_matching_category(
    mock_gmail, mock_load_token, mock_categorize, _mock_outlook, client_with_db, setup_database, auth_headers
):
    """GET /emails/feed?category=rdv must return only emails classified as 'rdv'."""
    mock_load_token.return_value = ("fake_token", "user@gmail.com")
    mock_svc = MagicMock()
    mock_gmail.return_value = mock_svc
    mock_svc.authenticate_for_user.return_value = True
    mock_svc.fetch_email_page.return_value = (
        [
            {"subject": "Réunion demain", "body": "Rendez-vous lundi", "message_id": "rdv_1", "sender": "a@b.com", "date": "2024-10-18T10:00:00"},
            {"subject": "Promo 50%", "body": "Code PROMO50", "message_id": "promo_1", "sender": "shop@deals.com", "date": "2024-10-18T09:00:00"},
            {"subject": "Newsletter", "body": "Actus de la semaine", "message_id": "info_1", "sender": "news@example.com", "date": "2024-10-18T08:00:00"},
        ],
        None,
    )
    # Simulate NLP categorization: first email is rdv, others are not
    mock_categorize.side_effect = ["rdv", "bonsplans", "info"]

    r = client_with_db.get("/api/v1/emails/feed?category=rdv", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "emails" in data
    for email in data["emails"]:
        assert email["category"] == "rdv", f"Expected rdv but got {email['category']} for '{email['subject']}'"


@patch("app.api.endpoints.emails.is_outlook_connected", return_value=False)
@patch("app.api.endpoints.emails.categorize_email")
@patch("app.services.gmail_service._load_gmail_token_from_db")
@patch("app.api.endpoints.emails.GmailService")
def test_feed_no_category_filter_returns_all_emails(
    mock_gmail, mock_load_token, mock_categorize, _mock_outlook, client_with_db, setup_database, auth_headers
):
    """GET /emails/feed without ?category= must return all emails regardless of category."""
    mock_load_token.return_value = ("fake_token", "user@gmail.com")
    mock_svc = MagicMock()
    mock_gmail.return_value = mock_svc
    mock_svc.authenticate_for_user.return_value = True
    mock_svc.fetch_email_page.return_value = (
        [
            {"subject": "Meeting invite", "body": "Can we meet Monday?", "message_id": "m1", "sender": "a@b.com", "date": "2024-10-18T10:00:00"},
            {"subject": "Sale 20% off", "body": "Limited time offer CODE20", "message_id": "m2", "sender": "shop@deals.com", "date": "2024-10-18T09:00:00"},
        ],
        None,
    )
    mock_categorize.side_effect = ["rdv", "bonsplans"]

    r = client_with_db.get("/api/v1/emails/feed", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data["emails"]) == 2
