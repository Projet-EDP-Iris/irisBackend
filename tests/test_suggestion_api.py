"""Tests for /suggest/{email_id} and /suggest-inline endpoints."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import get_db
from app.main import app
from app.models.base import Base
from app.models.email import Email  # registers Email table
from app.models.user import User   # registers User table

TEST_DATABASE_URL = "sqlite:///./test_suggestion.db"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


# ── /suggest-inline ─────────────────────────────────────────────────────────

def test_suggest_inline_returns_200_with_variants():
    """POST /suggest-inline must return 3 labelled variants."""
    response = client.post(
        "/api/v1/suggest-inline",
        json={
            "subject": "Reunion projet Iris",
            "body": "Bonjour, pouvez-vous confirmer votre disponibilite pour jeudi a 14h ?"
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "READY"
    assert "variants" in data
    variants = data["variants"]
    assert isinstance(variants, list)
    assert len(variants) >= 1
    for v in variants:
        assert "label" in v
        assert "content" in v
        assert len(v["content"]) > 0


def test_suggest_inline_missing_subject_returns_422():
    """subject is required — missing field must return 422."""
    response = client.post(
        "/api/v1/suggest-inline",
        json={"body": "Corps de l email seulement"},
    )
    assert response.status_code == 422


def test_suggest_inline_missing_body_returns_422():
    """body is required — missing field must return 422."""
    response = client.post(
        "/api/v1/suggest-inline",
        json={"subject": "Sujet seulement"},
    )
    assert response.status_code == 422


def test_suggest_inline_empty_strings_returns_200():
    """Empty strings are valid inputs — endpoint must still return suggestions."""
    response = client.post(
        "/api/v1/suggest-inline",
        json={"subject": "", "body": ""},
    )
    assert response.status_code == 200


# ── /suggest/{email_id} ──────────────────────────────────────────────────────

def _create_email_in_db(db, predicted_slots=None):
    """Helper: insert an Email row and return its id."""
    email = Email(
        message_id="test-msg-001",
        user_id=1,
        subject="Meeting demain",
        body="Pouvez-vous confirmer ?",
        predicted_slots=predicted_slots,
    )
    db.add(email)
    db.commit()
    db.refresh(email)
    return email.id


def test_suggest_by_id_not_found_returns_404():
    """Requesting a non-existent email_id must return 404."""
    response = client.post("/api/v1/suggest/9999")
    assert response.status_code == 404


def test_suggest_by_id_no_slots_returns_400():
    """An email without predicted_slots must return 400."""
    db = TestSessionLocal()
    email_id = _create_email_in_db(db, predicted_slots=None)
    db.close()

    response = client.post(f"/api/v1/suggest/{email_id}")
    assert response.status_code == 400
    assert "creneau" in response.json()["detail"].lower()


def test_suggest_by_id_with_slots_returns_200():
    """An email with predicted_slots must return a suggestion."""
    slots = [{"start": "2026-05-01T10:00:00", "end": "2026-05-01T10:30:00"}]
    db = TestSessionLocal()
    email_id = _create_email_in_db(db, predicted_slots=slots)
    db.close()

    response = client.post(f"/api/v1/suggest/{email_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["email_id"] == email_id
    assert "suggested_content" in data
    assert len(data["suggested_content"]) > 0
    assert data["status"] == "READY"
