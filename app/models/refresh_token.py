from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from .base import Base, TimestampMixin


class RefreshToken(Base, TimestampMixin):
    """Long-lived token issued at login when the user checks "remember me",
    exchanged for a new short-lived access token without re-entering credentials.

    Kept as its own table (rather than a new AuthToken.token_type value) so a
    new deployment gets it for free via create_all() -- adding a value to
    AuthToken's native Postgres enum would need a real ALTER TYPE migration,
    which this repo has no infrastructure for.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user = relationship("User", backref=backref("refresh_tokens", cascade="all, delete-orphan"))
