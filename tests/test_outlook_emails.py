"""
Tests for Outlook email reading via Microsoft Graph API.

Tests:
  - is_outlook_connected() returns correct state based on token file presence
  - fetch_outlook_emails() parses Graph API response correctly
  - get_outlook_connection_status() returns correct status when connected/not connected
  - emails endpoint merges Gmail + Outlook results
  - emails endpoint returns 404 when neither provider is connected
"""
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
    def test_returns_false_when_no_token_file(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.outlook_email_service._load_outlook_token_from_db",
            lambda uid: None,
        )
        from app.services.outlook_email_service import is_outlook_connected
        assert is_outlook_connected(999) is False

    def test_returns_true_when_token_file_exists(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.outlook_email_service._load_outlook_token_from_db",
            lambda uid: {"access_token": "tok"},
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


class TestFetchOutlookDelta:
    """fetch_outlook_delta must page all the way to @odata.deltaLink on a fresh
    baseline (delta_link=None), even past `limit` messages, since Graph only
    returns deltaLink on the final page (issue #103)."""

    def test_baseline_pages_past_limit_to_reach_delta_link(self, monkeypatch):
        """A mailbox with more messages than `limit` must still yield a delta
        cursor by walking every @odata.nextLink page."""
        monkeypatch.setattr(
            "app.services.outlook_email_service.get_valid_token",
            lambda uid: "fake-access-token",
        )

        page_1 = MagicMock()
        page_1.raise_for_status = MagicMock()
        page_1.json.return_value = {
            "value": [_make_graph_message(msg_id=f"M{i}") for i in range(50)],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/next-page-2",
        }
        page_2 = MagicMock()
        page_2.raise_for_status = MagicMock()
        page_2.json.return_value = {
            "value": [_make_graph_message(msg_id=f"M{i}") for i in range(50, 70)],
            "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta-cursor-abc",
        }

        with patch("app.services.outlook_email_service.httpx.get", side_effect=[page_1, page_2]):
            from app.services.outlook_email_service import fetch_outlook_delta
            emails, new_delta_link = fetch_outlook_delta(user_id=1, delta_link=None, limit=50)

        assert new_delta_link == "https://graph.microsoft.com/v1.0/delta-cursor-abc"
        # Still only returns the first `limit` messages for this call, even
        # though it had to walk further to reach the delta cursor.
        assert len(emails) == 50

    def test_baseline_single_page_returns_delta_link_immediately(self, monkeypatch):
        """A mailbox under `limit` messages gets its deltaLink on the first page."""
        monkeypatch.setattr(
            "app.services.outlook_email_service.get_valid_token",
            lambda uid: "fake-access-token",
        )
        page = MagicMock()
        page.raise_for_status = MagicMock()
        page.json.return_value = {
            "value": [_make_graph_message(msg_id="M1")],
            "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta-cursor-xyz",
        }

        with patch("app.services.outlook_email_service.httpx.get", return_value=page):
            from app.services.outlook_email_service import fetch_outlook_delta
            emails, new_delta_link = fetch_outlook_delta(user_id=1, delta_link=None, limit=50)

        assert new_delta_link == "https://graph.microsoft.com/v1.0/delta-cursor-xyz"
        assert len(emails) == 1

    def test_incremental_sync_with_existing_delta_link_does_not_over_fetch(self, monkeypatch):
        """When a delta_link is already stored, only messages since last sync
        are fetched — the `limit` cap only applies to a fresh baseline."""
        monkeypatch.setattr(
            "app.services.outlook_email_service.get_valid_token",
            lambda uid: "fake-access-token",
        )
        page = MagicMock()
        page.raise_for_status = MagicMock()
        page.json.return_value = {
            "value": [_make_graph_message(msg_id=f"M{i}") for i in range(75)],
            "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta-cursor-next",
        }

        with patch("app.services.outlook_email_service.httpx.get", return_value=page) as mock_get:
            from app.services.outlook_email_service import fetch_outlook_delta
            emails, new_delta_link = fetch_outlook_delta(
                user_id=1, delta_link="https://graph.microsoft.com/v1.0/delta-cursor-prev", limit=50
            )

        # Incremental sync isn't capped at `limit` — all 75 changed messages come back.
        assert len(emails) == 75
        assert new_delta_link == "https://graph.microsoft.com/v1.0/delta-cursor-next"
        mock_get.assert_called_once_with(
            "https://graph.microsoft.com/v1.0/delta-cursor-prev",
            params=None,
            headers={
                "Authorization": "Bearer fake-access-token",
                "Prefer": 'outlook.body-content-type="text"',
            },
            timeout=30,
        )

    def test_baseline_gives_up_after_max_pages_without_crashing(self, monkeypatch):
        """A pathologically large mailbox must not loop forever — it should
        stop at the safety cap and return no delta cursor (next sync retries)."""
        monkeypatch.setattr(
            "app.services.outlook_email_service.get_valid_token",
            lambda uid: "fake-access-token",
        )
        monkeypatch.setattr("app.services.outlook_email_service._MAX_BASELINE_PAGES", 2)

        def make_page(page_num: int) -> MagicMock:
            page = MagicMock()
            page.raise_for_status = MagicMock()
            page.json.return_value = {
                "value": [_make_graph_message(msg_id=f"P{page_num}")],
                "@odata.nextLink": f"https://graph.microsoft.com/v1.0/page-{page_num + 1}",
            }
            return page

        with patch(
            "app.services.outlook_email_service.httpx.get",
            side_effect=[make_page(1), make_page(2), make_page(3)],
        ) as mock_get:
            from app.services.outlook_email_service import fetch_outlook_delta
            emails, new_delta_link = fetch_outlook_delta(user_id=1, delta_link=None, limit=50)

        assert new_delta_link is None
        assert mock_get.call_count == 2


# ---------------------------------------------------------------------------
# get_outlook_connection_status
# ---------------------------------------------------------------------------

class TestGetOutlookConnectionStatus:
    def test_not_connected(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.outlook_email_service._load_outlook_token_from_db",
            lambda uid: None,
        )
        from app.services.outlook_email_service import get_outlook_connection_status
        result = get_outlook_connection_status(99)
        assert result == {"connected": False, "email": None}

    def test_connected_returns_email(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.outlook_email_service._load_outlook_token_from_db",
            lambda uid: {"access_token": "tok"},
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
