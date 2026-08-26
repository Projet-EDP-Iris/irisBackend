"""
Unit tests for app/services/resend_service.py (SMTP reply path).

All network calls are mocked — no real SMTP connection is made.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.services.resend_service import ReplyRequest, send_reply


def _make_req(**kwargs) -> ReplyRequest:
    defaults = {
        "to": "recipient@example.com",
        "subject": "Meeting tomorrow",
        "text": "Sounds good, see you then.",
        "rfc_message_id": "<original@mail.example.com>",
        "attachments": [],
    }
    defaults.update(kwargs)
    return ReplyRequest(**defaults)


def _mock_smtp():
    """Return a MagicMock SMTP server wired as a context manager."""
    server = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=server)
    ctx.__exit__ = MagicMock(return_value=None)
    return ctx, server


class TestSendReply:
    @patch("app.services.resend_service.settings")
    def test_raises_when_no_credentials(self, mock_settings):
        """Missing SMTP credentials → ValueError before any network call."""
        mock_settings.SMTP_USERNAME = None
        mock_settings.SMTP_PASSWORD = "pw"

        with pytest.raises(ValueError, match="SMTP_USERNAME"):
            send_reply(_make_req())

    @patch("app.services.resend_service.settings")
    @patch("app.services.resend_service.smtplib.SMTP")
    def test_sends_reply_with_threading_headers(self, mock_smtp_cls, mock_settings):
        """rfc_message_id → In-Reply-To and References headers are set."""
        mock_settings.SMTP_USERNAME = "user@iris.com"
        mock_settings.SMTP_PASSWORD = "pw"
        mock_settings.SMTP_FROM_EMAIL = "iris@iris.com"
        mock_settings.SMTP_HOST = "smtp.gmail.com"
        mock_settings.SMTP_PORT = 587
        mock_settings.SMTP_USE_TLS = True

        ctx, server = _mock_smtp()
        mock_smtp_cls.return_value = ctx

        result = send_reply(_make_req())

        # Must have called starttls (TLS=True)
        server.starttls.assert_called_once()
        server.login.assert_called_once_with("user@iris.com", "pw")
        server.sendmail.assert_called_once()

        _, (from_addr, to_addr, raw_msg), _ = server.sendmail.mock_calls[0]
        assert from_addr == "iris@iris.com"
        assert to_addr == "recipient@example.com"
        assert "In-Reply-To: <original@mail.example.com>" in raw_msg
        assert "References: <original@mail.example.com>" in raw_msg

        # Returns a synthetic RFC Message-ID
        assert result.startswith("<smtp-reply-")
        assert result.endswith("@iris>")

    @patch("app.services.resend_service.settings")
    @patch("app.services.resend_service.smtplib.SMTP")
    def test_no_threading_headers_when_no_rfc_id(self, mock_smtp_cls, mock_settings):
        """rfc_message_id=None → no In-Reply-To/References headers in the message."""
        mock_settings.SMTP_USERNAME = "user@iris.com"
        mock_settings.SMTP_PASSWORD = "pw"
        mock_settings.SMTP_FROM_EMAIL = "iris@iris.com"
        mock_settings.SMTP_HOST = "smtp.gmail.com"
        mock_settings.SMTP_PORT = 587
        mock_settings.SMTP_USE_TLS = False

        ctx, server = _mock_smtp()
        mock_smtp_cls.return_value = ctx

        send_reply(_make_req(rfc_message_id=None))

        server.starttls.assert_not_called()
        _, (_, _, raw_msg), _ = server.sendmail.mock_calls[0]
        assert "In-Reply-To" not in raw_msg
        assert "References" not in raw_msg

    @patch("app.services.resend_service.settings")
    @patch("app.services.resend_service.smtplib.SMTP")
    def test_adds_re_prefix_to_subject_if_missing(self, mock_smtp_cls, mock_settings):
        """Subject without 're:' prefix → 'Re: ' is prepended."""
        mock_settings.SMTP_USERNAME = "u"
        mock_settings.SMTP_PASSWORD = "p"
        mock_settings.SMTP_FROM_EMAIL = "from@iris.com"
        mock_settings.SMTP_HOST = "smtp.gmail.com"
        mock_settings.SMTP_PORT = 587
        mock_settings.SMTP_USE_TLS = False

        ctx, server = _mock_smtp()
        mock_smtp_cls.return_value = ctx

        send_reply(_make_req(subject="Lunch plans"))

        _, (_, _, raw_msg), _ = server.sendmail.mock_calls[0]
        assert "Subject: Re: Lunch plans" in raw_msg

    @patch("app.services.resend_service.settings")
    @patch("app.services.resend_service.smtplib.SMTP")
    def test_does_not_double_re_prefix(self, mock_smtp_cls, mock_settings):
        """Subject already starting with 're:' → no double prefix."""
        mock_settings.SMTP_USERNAME = "u"
        mock_settings.SMTP_PASSWORD = "p"
        mock_settings.SMTP_FROM_EMAIL = "from@iris.com"
        mock_settings.SMTP_HOST = "smtp.gmail.com"
        mock_settings.SMTP_PORT = 587
        mock_settings.SMTP_USE_TLS = False

        ctx, server = _mock_smtp()
        mock_smtp_cls.return_value = ctx

        send_reply(_make_req(subject="Re: Lunch plans"))

        _, (_, _, raw_msg), _ = server.sendmail.mock_calls[0]
        assert "Subject: Re: Lunch plans" in raw_msg
        assert "Re: Re:" not in raw_msg

    @patch("app.services.resend_service.settings")
    @patch("app.services.resend_service.smtplib.SMTP")
    def test_sends_attachment(self, mock_smtp_cls, mock_settings):
        """Attachments are included in the MIME message."""
        mock_settings.SMTP_USERNAME = "u"
        mock_settings.SMTP_PASSWORD = "p"
        mock_settings.SMTP_FROM_EMAIL = "from@iris.com"
        mock_settings.SMTP_HOST = "smtp.gmail.com"
        mock_settings.SMTP_PORT = 587
        mock_settings.SMTP_USE_TLS = False

        ctx, server = _mock_smtp()
        mock_smtp_cls.return_value = ctx

        send_reply(_make_req(attachments=[("file.txt", b"hello")]))

        _, (_, _, raw_msg), _ = server.sendmail.mock_calls[0]
        assert "file.txt" in raw_msg

    @patch("app.services.resend_service.settings")
    @patch("app.services.resend_service.smtplib.SMTP")
    def test_synthetic_id_is_unique(self, mock_smtp_cls, mock_settings):
        """Each send_reply call returns a different synthetic ID (uses uuid4)."""
        mock_settings.SMTP_USERNAME = "u"
        mock_settings.SMTP_PASSWORD = "p"
        mock_settings.SMTP_FROM_EMAIL = "from@iris.com"
        mock_settings.SMTP_HOST = "smtp.gmail.com"
        mock_settings.SMTP_PORT = 587
        mock_settings.SMTP_USE_TLS = False

        ctx1, _ = _mock_smtp()
        ctx2, _ = _mock_smtp()
        mock_smtp_cls.side_effect = [ctx1, ctx2]

        id1 = send_reply(_make_req())
        id2 = send_reply(_make_req())
        assert id1 != id2
