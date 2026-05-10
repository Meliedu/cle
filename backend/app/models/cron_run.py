from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CronRun(Base):
    """Durable cron watermark.

    One row per logical cron job (e.g. ``overdue``, ``decay``, ``alert``).
    ``last_success_at`` is advanced ONLY after the job body completes
    without raising; transient failures leave it unchanged so the next
    worker tick retries instead of waiting a full cadence interval.
    """

    __tablename__ = "cron_runs"

    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    last_success_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
