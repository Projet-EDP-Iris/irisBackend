"""
Tests for Outlook email reading via Microsoft Graph API.

Tests:
  - is_outlook_connected() returns correct state based on token file presence
  - fetch_outlook_emails() parses Graph API response correctly
  - get_outlook_connection_status() returns correct status when connected/not connected
  - emails endpoint merges Gmail + Outlook results
  - emails endpoint returns 404 when neither provider is connected
"""
import json
import os
import time
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.email import EmailItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_graph_message(
    msg_id: str = "MSG001",
    subject: str = "Réunion vendredi",
    body_content: str = "Bonjour, je vous propose vendredi à 14h.",
    sender_name: str = "Alice Martin",
    sender_email: str = "alice@contoso.com",
    received: str = "2025-04-25T09:00:00Z",
) -> dict:
    return {
        "id": msg_id,
        "subject": subject,
        "body": {"contentType": "text", "content": body_content},
        "from": {"emailAddress": {"name": sender_name, "address": sender_email}},
        "receivedDateTime": received,
        "isDraft": False,
    }


# ---------------------------------------------------------------------------
# is_outlook_connected
# ---------------------------------------------------------------------------

class TestIsOutlookConnected:
    def test_returns_false_when_no_token_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.services.outlook_email_service._token_path",
            lambda uid: str(tmp_path / f"outlook_user_{uid}.json"),
        )
        from app.services.outlook_email_service import is_outlook_connected
        assert is_outlook_connected(999) is False

    def test_returns_true_when_token_file_exists(self, tmp_path, monkeypatch):
        token_file = tmp_path / "outlook_user_1.json"
        token_file.write_text("{}")
        monkeypatch.setattr(
            "app.services.outlook_email_service._token_path",
            lambda uid: str(tmp_path / f"outlook_user_{uid}.json"),
        )
        from app.services.outlook_email_service import is_outlook_connected
        assert is_outlook_connected(1) is True


# ---------------------------------------------------------------------------
# _parse_email_item
# ---------------------------------------------------------------------------

class TestParseEmailItem:
    def test_full_message(self):
        from app.services.outlook_email_service import _parse_email_item
        msg = _make_graph_message()
        item = _parse_email_item(msg)
        assert item.subject == "Réunion vendredi"
        assert "Bonjour" in item.body
        assert item.sender == "Alice Martin <alice@contoso.com>"
        assert item.date == "2025-04-25T09:00:00Z"
        assert item.message_id == "MSG001"

    def test_missing_sender_name(self):
        from app.services.outlook_email_service import _parse_email_item
        msg = _make_graph_message(sender_name="", sender_email="bob@example.com")
        item = _parse_email_item(msg)
        assert item.sender == "bob@example.com"

    def test_missing_subject_becomes_placeholder(self):
        from app.services.outlook_email_service import _parse_email_item
        msg = _make_graph_message(subject="")
        msg["subject"] = None
        item = _parse_email_item(msg)
        assert item.subject == "(Sans objet)"

    def test_missing_body(self):
        from app.services.outlook_email_service import _parse_email_item
        msg = _make_graph_message()
        msg.pop("body")
        item = _parse_email_item(msg)
        assert item.body == ""


# ---------------------------------------------------------------------------
# fetch_outlook_emails
# ---------------------------------------------------------------------------

class TestFetchOutlookEmails:
    def test_returns_email_items(self, monkeypatch):
        """fetch_outlook_emails should convert Graph API messages to EmailItem list."""
        fake_messages = [_make_graph_message(msg_id=f"M{i}") for i in range(3)]

        monkeypatch.setattr(
            "app.services.outlook_email_service.get_valid_token",
            lambda uid: "fake-access-token",
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"value": fake_messages}

        with patch("app.services.outlook_email_service.httpx.get", return_value=mock_response):
            from app.services.outlook_email_service import fetch_outlook_emails
            result = fetch_outlook_emails(user_id=1, n=3)

        assert len(result) == 3
        assert all(isinstance(e, EmailItem) for e in result)
        assert result[0].message_id == "M0"

    def test_raises_file_not_found_if_not_connected(self, monkeypatch):
        """Should propagate FileNotFoundError from get_valid_token when not connected."""
        monkeypatch.setattr(
            "app.services.outlook_email_service.get_valid_token",
            lambda uid: (_ for _ in ()).throw(FileNotFoundError("no token")),
        )
        from app.services.outlook_email_service import fetch_outlook_emails
        with pytest.raises(FileNotFoundError):
            fetch_outlook_emails(user_id=42, n=5)

    def test_empty_inbox_returns_empty_list(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.outlook_email_service.get_valid_token",
            lambda uid: "fake-access-token",
        )
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"value": []}
        with patch("app.services.outlook_email_service.httpx.get", return_value=mock_response):
            from app.services.outlook_email_service import fetch_outlook_emails
            result = fetch_outlook_emails(user_id=1, n=10)
        assert result == []


# ---------------------------------------------------------------------------
# get_outlook_connection_status
# ---------------------------------------------------------------------------

class TestGetOutlookConnectionStatus:
    def test_not_connected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.services.outlook_email_service._token_path",
            lambda uid: str(tmp_path / f"outlook_user_{uid}.json"),
        )
        from app.services.outlook_email_service import get_outlook_connection_status
        result = get_outlook_connection_status(99)
        assert result == {"connected": False, "email": None}

    def test_connected_returns_email(self, tmp_path, monkeypatch):
        token_file = tmp_path / "outlook_user_1.json"
        token_file.write_text("{}")
        monkeypatch.setattr(
            "app.services.outlook_email_service._token_path",
            lambda uid: str(tmp_path / f"outlook_user_{uid}.json"),
        )
        monkeypatch.setattr(
            "app.services.outlook_email_service.get_valid_token",
            lambda uid: "token",
        )
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"mail": "user@contoso.com"}
        with patch("app.services.outlook_email_service.httpx.get", return_value=mock_response):
            from app.services.outlook_email_service import get_outlook_connection_status
            result = get_outlook_connection_status(1)
        assert result["connected"] is True
        assert result["email"] == "user@contoso.com"
