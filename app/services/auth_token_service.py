import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.auth_token import AuthToken, TokenType


def create_token(
    db: Session,
    user_id: int,
    token_type: TokenType,
    expires_minutes: int,
) -> str:
    """
    Invalidate existing active tokens of this type for the user, then create and
    persist a new single-use token. Caller is responsible for committing.
    """
    db.query(AuthToken).filter(
        AuthToken.user_id == user_id,
        AuthToken.token_type == token_type,
        AuthToken.used == False,  # noqa: E712
    ).update({"used": True})

    raw_token = secrets.token_urlsafe(32)
    auth_token = AuthToken(
        user_id=user_id,
        token=raw_token,
        token_type=token_type,
        expires_at=datetime.now(UTC) + timedelta(minutes=expires_minutes),
        used=False,
    )
    db.add(auth_token)
    db.flush()
    return raw_token


def consume_token(
    db: Session,
    raw_token: str,
    token_type: TokenType,
) -> AuthToken | None:
    """
    Return the AuthToken record if valid (exists, correct type, not used, not expired).
    Does NOT mark as used — caller does that after business logic succeeds.
    """
    now = datetime.now(UTC)
    return (
        db.query(AuthToken)
        .filter(
            AuthToken.token == raw_token,
            AuthToken.token_type == token_type,
            AuthToken.used == False,  # noqa: E712
            AuthToken.expires_at > now,
        )
        .first()
    )
