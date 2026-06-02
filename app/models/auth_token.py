import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from .base import Base, TimestampMixin


class TokenType(str, enum.Enum):
    password_reset = "password_reset"
    email_verification = "email_verification"


class AuthToken(Base, TimestampMixin):
    __tablename__ = "auth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    token_type: Mapped[TokenType] = mapped_column(
        Enum(TokenType, name="tokentype"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user = relationship("User", backref=backref("auth_tokens", cascade="all, delete-orphan"))
