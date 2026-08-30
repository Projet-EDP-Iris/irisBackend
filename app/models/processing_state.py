from sqlalchemy import Boolean, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class ProcessingState(Base, TimestampMixin):
    """One row per user tracking whether Iris is actively processing mail.

    Only is_active is persisted here — total_emails/processed_emails/
    processed_by_category are computed on read from the Email table
    (see app/api/endpoints/processing_state.py) to avoid counter drift.
    """
    __tablename__ = "processing_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
