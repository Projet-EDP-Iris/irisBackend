from sqlalchemy import JSON, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(225), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="regular")
    has_subscription: Mapped[bool] = mapped_column(Boolean, default=False)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    profile_icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bank_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    oauth_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    require_password_reset: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Calendar integration
    calendar_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Legacy single-provider field — kept for backwards compatibility
    calendar_providers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # List of active providers e.g. ["google", "apple", "outlook"]
    apple_caldav_user: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Apple ID email address (e.g. dan@icloud.com)
    apple_caldav_password: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # App Password from appleid.apple.com — stored Fernet-encrypted

    # Gmail OAuth — stored Fernet-encrypted
    gmail_oauth_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    gmail_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Outlook OAuth — stored Fernet-encrypted
    outlook_oauth_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    outlook_email: Mapped[str | None] = mapped_column(String(255), nullable=True)


