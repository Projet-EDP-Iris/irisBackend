import pytest
from unittest.mock import MagicMock, patch
from app.services.gmail_service import GmailService

@pytest.fixture
def gmail_service():
    return GmailService(credentials_path="tests/mock_credentials.json")

def test_token_path_formatting(gmail_service):
    path = gmail_service._get_token_path(user_id=42)
    assert "gmail_user_42.json" in path

def test_decode_base64_plain_text(gmail_service):
    # Base64 for "Hello World"
    encoded = "SGVsbG8gV29ybGQ="
    decoded = gmail_service._decode_base64(encoded)
    assert decoded == "Hello World"

def test_get_body_priority_text_over_html(gmail_service):
    payload = {
        "parts": [
            {
                "mimeType": "text/html",
                "body": {"data": "PGgxPkh0bWwgSGVhZGVyPC9oMT4="} # <h1>Html Header</h1>
            },
            {
                "mimeType": "text/plain",
                "body": {"data": "UGxhaW4gdGV4dCBib2R5"} # Plain text body
            }
        ]
    }
    body = gmail_service._get_body(payload)
    assert body == "Plain text body"

def test_fetch_recent_emails_empty(gmail_service):
    service = MagicMock()
    service.users().messages().list().execute.return_value = {"messages": []}
    
    emails = gmail_service.fetch_recent_emails(service, n=5)
    assert emails == []

@patch("app.services.gmail_service.build")
def test_authenticate_for_user_missing_token(mock_build, gmail_service):
    with patch("os.path.exists", return_value=False):
        service = gmail_service.authenticate_for_user(user_id=123)
        assert service is None
