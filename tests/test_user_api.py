from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_create_user_api():
    response = client.post(
        "/users/",
        json={
            "email": "apiuser@example.com",
            "password": "Secret12!",
            "role": "regular"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "apiuser@example.com"
    assert data["role"] == "regular"
