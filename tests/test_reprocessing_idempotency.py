"""
Regression test for the "emails get reclassified on every login" bug.

Root cause (see /Users/dan/.claude/plans/context-iris-is-a-shimmering-donut.md, Part 1):
  (a) no Gmail historyId / Outlook deltaLink cursor was ever persisted, so every
      sync fully re-listed the mailbox, and
  (b) sync_user_emails_background (the function called from the OAuth login
      callbacks) re-ran categorize_email() on every fetched email unconditionally,
      even for emails already categorized in a previous sync.

This test simulates two consecutive logins against the same mock Gmail mailbox
and asserts:
  - The Email row count for the user does not double after the 2nd sync.
  - categorize_email is invoked exactly once per unique message_id — not once
    per sync — proving the second login does not reclassify already-seen mail.
"""
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
from app.models.sync_state import SyncState
from app.models.user import User

TEST_DATABASE_URL = "sqlite:///./test_reprocessing_idempotency.db"
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
    db = TestSessionLocal()
    try:
        user = db.query(User).filter_by(email=email).first()
        if user:
            user.is_email_verified = True
            db.commit()
    finally:
        db.close()


@pytest.fixture
def registered_user(client_with_db, setup_database):
    client_with_db.post(
        "/api/v1/users/",
        json={"email": "reprocessing@example.com", "password": "Secret12!", "role": "regular"},
    )
    _verify_user("reprocessing@example.com")
    db = TestSessionLocal()
    try:
        user = db.query(User).filter_by(email="reprocessing@example.com").first()
        return user.id
    finally:
        db.close()


_MOCK_MAILBOX = [
    {"subject": "Réunion mardi", "body": "On se voit à 10h ?", "message_id": "msg_1",
     "sender": "a@b.com", "date": "Mon, 1 Jan 2024 10:00:00", "rfc_message_id": "<1@x>"},
    {"subject": "Facture à régler", "body": "Merci de valider avant vendredi.", "message_id": "msg_2",
     "sender": "c@d.com", "date": "Mon, 1 Jan 2024 11:00:00", "rfc_message_id": "<2@x>"},
]


@patch("app.api.endpoints.emails.categorize_email")
@patch("app.api.endpoints.emails.is_outlook_connected", return_value=False)
@patch("app.services.gmail_service._load_gmail_token_from_db")
@patch("app.api.endpoints.emails.GmailService")
def test_two_consecutive_syncs_do_not_duplicate_or_reclassify(
    mock_gmail_cls, mock_load_token, _mock_outlook, mock_categorize, registered_user
):
    """Simulates two logins in a row against an unchanged mailbox."""
    from app.api.endpoints.emails import sync_user_emails_background

    user_id = registered_user
    mock_load_token.return_value = ("fake_token", "user@gmail.com")

    mock_svc = MagicMock()
    mock_gmail_cls.return_value = mock_svc
    mock_svc.authenticate_for_user.return_value = True

    # First login: no cursor yet -> full fetch_email_page(), then a historyId is minted.
    mock_svc.fetch_email_page.return_value = (_MOCK_MAILBOX, None)
    mock_svc.get_history_id.return_value = "history-100"
    # Second login: a cursor now exists -> fetch_history_since() is used instead,
    # and (since nothing changed in the mailbox) returns no new messages.
    mock_svc.fetch_history_since.return_value = ([], "history-101")

    mock_categorize.return_value = "info"

    # Patch the SessionLocal that sync_user_emails_background opens internally
    # (it does a local `from app.db.database import SessionLocal`, bypassing the
    # FastAPI get_db override) so it writes to the same test database.
    with patch("app.db.database.SessionLocal", TestSessionLocal):
        sync_user_emails_background(user_id)
        sync_user_emails_background(user_id)

    db = TestSessionLocal()
    try:
        emails = db.query(Email).filter(Email.user_id == user_id).all()
        assert len(emails) == 2, "Email row count must not double after a 2nd identical sync"
        assert {e.message_id for e in emails} == {"msg_1", "msg_2"}

        sync_state = db.query(SyncState).filter(
            SyncState.user_id == user_id, SyncState.provider == "gmail"
        ).first()
        assert sync_state is not None
        assert sync_state.cursor == "history-101"
    finally:
        db.close()

    # The 2nd sync must not have re-listed the whole mailbox.
    mock_svc.fetch_email_page.assert_called_once()
    mock_svc.fetch_history_since.assert_called_once_with("history-100", limit=50)

    # categorize_email must run exactly once per unique message_id (2 total),
    # not once per sync (which would be 4) — proves the 2nd login didn't reclassify.
    assert mock_categorize.call_count == 2
