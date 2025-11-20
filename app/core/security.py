from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from jose import jwt, JWTError
from passlib.context import CryptContext

# Use Argon2 for OWASP-compliant password hashing
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def hash_password(plain: str) -> str:
    """Hash a plain text password using Argon2."""
    return pwd_context.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain text password against a hashed password."""
    return pwd_context.verify(plain, hashed)

def create_access_token(subject: str, data: Dict[str, Any], *, secret: str, algorithm: str, minutes: int) -> str:
    """Create a signed JWT access token for successful authentication."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
        **data,
    }
    return jwt.encode(payload, secret, algorithm=algorithm)

def decode_access_token(token: str, secret: str, algorithm: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT access token. Returns payload if valid, None otherwise."""
    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm])
        return payload
    except JWTError:
        return None
