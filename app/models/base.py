# file models/base.py

from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import DateTime, func

Base = declarative_base()

class TimestampMixin:
    created_at: Mapped[DateTime] = mapped_column(
            DateTime(timezone=True), server_default=func.now(), nullable=False
            )
    updated_at: Mapped[DateTime] = mapped_column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
            )
