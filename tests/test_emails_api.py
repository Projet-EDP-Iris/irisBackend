import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import get_db
from app.main import app
from app.models.base import Base
from app.models.user import User
from app.core.auth import get_current_user

# Setup test DB
TEST_DATABASE_URL = "sqlite:///./test_emails.db"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()

# Mock user for dependency injection
test_user = User(id=1, email="test@example.com", role="regular")

def override_get_current_user():
    return test_user

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_current_user] = override_get_current_user

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    # Add our test user to DB
    if not db.query(User).filter_by(id=1).first():
        db.add(User(id=1, email="test@example.com", password_hash="hashed", role="regular"))
        db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=test_engine)

@patch("app.api.endpoints.emails.GmailService.authenticate_for_user")
@patch("app.api.endpoints.emails.GmailService.fetch_recent_emails")
def test_get_emails_success(mock_fetch, mock_auth):
    # Mock successful auth and email fetching
    mock_auth.return_value = MagicMock() # Mocked Gmail service resource
    mock_fetch.return_value = [
        {"message_id": "123", "subject": "Test", "sender": "me", "date": "today", "snippet": "hi", "body": "hello"}
    ]
    
    response = client.get("/api/v1/emails/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["message_id"] == "123"

@patch("app.api.endpoints.emails.GmailService.authenticate_for_user")
def test_get_emails_no_token(mock_auth):
    # Mock failed auth (no token)
    mock_auth.return_value = None
    
    response = client.get("/api/v1/emails/")
    assert response.status_code == 404
    assert "No Gmail token found" in response.json()["detail"]

@patch("app.api.endpoints.emails.GmailService.authenticate_for_user")
@patch("app.api.endpoints.emails.GmailService.fetch_recent_emails_as_inputs")
def test_fetch_and_detect_emails(mock_fetch, mock_auth):
    mock_auth.return_value = MagicMock()
    mock_fetch.return_value = [
        {"message_id": "123", "subject": "Reunion demain", "sender": "me", "date": "today", "snippet": "hi", "body": "hello"}
    ]
    
    response = client.post("/api/v1/emails/fetch-and-detect")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["extractions"][0]["detected_intent"] == "meeting"
