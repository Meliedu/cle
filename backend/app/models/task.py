from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class Task(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "tasks"

    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    # Server-side only. Carries "{ExceptionClass}: {message}" for triage and
    # must never be serialised to a client; the API exposes ``error_code``.
    error_message: Mapped[str | None] = mapped_column(String)
    # Typed, user-safe failure classification (``SourceFailureCode``). The UI
    # maps this to copy naming the object, consequence, preserved work, and
    # next action.
    error_code: Mapped[str | None] = mapped_column(String(40))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
