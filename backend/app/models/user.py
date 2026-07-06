from sqlalchemy import CheckConstraint, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('student', 'instructor')",
            name="ck_users_role_valid",
        ),
    )

    better_auth_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    # JSONB (not JSON) so PATCH /auth/me/preferences can merge submitted keys
    # atomically server-side with the `||` operator (no lost updates).
    notification_prefs: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
