"""
Unit tests for app/core/encryption.py

These tests verify the encrypt/decrypt round-trip and error handling.
No external services involved — pure Python logic.
"""
import os

import pytest
from cryptography.fernet import Fernet

# Generate a fresh key per test run — no hardcoded secret in source.
_TEST_KEY = Fernet.generate_key().decode()
os.environ.setdefault("SECRET_ENCRYPTION_KEY", _TEST_KEY)

from app.core.encryption import decrypt, encrypt  # noqa: E402

TEST_SECRET_VALUE = "TEST_ENCRYPTION_VALUE_123"
TEST_REPEAT_VALUE = "TEST_REPEATABLE_INPUT_VALUE"
TEST_UNICODE_VALUE = "tëst-välüe-ünïcödé"
TEST_INVALID_TOKEN = "NOT_A_VALID_FERNET_TOKEN_TEST_VALUE"

# --- Round-trip ---

def test_encrypt_decrypt_round_trip():
    """Encrypting then decrypting must return the original value."""
    original = TEST_SECRET_VALUE
    assert decrypt(encrypt(original)) == original


def test_encrypt_produces_different_output_each_time():
    """Fernet uses a random IV, so two encryptions of the same value differ."""
    value = TEST_REPEAT_VALUE
    assert encrypt(value) != encrypt(value)


def test_decrypt_round_trip_with_unicode():
    """Non-ASCII passwords (accented characters, etc.) survive the round-trip."""
    original = TEST_UNICODE_VALUE
    assert decrypt(encrypt(original)) == original


# --- Error handling ---

def test_decrypt_raises_on_corrupted_token():
    """A tampered or garbage token must raise ValueError, not crash silently."""
    with pytest.raises(ValueError, match="Failed to decrypt"):
        decrypt(TEST_INVALID_TOKEN)


def test_decrypt_raises_on_empty_string():
    """An empty string must raise ValueError."""
    with pytest.raises(ValueError):
        decrypt("")


def test_encrypt_raises_when_key_missing(monkeypatch):
    """If SECRET_ENCRYPTION_KEY is unset, encrypt() must raise RuntimeError."""
    monkeypatch.delenv("SECRET_ENCRYPTION_KEY", raising=False)
    # Re-import to bypass the module-level cached key
    import importlib

    import app.core.encryption as enc_module
    importlib.reload(enc_module)
    with pytest.raises(RuntimeError, match="SECRET_ENCRYPTION_KEY"):
        enc_module.encrypt("anything")
    # Restore so other tests are unaffected
    os.environ["SECRET_ENCRYPTION_KEY"] = _TEST_KEY
    importlib.reload(enc_module)
