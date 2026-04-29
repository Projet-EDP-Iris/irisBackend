from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Fernet:
    from app.core.config import settings
    key = settings.SECRET_ENCRYPTION_KEY or ""
    if not key:
        raise RuntimeError(
            "SECRET_ENCRYPTION_KEY is not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode())


def encrypt(plain: str) -> str:
    """Encrypt a plain-text string. Returns a base64 token safe to store in the DB."""
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a Fernet token back to the original plain-text string."""
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Failed to decrypt value — key mismatch or corrupted token") from exc
