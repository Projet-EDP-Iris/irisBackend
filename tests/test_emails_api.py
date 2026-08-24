from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.database import get_db
from app.main import app
from app.models import Base
from app.models.email import Email
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


# --- Server-side category filtering: /emails/cached?category= and /emails/counts ---


def _seed_categorized_emails(user_email: str) -> None:
    """Insert emails with known categories directly into the test DB."""
    db = TestSessionLocal()
    try:
        user = db.query(User).filter_by(email=user_email).first()
        db.add_all([
            Email(subject="Réunion mardi", body="RDV à 10h", message_id="cat_1",
                  user_id=user.id, status="fetched", category="rdv"),
            Email(subject="Point projet", body="On se cale un créneau ?", message_id="cat_2",
                  user_id=user.id, status="fetched", category="rdv"),
            Email(subject="Valider le doc", body="Merci de signer avant vendredi", message_id="cat_3",
                  user_id=user.id, status="fetched", category="action"),
            Email(subject="-20% ce week-end", body="Code promo IRIS20", message_id="cat_4",
                  user_id=user.id, status="fetched", category="bonsplans"),
            Email(subject="Newsletter", body="Les infos du mois", message_id="cat_5",
                  user_id=user.id, status="fetched", category=None),
        ])
        db.commit()
    finally:
        db.close()


def test_cached_emails_unauthorized(client_with_db, setup_database):
    r = client_with_db.get("/api/v1/emails/cached")
    assert r.status_code == 403


def test_cached_emails_filters_by_category(client_with_db, setup_database, auth_headers):
    _seed_categorized_emails("emails@example.com")
    r = client_with_db.get("/api/v1/emails/cached?category=rdv", headers=auth_headers)
    assert r.status_code == 200
    emails = r.json()["emails"]
    assert len(emails) == 2
    assert all(e["category"] == "rdv" for e in emails)


def test_cached_emails_without_category_returns_all(client_with_db, setup_database, auth_headers):
    _seed_categorized_emails("emails@example.com")
    r = client_with_db.get("/api/v1/emails/cached", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()["emails"]) == 5


def test_cached_emails_empty_category_returns_no_results(client_with_db, setup_database, auth_headers):
    _seed_categorized_emails("emails@example.com")
    r = client_with_db.get("/api/v1/emails/cached?category=attente", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["emails"] == []
    assert r.json()["has_more"] is False


def test_cached_emails_does_not_leak_other_users_emails(client_with_db, setup_database, auth_headers):
    _seed_categorized_emails("emails@example.com")
    db = TestSessionLocal()
    try:
        db.add(Email(subject="Other user RDV", body="x", message_id="other_1",
                     user_id=99999, status="fetched", category="rdv"))
        db.commit()
    finally:
        db.close()
    r = client_with_db.get("/api/v1/emails/cached?category=rdv", headers=auth_headers)
    assert r.status_code == 200
    subjects = [e["subject"] for e in r.json()["emails"]]
    assert "Other user RDV" not in subjects


def test_counts_unauthorized(client_with_db, setup_database):
    r = client_with_db.get("/api/v1/emails/counts")
    assert r.status_code == 403


def test_counts_returns_per_category_totals(client_with_db, setup_database, auth_headers):
    _seed_categorized_emails("emails@example.com")
    r = client_with_db.get("/api/v1/emails/counts", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    # NULL category is reported as "info" so the frontend tab badges stay consistent
    assert data["counts"] == {"rdv": 2, "action": 1, "bonsplans": 1, "info": 1}
    assert data["total"] == 5


def test_counts_empty_mailbox_returns_zero_total(client_with_db, setup_database, auth_headers):
    r = client_with_db.get("/api/v1/emails/counts", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"counts": {}, "total": 0}


# --- mark-done: category-gated terminal state ---


def _seed_email(user_email: str, message_id: str, category: str | None, is_done: bool = False) -> int:
    """Insert a single email with a known category directly into the test DB, return its id."""
    db = TestSessionLocal()
    try:
        user = db.query(User).filter_by(email=user_email).first()
        email = Email(
            subject="Test", body="Body", message_id=message_id,
            user_id=user.id, status="fetched", category=category, is_done=is_done,
        )
        db.add(email)
        db.commit()
        db.refresh(email)
        return email.id
    finally:
        db.close()


def test_mark_done_unauthorized(client_with_db, setup_database):
    r = client_with_db.post("/api/v1/emails/1/mark-done")
    assert r.status_code == 403


@pytest.mark.parametrize("category", ["action", "attente", "bonsplans"])
def test_mark_done_succeeds_for_allowed_categories(client_with_db, setup_database, auth_headers, category):
    email_id = _seed_email("emails@example.com", f"md_{category}", category)
    r = client_with_db.post(f"/api/v1/emails/{email_id}/mark-done", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"status": "done", "email_id": email_id}


@pytest.mark.parametrize("category", ["rdv", "info", None])
def test_mark_done_rejects_disallowed_categories(client_with_db, setup_database, auth_headers, category):
    email_id = _seed_email("emails@example.com", f"md_bad_{category}", category)
    r = client_with_db.post(f"/api/v1/emails/{email_id}/mark-done", headers=auth_headers)
    assert r.status_code == 400
    assert "action, attente, or bonsplans" in r.json()["detail"]


def test_mark_done_not_found_returns_404(client_with_db, setup_database, auth_headers):
    r = client_with_db.post("/api/v1/emails/999999/mark-done", headers=auth_headers)
    assert r.status_code == 404


# --- get_email_body: only Info emails get auto-marked done on open ---


@patch("app.api.endpoints.emails.GmailService")
def test_get_email_body_marks_info_email_done(mock_gmail, client_with_db, setup_database, auth_headers):
    _seed_email("emails@example.com", "body_info_1", "info")
    mock_svc = MagicMock()
    mock_gmail.return_value = mock_svc
    mock_svc.authenticate_for_user.return_value = True
    mock_svc.fetch_email_body.return_value = "Full body text"

    r = client_with_db.get("/api/v1/emails/body/body_info_1?provider=gmail", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"body": "Full body text"}

    db = TestSessionLocal()
    try:
        record = db.query(Email).filter_by(message_id="body_info_1").first()
        assert record.is_done is True
    finally:
        db.close()


@patch("app.api.endpoints.emails.GmailService")
def test_get_email_body_does_not_mark_other_categories_done(mock_gmail, client_with_db, setup_database, auth_headers):
    _seed_email("emails@example.com", "body_action_1", "action")
    mock_svc = MagicMock()
    mock_gmail.return_value = mock_svc
    mock_svc.authenticate_for_user.return_value = True
    mock_svc.fetch_email_body.return_value = "Full body text"

    r = client_with_db.get("/api/v1/emails/body/body_action_1?provider=gmail", headers=auth_headers)
    assert r.status_code == 200

    db = TestSessionLocal()
    try:
        record = db.query(Email).filter_by(message_id="body_action_1").first()
        assert record.is_done is False
    finally:
        db.close()


# --- /emails hydrates persisted is_done/is_read/status (not just /emails/cached) ---


@patch("app.api.endpoints.emails.is_outlook_connected", return_value=False)
@patch("app.services.gmail_service._load_gmail_token_from_db")
@patch("app.api.endpoints.emails.GmailService")
def test_get_emails_hydrates_persisted_state(mock_gmail, mock_load_token, _mock_outlook, client_with_db, setup_database, auth_headers):
    _seed_email("emails@example.com", "hydrate_1", "action", is_done=True)
    db = TestSessionLocal()
    try:
        record = db.query(Email).filter_by(message_id="hydrate_1").first()
        record.is_read = True
        db.commit()
    finally:
        db.close()

    mock_load_token.return_value = ("fake_token", "user@gmail.com")
    mock_svc = MagicMock()
    mock_gmail.return_value = mock_svc
    mock_svc.authenticate_for_user.return_value = True
    mock_svc.fetch_recent_emails.return_value = [
        {"subject": "Test", "body": "Body", "message_id": "hydrate_1", "sender": "a@b.com", "date": "1"},
    ]

    r = client_with_db.get("/api/v1/emails", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["is_done"] is True
    assert data[0]["is_read"] is True


# --- reminders: expose provider outcome to the frontend ---


def _set_task_providers(providers: list[str]) -> None:
    db = TestSessionLocal()
    try:
        user = db.query(User).filter_by(email="emails@example.com").first()
        user.calendar_providers = providers
        user.calendar_provider = providers[0] if providers else None
        db.commit()
    finally:
        db.close()


@patch("app.api.endpoints.emails.create_google_task", return_value="google-task-1")
def test_remind_returns_success_message(mock_google_task, client_with_db, setup_database, auth_headers):
    email_id = _seed_email("emails@example.com", "remind_google", "attente")
    _set_task_providers(["google"])

    response = client_with_db.post(f"/api/v1/emails/{email_id}/remind", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["message"] == "Rappel créé dans vos tâches."
    assert response.json()["providers"] == [
        {"provider": "google", "task_id": "google-task-1", "error": None}
    ]
    mock_google_task.assert_called_once()


@patch("app.api.endpoints.emails.create_outlook_task", side_effect=RuntimeError("provider unavailable"))
@patch("app.api.endpoints.emails.create_google_task", return_value="google-task-1")
def test_remind_returns_partial_provider_message(
    mock_google_task, _mock_outlook_task, client_with_db, setup_database, auth_headers
):
    email_id = _seed_email("emails@example.com", "remind_partial", "attente")
    _set_task_providers(["google", "outlook"])

    response = client_with_db.post(f"/api/v1/emails/{email_id}/remind", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["message"] == "Rappel créé (google) — échec sur outlook."
    assert response.json()["providers"][1]["error"] == "Impossible de créer le rappel avec ce service"
    mock_google_task.assert_called_once()
