"""
Unit tests for app/services/email_service.py.

All SMTP calls are mocked — no real network connection is made.
Settings are patched per-test to isolate from the .env file.
"""
import smtplib
from unittest.mock import MagicMock, patch

import pytest

from app.services.email_service import (
    _send_smtp,
    send_password_reset_email,
    send_verification_email,
)

# ---------------------------------------------------------------------------
# _send_smtp — low-level SMTP helper
# ---------------------------------------------------------------------------


class TestSendSmtp:
    def _mock_smtp_server(self):
        """Return a mock SMTP server usable as a context manager."""
        server = MagicMock()
        return server

    @patch("app.services.email_service.settings")
    def test_raises_value_error_when_no_credentials(self, mock_settings):
        """Missing SMTP credentials must raise ValueError before any network call."""
        mock_settings.SMTP_USERNAME = None
        mock_settings.SMTP_PASSWORD = None

        with pytest.raises(ValueError, match="SMTP_USERNAME"):
            _send_smtp("dest@example.com", "Subject", "<p>body</p>")

    @patch("app.services.email_service.settings")
    @patch("app.services.email_service.smtplib.SMTP")
    def test_sends_email_with_tls(self, mock_smtp_cls, mock_settings):
        """With SMTP_USE_TLS=True, starttls must be called before login."""
        mock_settings.SMTP_USERNAME = "user@gmail.com"
        mock_settings.SMTP_PASSWORD = "app-password"
        mock_settings.SMTP_FROM_EMAIL = "noreply@iris-app.com"
        mock_settings.SMTP_HOST = "smtp.gmail.com"
        mock_settings.SMTP_PORT = 587
        mock_settings.SMTP_USE_TLS = True

        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=None)

        _send_smtp("dest@example.com", "Hello", "<p>hi</p>")

        mock_smtp_cls.assert_called_once_with("smtp.gmail.com", 587)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user@gmail.com", "app-password")
        mock_server.sendmail.assert_called_once()
        _, args, _ = mock_server.sendmail.mock_calls[0]
        assert args[0] == "noreply@iris-app.com"
        assert args[1] == "dest@example.com"

    @patch("app.services.email_service.settings")
    @patch("app.services.email_service.smtplib.SMTP")
    def test_sends_email_without_tls(self, mock_smtp_cls, mock_settings):
        """With SMTP_USE_TLS=False, starttls must NOT be called."""
        mock_settings.SMTP_USERNAME = "user@iris-app.com"
        mock_settings.SMTP_PASSWORD = "secret"
        mock_settings.SMTP_FROM_EMAIL = "noreply@iris-app.com"
        mock_settings.SMTP_HOST = "mail.iris-app.com"
        mock_settings.SMTP_PORT = 25
        mock_settings.SMTP_USE_TLS = False

        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=None)

        _send_smtp("dest@example.com", "Hi", "<p>body</p>")

        mock_server.starttls.assert_not_called()
        mock_server.login.assert_called_once()
        mock_server.sendmail.assert_called_once()


# ---------------------------------------------------------------------------
# send_password_reset_email
# ---------------------------------------------------------------------------


class TestSendPasswordResetEmail:
    @patch("app.services.email_service.settings")
    def test_skips_when_email_disabled(self, mock_settings):
        """EMAIL_ENABLED=False → no SMTP call, returns silently."""
        mock_settings.EMAIL_ENABLED = False

        with patch("app.services.email_service._send_smtp") as mock_send:
            send_password_reset_email("user@example.com", "tok123")
            mock_send.assert_not_called()

    @patch("app.services.email_service.settings")
    def test_calls_send_smtp_with_reset_url(self, mock_settings):
        """EMAIL_ENABLED=True → _send_smtp called with a URL containing the token."""
        mock_settings.EMAIL_ENABLED = True
        mock_settings.FRONTEND_URL = "http://localhost:5173"
        mock_settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 30

        with patch("app.services.email_service._send_smtp") as mock_send:
            send_password_reset_email("user@example.com", "tok123")

            mock_send.assert_called_once()
            _, (to, subject, html), _ = mock_send.mock_calls[0]
            assert to == "user@example.com"
            assert "password" in subject.lower()
            assert "tok123" in html
            assert "http://localhost:5173/reset-password" in html

    @patch("app.services.email_service.settings")
    def test_swallows_smtp_exception(self, mock_settings):
        """SMTP failure must be caught and logged — never re-raised to the caller."""
        mock_settings.EMAIL_ENABLED = True
        mock_settings.FRONTEND_URL = "http://localhost:5173"
        mock_settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 30

        with patch("app.services.email_service._send_smtp", side_effect=smtplib.SMTPException("err")):
            # Must not raise
            send_password_reset_email("user@example.com", "tok")


# ---------------------------------------------------------------------------
# send_verification_email
# ---------------------------------------------------------------------------


class TestSendVerificationEmail:
    @patch("app.services.email_service.settings")
    def test_skips_when_email_disabled(self, mock_settings):
        """EMAIL_ENABLED=False → no SMTP call."""
        mock_settings.EMAIL_ENABLED = False

        with patch("app.services.email_service._send_smtp") as mock_send:
            send_verification_email("user@example.com", "vtok")
            mock_send.assert_not_called()

    @patch("app.services.email_service.settings")
    def test_calls_send_smtp_with_verify_url(self, mock_settings):
        """EMAIL_ENABLED=True → _send_smtp called with URL containing the token."""
        mock_settings.EMAIL_ENABLED = True
        mock_settings.FRONTEND_URL = "https://iris-app.com"
        mock_settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS = 24

        with patch("app.services.email_service._send_smtp") as mock_send:
            send_verification_email("user@example.com", "vtok456")

            mock_send.assert_called_once()
            _, (to, subject, html), _ = mock_send.mock_calls[0]
            assert to == "user@example.com"
            assert "verif" in subject.lower()
            assert "vtok456" in html
            assert "https://iris-app.com/verify-email" in html

    @patch("app.services.email_service.settings")
    def test_swallows_smtp_exception(self, mock_settings):
        """SMTP failure must be caught and logged — never re-raised."""
        mock_settings.EMAIL_ENABLED = True
        mock_settings.FRONTEND_URL = "http://localhost:5173"
        mock_settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS = 24

        with patch("app.services.email_service._send_smtp", side_effect=ConnectionRefusedError("conn")):
            send_verification_email("user@example.com", "vtok")
