import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.google_oauth_service import (
    GoogleOAuthExchangeError,
    _consume_code_verifier,
    _store_code_verifier,
    exchange_code_for_token,
    get_auth_url,
)


@patch("app.services.google_oauth_service._verify_state", side_effect=ValueError("bad state"))
def test_exchange_code_for_token_classifies_state_failures(_mock_verify):
    with pytest.raises(GoogleOAuthExchangeError) as exc_info:
        exchange_code_for_token("bad", "code")

    assert exc_info.value.reason == "state_verification_failed"


@patch("app.services.google_oauth_service._ensure_runtime_config")
@patch("app.services.google_oauth_service._consume_code_verifier", return_value="stored-verifier")
@patch("app.services.google_oauth_service._verify_state", return_value=(1, "nonce-123"))
@patch("app.services.google_oauth_service.Flow.from_client_config")
def test_exchange_code_for_token_classifies_token_exchange_failures(
    mock_flow_factory,
    _mock_verify,
    _mock_consume_verifier,
    _mock_runtime_config,
):
    mock_flow = MagicMock()
    mock_flow.fetch_token.side_effect = RuntimeError("invalid_grant")
    mock_flow_factory.return_value = mock_flow

    with pytest.raises(GoogleOAuthExchangeError) as exc_info:
        exchange_code_for_token("1.valid", "code")

    assert exc_info.value.reason == "token_exchange_failed"


@patch("app.services.google_oauth_service._ensure_runtime_config")
@patch("app.services.google_oauth_service._consume_code_verifier", return_value="stored-verifier")
@patch("app.services.google_oauth_service._verify_state", return_value=(1, "nonce-123"))
@patch("app.services.google_oauth_service.build")
@patch("app.services.google_oauth_service.Flow.from_client_config")
def test_exchange_code_for_token_classifies_userinfo_failures(
    mock_flow_factory,
    mock_build,
    _mock_verify,
    _mock_consume_verifier,
    _mock_runtime_config,
):
    mock_flow = MagicMock()
    mock_flow.credentials = object()
    mock_flow_factory.return_value = mock_flow

    mock_oauth2 = MagicMock()
    mock_oauth2.userinfo.return_value.get.return_value.execute.side_effect = RuntimeError("userinfo failed")
    mock_build.return_value = mock_oauth2

    with pytest.raises(GoogleOAuthExchangeError) as exc_info:
        exchange_code_for_token("1.valid", "code")

    assert exc_info.value.reason == "userinfo_fetch_failed"


@patch("app.services.google_oauth_service._ensure_runtime_config")
@patch("app.services.google_oauth_service._consume_code_verifier", return_value="stored-verifier")
@patch("app.services.google_oauth_service._verify_state", return_value=(1, "nonce-123"))
@patch("app.services.google_oauth_service.GmailService")
@patch("app.services.google_oauth_service.build")
@patch("app.services.google_oauth_service.Flow.from_client_config")
def test_exchange_code_for_token_classifies_token_persist_failures(
    mock_flow_factory,
    mock_build,
    mock_gmail_service,
    _mock_verify,
    _mock_consume_verifier,
    _mock_runtime_config,
):
    mock_flow = MagicMock()
    mock_flow.credentials = object()
    mock_flow_factory.return_value = mock_flow

    mock_oauth2 = MagicMock()
    mock_oauth2.userinfo.return_value.get.return_value.execute.return_value = {"email": "user@example.com"}
    mock_build.return_value = mock_oauth2

    mock_gmail_service.return_value.save_token_for_user.side_effect = OSError("disk full")

    with pytest.raises(GoogleOAuthExchangeError) as exc_info:
        exchange_code_for_token("1.valid", "code")

    assert exc_info.value.reason == "token_persist_failed"


@patch("app.services.google_oauth_service._ensure_runtime_config")
@patch("app.services.google_oauth_service._generate_code_verifier", return_value="verifier-123")
@patch("app.services.google_oauth_service._generate_state_nonce", return_value="nonce-123")
@patch("app.services.google_oauth_service._store_code_verifier")
@patch("app.services.google_oauth_service.Flow.from_client_config")
def test_get_auth_url_stores_code_verifier_by_nonce(
    mock_flow_factory,
    mock_store_verifier,
    _mock_nonce,
    _mock_verifier,
    _mock_runtime_config,
):
    mock_flow = MagicMock()
    mock_flow.authorization_url.return_value = ("https://accounts.google.com/o/oauth2/auth", "ignored-state")
    mock_flow_factory.return_value = mock_flow

    auth_url = get_auth_url(7)

    assert auth_url == "https://accounts.google.com/o/oauth2/auth"
    assert mock_flow.code_verifier == "verifier-123"
    mock_store_verifier.assert_called_once_with("nonce-123", "verifier-123")
    called_state = mock_flow.authorization_url.call_args.kwargs["state"]
    assert called_state.startswith("7:nonce-123.")


def test_store_and_consume_code_verifier_round_trip(tmp_path):
    store_path = tmp_path / "pkce.json"

    with patch("app.services.google_oauth_service._get_pkce_store_path", return_value=store_path):
        _store_code_verifier("nonce-abc", "verifier-abc")
        assert _consume_code_verifier("nonce-abc") == "verifier-abc"

        data = json.loads(store_path.read_text())
        assert data == {}


@patch("app.services.google_oauth_service._ensure_runtime_config")
@patch("app.services.google_oauth_service._consume_code_verifier", return_value=None)
@patch("app.services.google_oauth_service._verify_state", return_value=(1, "missing-nonce"))
@patch("app.services.google_oauth_service.Flow.from_client_config")
def test_exchange_code_for_token_classifies_missing_pkce_verifier(
    mock_flow_factory,
    _mock_verify,
    _mock_consume_verifier,
    _mock_runtime_config,
):
    mock_flow_factory.return_value = MagicMock()

    with pytest.raises(GoogleOAuthExchangeError) as exc_info:
        exchange_code_for_token("1:missing-nonce.valid", "code")

    assert exc_info.value.reason == "pkce_verifier_not_found"


@patch("app.services.google_oauth_service._ensure_runtime_config")
@patch("app.services.google_oauth_service._consume_code_verifier", return_value="stored-verifier")
@patch("app.services.google_oauth_service._verify_state", return_value=(1, "nonce-123"))
@patch("app.services.google_oauth_service.GmailService")
@patch("app.services.google_oauth_service.build")
@patch("app.services.google_oauth_service.Flow.from_client_config")
def test_exchange_code_for_token_uses_stored_pkce_verifier(
    mock_flow_factory,
    mock_build,
    mock_gmail_service,
    _mock_verify,
    _mock_consume_verifier,
    _mock_runtime_config,
):
    mock_flow = MagicMock()
    mock_flow.credentials = object()
    mock_flow_factory.return_value = mock_flow

    mock_oauth2 = MagicMock()
    mock_oauth2.userinfo.return_value.get.return_value.execute.return_value = {"email": "user@example.com"}
    mock_build.return_value = mock_oauth2

    user_id = exchange_code_for_token("1:nonce-123.valid", "code")

    assert user_id == 1
    assert mock_flow.code_verifier == "stored-verifier"
    mock_flow.fetch_token.assert_called_once_with(code="code")
    mock_gmail_service.return_value.save_token_for_user.assert_called_once()
