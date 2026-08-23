from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class SyncState(Base, TimestampMixin):
    """Persists an incremental sync cursor per user/provider so repeat syncs
    (e.g. on every login) only fetch new/changed mail instead of re-listing
    the whole mailbox.

    cursor holds Gmail's historyId or Microsoft Graph's @odata.deltaLink,
    depending on provider. Unique per (user_id, provider) — a user can have
    both a Gmail and an Outlook sync cursor at once.
    """
    __tablename__ = "sync_state"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_sync_state_user_provider"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20))  # "gmail" | "outlook"
    cursor: Mapped[str | None] = mapped_column(String(2048), nullable=True)
