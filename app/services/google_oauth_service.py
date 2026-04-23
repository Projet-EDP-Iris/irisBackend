"""
Google OAuth 2.0 flow for Gmail + Calendar integration.

Flow:
  1. Frontend calls GET /api/v1/auth/google (with Bearer token)
     → Backend returns {"auth_url": "https://accounts.google.com/o/oauth2/auth?..."}
  2. Frontend opens the URL in the browser
  3. User grants permission on Google's page
  4. Google redirects to /api/v1/auth/google/callback?code=...&state=...
  5. Backend exchanges code for tokens, saves to tokens/gmail_user_{id}.json
  6. GET /api/v1/emails now works for this user

The `state` parameter is an HMAC-signed string containing the user_id to prevent CSRF.
"""
import hashlib
import hmac
import json
import os
from pathlib import Path
from secrets import choice, token_urlsafe
from string import ascii_letters, digits
from time import time

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from app.core.config import settings
from app.services.gmail_service import SCOPES, TOKENS_DIR, GmailService


class GoogleOAuthExchangeError(RuntimeError):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


PKCE_VERIFIER_TTL_SECONDS = 600
_CODE_VERIFIER_ALPHABET = ascii_letters + digits + "-._~"


def _get_credentials_resolved_path() -> Path:
    configured_path = Path(settings.GMAIL_CREDENTIALS_PATH).expanduser()
    return configured_path if configured_path.is_absolute() else Path.cwd() / configured_path


def _get_pkce_store_path() -> Path:
    tokens_dir = Path(TOKENS_DIR)
    resolved_tokens_dir = tokens_dir if tokens_dir.is_absolute() else Path.cwd() / tokens_dir
    return resolved_tokens_dir / ".google_oauth_pkce.json"


def _load_pkce_store() -> dict[str, dict[str, float | str]]:
    store_path = _get_pkce_store_path()
    if not store_path.exists():
        return {}

    try:
        data = json.loads(store_path.read_text())
    except Exception:
        return {}

    if not isinstance(data, dict):
        return {}

    return data


def _save_pkce_store(store: dict[str, dict[str, float | str]]) -> None:
    store_path = _get_pkce_store_path()
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(json.dumps(store))


def _prune_expired_pkce_store(
    store: dict[str, dict[str, float | str]],
    now: float | None = None,
) -> dict[str, dict[str, float | str]]:
    current_time = now if now is not None else time()
    return {
        nonce: entry
        for nonce, entry in store.items()
        if isinstance(entry, dict)
        and isinstance(entry.get("expires_at"), (int, float))
        and float(entry["expires_at"]) > current_time
        and isinstance(entry.get("code_verifier"), str)
    }


def _store_code_verifier(nonce: str, code_verifier: str) -> None:
    store = _prune_expired_pkce_store(_load_pkce_store())
    now = time()
    store[nonce] = {
        "code_verifier": code_verifier,
        "created_at": now,
        "expires_at": now + PKCE_VERIFIER_TTL_SECONDS,
    }
    _save_pkce_store(store)


def _consume_code_verifier(nonce: str) -> str | None:
    store = _prune_expired_pkce_store(_load_pkce_store())
    entry = store.pop(nonce, None)
    _save_pkce_store(store)
    if not entry:
        return None
    code_verifier = entry.get("code_verifier")
    return code_verifier if isinstance(code_verifier, str) else None


def _generate_state_nonce() -> str:
    return token_urlsafe(18)


def _generate_code_verifier(length: int = 96) -> str:
    return "".join(choice(_CODE_VERIFIER_ALPHABET) for _ in range(length))


def get_google_oauth_runtime_diagnostics() -> dict[str, str | bool | None]:
    resolved_path = _get_credentials_resolved_path()
    pkce_store_path = _get_pkce_store_path()
    settings_source = "environment" if os.getenv("DATABASE_URL") else ".env"
    return {
        "settings_source": settings_source,
        "cwd": str(Path.cwd()),
        "redirect_uri": settings.GMAIL_REDIRECT_URI,
        "credentials_path": settings.GMAIL_CREDENTIALS_PATH,
        "credentials_resolved_path": str(resolved_path),
        "credentials_exists": resolved_path.exists(),
        "pkce_store_path": str(pkce_store_path),
        "pkce_store_exists": pkce_store_path.exists(),
        "secret_key_configured": bool(settings.SECRET_KEY),
    }


def _ensure_runtime_config() -> None:
    if not settings.GMAIL_REDIRECT_URI:
        raise GoogleOAuthExchangeError(
            "missing_redirect_uri",
            "GMAIL_REDIRECT_URI is not configured for Google OAuth.",
        )

    resolved_path = _get_credentials_resolved_path()
    if not resolved_path.exists():
        raise GoogleOAuthExchangeError(
            "missing_credentials_file",
            f"Gmail OAuth credentials file not found: {resolved_path}",
        )


def _sign_state(user_id: int, nonce: str) -> str:
    payload = f"{user_id}:{nonce}"
    sig = hmac.new(settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _verify_state(state: str) -> tuple[int, str]:
    parts = state.split(".", 1)
    if len(parts) != 2:
        raise ValueError("Invalid state parameter")
    payload, sig = parts
    expected = hmac.new(settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise ValueError("State signature mismatch — possible CSRF")
    payload_parts = payload.split(":", 1)
    if len(payload_parts) != 2:
        raise ValueError("Invalid state payload")
    user_id_str, nonce = payload_parts
    if not nonce:
        raise ValueError("Missing state nonce")
    return int(user_id_str), nonce


def get_auth_url(user_id: int) -> str:
    """Build the Google OAuth consent URL for the given user."""
    _ensure_runtime_config()
    try:
        flow = Flow.from_client_secrets_file(
            settings.GMAIL_CREDENTIALS_PATH,
            scopes=SCOPES,
            redirect_uri=settings.GMAIL_REDIRECT_URI,
        )
    except GoogleOAuthExchangeError:
        raise
    except Exception as exc:
        raise GoogleOAuthExchangeError(
            "oauth_client_config_invalid",
            "Google OAuth client configuration could not be loaded.",
        ) from exc
    nonce = _generate_state_nonce()
    flow.code_verifier = _generate_code_verifier()
    url, _ = flow.authorization_url(
        state=_sign_state(user_id, nonce),
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    _store_code_verifier(nonce, flow.code_verifier)
    return url


def exchange_code_for_token(state: str, code: str) -> int:
    """
    Exchange an authorization code for Google credentials and persist them.
    Returns the user_id extracted from the verified state parameter.
    """
    try:
        user_id, nonce = _verify_state(state)
    except Exception as exc:
        raise GoogleOAuthExchangeError(
            "state_verification_failed",
            "Google OAuth state verification failed.",
        ) from exc

    _ensure_runtime_config()

    try:
        flow = Flow.from_client_secrets_file(
            settings.GMAIL_CREDENTIALS_PATH,
            scopes=SCOPES,
            redirect_uri=settings.GMAIL_REDIRECT_URI,
            state=state,
        )
    except GoogleOAuthExchangeError:
        raise
    except Exception as exc:
        raise GoogleOAuthExchangeError(
            "oauth_client_config_invalid",
            "Google OAuth client configuration could not be loaded.",
        ) from exc

    code_verifier = _consume_code_verifier(nonce)
    if not code_verifier:
        raise GoogleOAuthExchangeError(
            "pkce_verifier_not_found",
            "Google OAuth PKCE verifier was missing or expired.",
        )
    flow.code_verifier = code_verifier

    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        raise GoogleOAuthExchangeError(
            "token_exchange_failed",
            "Google OAuth token exchange failed.",
        ) from exc

    creds: Credentials = flow.credentials

    try:
        oauth2_service = build("oauth2", "v2", credentials=creds)
        user_info = oauth2_service.userinfo().get().execute()
    except Exception as exc:
        raise GoogleOAuthExchangeError(
            "userinfo_fetch_failed",
            "Google OAuth userinfo lookup failed.",
        ) from exc
    gmail_email: str | None = user_info.get("email")

    try:
        GmailService().save_token_for_user(user_id, creds, gmail_email)
    except Exception as exc:
        raise GoogleOAuthExchangeError(
            "token_persist_failed",
            "Google OAuth token could not be saved.",
        ) from exc
    return user_id
