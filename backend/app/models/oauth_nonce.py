"""Postgres-backed store for consumed OAuth state nonces.

Replaces the in-memory dict previously used in ``canvas_oauth.py`` so replay
protection holds across multiple worker processes.
"""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OAuthConsumedNonce(Base):
    __tablename__ = "oauth_consumed_nonces"

    nonce: Mapped[str] = mapped_column(String(128), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
