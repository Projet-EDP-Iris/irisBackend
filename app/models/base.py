# file models/base.py

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, declarative_base, mapped_column

Base = declarative_base()

class TimestampMixin:
    created_at: Mapped[DateTime] = mapped_column(
            DateTime(timezone=True), server_default=func.now(), nullable=False
            )
    updated_at: Mapped[DateTime] = mapped_column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
            )
