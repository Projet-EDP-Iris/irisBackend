import base64
import json
import os
from unittest.mock import MagicMock, patch

from app.schemas.detection import EmailInput
from app.services.gmail_service import (
    TOKENS_DIR,
    GmailService,
    _decode_body,
    _extract_body_from_payload,
    fetch_recent_emails_as_inputs_for_user,
    get_token_path_for_user,
)


def test_decode_body_empty():
    assert _decode_body(None) == ""
    assert _decode_body("") == ""


def test_decode_body_simple():
    raw = "Hello world"
    encoded = base64.urlsafe_b64encode(raw.encode()).decode("ASCII")
    assert _decode_body(encoded) == raw


def test_extract_body_from_payload_body_data():
    encoded = base64.urlsafe_b64encode("Full email body".encode()).decode("ASCII")
    payload = {"body": {"data": encoded}}
    assert _extract_body_from_payload(payload, "snippet") == "Full email body"


def test_extract_body_from_payload_parts_text_plain():
    encoded = base64.urlsafe_b64encode("Plain text part".encode()).decode("ASCII")
    payload = {
        "body": {},
        "parts": [
            {"mimeType": "text/plain", "body": {"data": encoded}},
        ],
    }
    assert _extract_body_from_payload(payload, "fallback") == "Plain text part"


def test_extract_body_from_payload_parts_prefers_plain_over_html():
    plain_enc = base64.urlsafe_b64encode("Plain".encode()).decode("ASCII")
    html_enc = base64.urlsafe_b64encode("HTML".encode()).decode("ASCII")
    payload = {
        "parts": [
            {"mimeType": "text/html", "body": {"data": html_enc}},
            {"mimeType": "text/plain", "body": {"data": plain_enc}},
        ],
    }
    assert _extract_body_from_payload(payload, "x") == "Plain"


def test_extract_body_from_payload_no_body_fallback():
    payload = {"body": {}, "parts": []}
    assert _extract_body_from_payload(payload, "snippet fallback") == "snippet fallback"


def test_get_token_path_for_user():
    path = get_token_path_for_user(42)
    assert path.endswith("gmail_user_42.json")
    assert "tokens" in path


@patch("app.services.gmail_service.build")
def test_fetch_recent_emails_returns_body_and_message_id(mock_build):
    encoded = base64.urlsafe_b64encode("Email body here".encode()).decode("ASCII")
    mock_get = MagicMock()
    mock_get.execute.return_value = {
        "id": "msg_123",
        "snippet": "short",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Test Subject"},
                {"name": "From", "value": "a@b.com"},
                {"name": "Date", "value": "Mon, 1 Jan 2020 12:00:00"},
            ],
            "body": {"data": encoded},
        },
    }
    mock_list = MagicMock()
    mock_list.execute.return_value = {"messages": [{"id": "msg_123"}]}
    mock_messages = MagicMock()
    mock_messages.list.return_value = mock_list
    mock_messages.get.return_value = mock_get
    mock_users = MagicMock()
    mock_users.messages.return_value = mock_messages
    mock_service = MagicMock()
    mock_service.users.return_value = mock_users
    mock_build.return_value = mock_service

    svc = GmailService()
    svc.service = mock_service
    result = svc.fetch_recent_emails(n=5)
    assert len(result) == 1
    assert result[0]["message_id"] == "msg_123"
    assert result[0]["body"] == "Email body here"
    assert result[0]["subject"] == "Test Subject"


@patch("app.services.gmail_service.build")
def test_fetch_recent_emails_multipart_body(mock_build):
    encoded = base64.urlsafe_b64encode("Multipart body".encode()).decode("ASCII")
    mock_get = MagicMock()
    mock_get.execute.return_value = {
        "id": "msg_456",
        "snippet": "snippet",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Multi"},
                {"name": "From", "value": "x@y.com"},
                {"name": "Date", "value": "Tue, 2 Jan 2020 10:00:00"},
            ],
            "body": {},
            "parts": [{"mimeType": "text/plain", "body": {"data": encoded}}],
        },
    }
    mock_list = MagicMock()
    mock_list.execute.return_value = {"messages": [{"id": "msg_456"}]}
    mock_messages = MagicMock()
    mock_messages.list.return_value = mock_list
    mock_messages.get.return_value = mock_get
    mock_users = MagicMock()
    mock_users.messages.return_value = mock_messages
    mock_service = MagicMock()
    mock_service.users.return_value = mock_users
    mock_build.return_value = mock_service

    svc = GmailService()
    svc.service = mock_service
    result = svc.fetch_recent_emails(n=1)
    assert result[0]["body"] == "Multipart body"
    assert result[0]["message_id"] == "msg_456"


def test_fetch_recent_emails_as_inputs_returns_email_inputs():
    svc = GmailService()
    with patch.object(svc, "fetch_recent_emails") as mock_fetch:
        mock_fetch.return_value = [
            {"subject": "S", "body": "B", "message_id": "mid1", "sender": "s@x.com", "date": "1"},
        ]
        svc.service = MagicMock()
        result = svc.fetch_recent_emails_as_inputs(n=1)
    assert len(result) == 1
    assert isinstance(result[0], EmailInput)
    assert result[0].subject == "S"
    assert result[0].body == "B"
    assert result[0].message_id == "mid1"


def test_fetch_recent_emails_as_inputs_for_user_no_token_returns_empty(tmp_path):
    with patch("app.services.gmail_service.get_token_path_for_user") as mock_path:
        mock_path.return_value = str(tmp_path / "nonexistent.json")
        result = fetch_recent_emails_as_inputs_for_user(999, n=5)
    assert result == []


def test_authenticate_for_user_returns_false_when_no_file():
    svc = GmailService()
    with patch("app.services.gmail_service.get_token_path_for_user") as mock_path:
        mock_path.return_value = os.path.join(TOKENS_DIR, "gmail_user_99999_nonexist.json")
        assert svc.authenticate_for_user(99999) is False


def test_authenticate_for_user_returns_true_when_token_exists(tmp_path):
    token_path = tmp_path / "gmail_user_1.json"
    token_data = {
        "token": "fake_access",
        "refresh_token": "fake_refresh",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "cid",
        "client_secret": "csec",
        "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        "gmail_email": "user@gmail.com",
    }
    token_path.write_text(json.dumps(token_data))
    with patch("app.services.gmail_service.get_token_path_for_user", return_value=str(token_path)):
        with patch("app.services.gmail_service.Credentials") as mock_creds:
            mock_cred_instance = MagicMock()
            mock_cred_instance.expired = False
            mock_cred_instance.refresh_token = None
            mock_creds.from_authorized_user_file.return_value = mock_cred_instance
            with patch("app.services.gmail_service.build") as _mock_build:
                svc = GmailService()
                result = svc.authenticate_for_user(1)
    assert result is True
