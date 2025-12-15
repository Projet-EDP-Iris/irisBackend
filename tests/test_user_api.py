import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import get_db
from app.main import app
from app.models.base import Base

# Create a test database engine (in-memory SQLite)
TEST_DATABASE_URL = "sqlite:///./test.db"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Override the get_db dependency
def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

# Test data
TEST_USER_EMAIL = "testuser@example.com"
TEST_USER_PASSWORD = "Secret12!"
TEST_ADMIN_EMAIL = "admin@example.com"
TEST_ADMIN_PASSWORD = "Admin123!"

@pytest.fixture(autouse=True)
def setup_database():
    """Reset database before each test"""
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)

def test_create_user_api():
    """Test creating a new user account"""
    response = client.post(
        "/users/",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "role": "regular"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == TEST_USER_EMAIL
    assert data["role"] == "regular"
    assert "id" in data
    assert "password" not in data
    assert "password_hash" not in data

def test_create_user_duplicate_email():
    """Test that duplicate email returns 400"""
    # Create first user
    client.post(
        "/users/",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "role": "regular"
        }
    )

    # Try to create duplicate
    response = client.post(
        "/users/",
        json={
            "email": TEST_USER_EMAIL,
            "password": "Different1!",
            "role": "regular"
        }
    )
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"].lower()

def test_create_user_weak_password():
    """Test that weak password returns 422"""
    response = client.post(
        "/users/",
        json={
            "email": "weak@example.com",
            "password": "weak",
            "role": "regular"
        }
    )
    assert response.status_code == 422

def test_login_success():
    """Test successful login returns JWT token"""
    # Create user
    client.post(
        "/users/",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "role": "regular"
        }
    )

    # Login
    response = client.post(
        "/users/login",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert len(data["access_token"]) > 0

def test_login_wrong_password():
    """Test login with wrong password returns 401"""
    # Create user
    client.post(
        "/users/",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "role": "regular"
        }
    )

    # Try to login with wrong password
    response = client.post(
        "/users/login",
        json={
            "email": TEST_USER_EMAIL,
            "password": "WrongPass1!"
        }
    )
    assert response.status_code == 401
    assert "incorrect" in response.json()["detail"].lower()

def test_login_nonexistent_user():
    """Test login with non-existent user returns 401"""
    response = client.post(
        "/users/login",
        json={
            "email": "nonexistent@example.com",
            "password": "SomePass1!"
        }
    )
    assert response.status_code == 401

def test_get_current_user():
    """Test getting current user info with valid token"""
    # Create and login
    client.post(
        "/users/",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "role": "regular"
        }
    )

    login_response = client.post(
        "/users/login",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        }
    )
    token = login_response.json()["access_token"]

    # Get current user
    response = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == TEST_USER_EMAIL
    assert data["role"] == "regular"

def test_get_current_user_no_token():
    """Test getting current user without token returns 403"""
    response = client.get("/users/me")
    assert response.status_code == 403

def test_get_current_user_invalid_token():
    """Test getting current user with invalid token returns 401"""
    response = client.get(
        "/users/me",
        headers={"Authorization": "Bearer invalid_token_here"}
    )
    assert response.status_code == 401

def test_get_user_by_id():
    """Test getting a specific user by ID"""
    # Create user
    create_response = client.post(
        "/users/",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "role": "regular"
        }
    )
    user_id = create_response.json()["id"]

    # Login
    login_response = client.post(
        "/users/login",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        }
    )
    token = login_response.json()["access_token"]

    # Get user by ID
    response = client.get(
        f"/users/{user_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == TEST_USER_EMAIL
    assert data["id"] == user_id

def test_get_user_not_found():
    """Test getting non-existent user returns 404"""
    # Create and login
    client.post(
        "/users/",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "role": "regular"
        }
    )

    login_response = client.post(
        "/users/login",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        }
    )
    token = login_response.json()["access_token"]

    # Try to get non-existent user
    response = client.get(
        "/users/99999",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404

def test_update_own_user():
    """Test user can update their own information"""
    # Create and login
    create_response = client.post(
        "/users/",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "role": "regular"
        }
    )
    user_id = create_response.json()["id"]

    login_response = client.post(
        "/users/login",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        }
    )
    token = login_response.json()["access_token"]

    # Update email
    response = client.patch(
        f"/users/{user_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "newemail@example.com"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "newemail@example.com"

def test_update_user_password():
    """Test user can update their password"""
    # Create and login
    create_response = client.post(
        "/users/",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "role": "regular"
        }
    )
    user_id = create_response.json()["id"]

    login_response = client.post(
        "/users/login",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        }
    )
    token = login_response.json()["access_token"]

    # Update password
    new_password = "NewPass123!"
    response = client.patch(
        f"/users/{user_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": new_password}
    )
    assert response.status_code == 200

    # Verify can login with new password
    login_response = client.post(
        "/users/login",
        json={
            "email": TEST_USER_EMAIL,
            "password": new_password
        }
    )
    assert login_response.status_code == 200

def test_update_other_user_forbidden():
    """Test regular user cannot update another user"""
    # Create two users
    user1_response = client.post(
        "/users/",
        json={
            "email": "user1@example.com",
            "password": "Pass1234!",
            "role": "regular"
        }
    )
    _ = user1_response.json()["id"]  # noqa: F841

    user2_response = client.post(
        "/users/",
        json={
            "email": "user2@example.com",
            "password": "Pass1234!",
            "role": "regular"
        }
    )
    user2_id = user2_response.json()["id"]

    # Login as user1
    login_response = client.post(
        "/users/login",
        json={
            "email": "user1@example.com",
            "password": "Pass1234!"
        }
    )
    token = login_response.json()["access_token"]

    # Try to update user2
    response = client.patch(
        f"/users/{user2_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "hacked@example.com"}
    )
    assert response.status_code == 403

def test_admin_can_update_other_user():
    """Test admin can update other users"""
    # Create regular user
    user_response = client.post(
        "/users/",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "role": "regular"
        }
    )
    user_id = user_response.json()["id"]

    # Create admin
    client.post(
        "/users/",
        json={
            "email": TEST_ADMIN_EMAIL,
            "password": TEST_ADMIN_PASSWORD,
            "role": "admin"
        }
    )

    # Login as admin
    login_response = client.post(
        "/users/login",
        json={
            "email": TEST_ADMIN_EMAIL,
            "password": TEST_ADMIN_PASSWORD
        }
    )
    token = login_response.json()["access_token"]

    # Update regular user
    response = client.patch(
        f"/users/{user_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"has_subscription": True}
    )
    assert response.status_code == 200
    assert response.json()["has_subscription"] is True

def test_delete_own_user():
    """Test user can delete their own account"""
    # Create and login
    create_response = client.post(
        "/users/",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "role": "regular"
        }
    )
    user_id = create_response.json()["id"]

    login_response = client.post(
        "/users/login",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        }
    )
    token = login_response.json()["access_token"]

    # Delete account
    response = client.delete(
        f"/users/{user_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 204

    # Verify user is deleted
    get_response = client.get(
        f"/users/{user_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert get_response.status_code == 401  # Token is now invalid

def test_delete_other_user_forbidden():
    """Test regular user cannot delete another user"""
    # Create two users
    _ = client.post(  # noqa: F841
        "/users/",
        json={
            "email": "user1@example.com",
            "password": "Pass1234!",
            "role": "regular"
        }
    )

    user2_response = client.post(
        "/users/",
        json={
            "email": "user2@example.com",
            "password": "Pass1234!",
            "role": "regular"
        }
    )
    user2_id = user2_response.json()["id"]

    # Login as user1
    login_response = client.post(
        "/users/login",
        json={
            "email": "user1@example.com",
            "password": "Pass1234!"
        }
    )
    token = login_response.json()["access_token"]

    # Try to delete user2
    response = client.delete(
        f"/users/{user2_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403

def test_admin_can_delete_other_user():
    """Test admin can delete other users"""
    # Create regular user
    user_response = client.post(
        "/users/",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "role": "regular"
        }
    )
    user_id = user_response.json()["id"]

    # Create admin
    client.post(
        "/users/",
        json={
            "email": TEST_ADMIN_EMAIL,
            "password": TEST_ADMIN_PASSWORD,
            "role": "admin"
        }
    )

    # Login as admin
    login_response = client.post(
        "/users/login",
        json={
            "email": TEST_ADMIN_EMAIL,
            "password": TEST_ADMIN_PASSWORD
        }
    )
    token = login_response.json()["access_token"]

    # Delete regular user
    response = client.delete(
        f"/users/{user_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 204
