import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken

REFRESH_TOKEN_EXPIRE_DAYS = 30


def create_refresh_token(db: Session, user_id: int) -> str:
    """Issue a new refresh token for the user. Caller is responsible for committing."""
    raw_token = secrets.token_urlsafe(32)
    db.add(RefreshToken(
        user_id=user_id,
        token=raw_token,
        expires_at=datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        revoked=False,
    ))
    db.flush()
    return raw_token


def consume_refresh_token(db: Session, raw_token: str) -> RefreshToken | None:
    """Return the RefreshToken record if valid (exists, not revoked, not expired).
    Does not revoke it — caller does that after deciding whether to rotate."""
    now = datetime.now(UTC)
    return (
        db.query(RefreshToken)
        .filter(
            RefreshToken.token == raw_token,
            RefreshToken.revoked == False,  # noqa: E712
            RefreshToken.expires_at > now,
        )
        .first()
    )
