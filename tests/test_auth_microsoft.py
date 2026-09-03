from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import get_db
from app.main import app
from app.models import Base
from app.models.user import User

TEST_DATABASE_URL = "sqlite:///./test_auth_microsoft.db"
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


def _verify_user(email: str) -> None:
    db = TestSessionLocal()
    try:
        user = db.query(User).filter_by(email=email).first()
        if user:
            user.is_email_verified = True
            db.commit()
    finally:
        db.close()


def _seed_connected_outlook_user() -> tuple[int, dict]:
    client.post(
        "/api/v1/users/",
        json={"email": "outlook-disconnect@example.com", "password": "Secret12!", "role": "regular"},
    )
    _verify_user("outlook-disconnect@example.com")
    login = client.post(
        "/api/v1/users/login",
        json={"email": "outlook-disconnect@example.com", "password": "Secret12!"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    db = TestSessionLocal()
    try:
        user = db.query(User).filter_by(email="outlook-disconnect@example.com").first()
        user.outlook_oauth_token = "encrypted-token-blob"
        user.outlook_email = "outlook-disconnect@example.com"
        db.commit()
        return user.id, headers
    finally:
        db.close()


def setup_module(_module) -> None:
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)


def teardown_module(_module) -> None:
    Base.metadata.drop_all(bind=test_engine)


def test_disconnect_microsoft_unauthorized():
    r = client.delete("/api/v1/auth/microsoft")
    assert r.status_code == 403


def test_disconnect_microsoft_clears_stored_token():
    user_id, headers = _seed_connected_outlook_user()

    r = client.delete("/api/v1/auth/microsoft", headers=headers)
    assert r.status_code == 204

    db = TestSessionLocal()
    try:
        user = db.query(User).filter_by(id=user_id).first()
        assert user.outlook_oauth_token is None
        assert user.outlook_email is None
    finally:
        db.close()

    status_response = client.get("/api/v1/auth/microsoft/status", headers=headers)
    assert status_response.status_code == 200
    assert status_response.json()["connected"] is False
