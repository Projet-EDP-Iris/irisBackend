import logging
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.api.routes.auth_google as auth_google
from app.main import app
from app.services.google_oauth_service import GoogleOAuthExchangeError


client = TestClient(app)


def test_google_callback_redirects_to_emails_page_with_query_status(monkeypatch):
    monkeypatch.setattr(auth_google, "_FRONTEND_URL", "http://localhost:5173/")

    with patch("app.api.routes.auth_google.exchange_code_for_token") as mock_exchange:
        response = client.get(
            "/api/v1/auth/google/callback",
            params={"code": "abc", "state": "1.valid"},
            follow_redirects=False,
        )

    mock_exchange.assert_called_once_with(state="1.valid", code="abc")
    assert response.status_code == 307
    assert response.headers["location"] == "http://localhost:5173/?gmail=connected#/emails"


def test_google_callback_error_redirects_to_emails_page_with_query_status(monkeypatch):
    monkeypatch.setattr(auth_google, "_FRONTEND_URL", "http://localhost:5173")

    response = client.get(
        "/api/v1/auth/google/callback",
        params={"code": "abc", "state": "1.valid", "error": "access_denied"},
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == "http://localhost:5173/?gmail=error&gmail_reason=provider_error#/emails"


def test_google_callback_redirect_supports_file_frontend_targets(monkeypatch):
    monkeypatch.setattr(auth_google, "_FRONTEND_URL", "file:///Applications/Iris.app/Contents/Resources/app.asar/dist/index.html")

    with patch("app.api.routes.auth_google.exchange_code_for_token") as mock_exchange:
        response = client.get(
            "/api/v1/auth/google/callback",
            params={"code": "abc", "state": "1.valid"},
            follow_redirects=False,
        )

    mock_exchange.assert_called_once_with(state="1.valid", code="abc")
    assert response.status_code == 307
    assert response.headers["location"] == (
        "file:///Applications/Iris.app/Contents/Resources/app.asar/dist/index.html"
        "?gmail=connected#/emails"
    )


def test_google_callback_logs_and_redirects_with_reason_for_classified_failures(monkeypatch, caplog):
    monkeypatch.setattr(auth_google, "_FRONTEND_URL", "http://localhost:5173/")
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    with patch(
        "app.api.routes.auth_google.exchange_code_for_token",
        side_effect=GoogleOAuthExchangeError("token_exchange_failed", "Google OAuth token exchange failed."),
    ):
        with caplog.at_level(logging.ERROR):
            response = client.get(
                "/api/v1/auth/google/callback",
                params={"code": "abc", "state": "1.valid"},
                follow_redirects=False,
            )

    assert response.status_code == 307
    assert response.headers["location"] == (
        "http://localhost:5173/?gmail=error&gmail_reason=token_exchange_failed#/emails"
    )
    assert "Google OAuth callback failed reason=token_exchange_failed" in caplog.text


def test_google_callback_omits_reason_code_in_production(monkeypatch):
    monkeypatch.setattr(auth_google, "_FRONTEND_URL", "http://localhost:5173")
    monkeypatch.setenv("ENVIRONMENT", "production")

    with patch(
        "app.api.routes.auth_google.exchange_code_for_token",
        side_effect=GoogleOAuthExchangeError("token_exchange_failed", "Google OAuth token exchange failed."),
    ):
        response = client.get(
            "/api/v1/auth/google/callback",
            params={"code": "abc", "state": "1.valid"},
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert response.headers["location"] == "http://localhost:5173/?gmail=error#/emails"


def test_google_callback_redirects_with_pkce_reason(monkeypatch):
    monkeypatch.setattr(auth_google, "_FRONTEND_URL", "http://localhost:5173/")
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    with patch(
        "app.api.routes.auth_google.exchange_code_for_token",
        side_effect=GoogleOAuthExchangeError(
            "pkce_verifier_not_found",
            "Google OAuth PKCE verifier was missing or expired.",
        ),
    ):
        response = client.get(
            "/api/v1/auth/google/callback",
            params={"code": "abc", "state": "1.valid"},
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert response.headers["location"] == (
        "http://localhost:5173/?gmail=error&gmail_reason=pkce_verifier_not_found#/emails"
    )
