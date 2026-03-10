from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class DetectionFeedback(Base, TimestampMixin):
    __tablename__ = "detection_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[str] = mapped_column(String(512), index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_extraction: Mapped[str] = mapped_column(Text)
    corrections: Mapped[str] = mapped_column(Text)
