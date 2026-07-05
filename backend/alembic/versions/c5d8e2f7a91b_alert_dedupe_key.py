"""instructor_alerts dedupe_key for cohort object identity

Revision ID: c5d8e2f7a91b
Revises: d9f4e8b1c2a7
Create Date: 2026-05-10

Cohort alerts share ``(course_id, alert_type, target_user_id IS NULL)`` and
the partial unique index ``uq_instructor_alerts_open_idempotent`` collapses
distinct concepts/quizzes/assignments under the same key, hiding multiple
real alerts of the same type. Add a ``dedupe_key`` column carrying the
affected object identity (e.g. ``concept:<uuid>`` or ``quiz:<uuid>``) and
make the partial unique index include it. Per-student alerts continue to
dedupe by ``target_user_id`` with ``dedupe_key=''``.

NULLS NOT DISTINCT (PG15+) lets cohort rows with ``target_user_id IS NULL``
collide on the same ``(course, type, dedupe_key)`` instead of always being
treated as unique by NULL-distinct semantics.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c5d8e2f7a91b"
down_revision: Union[str, None] = "d9f4e8b1c2a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "instructor_alerts",
        sa.Column(
            "dedupe_key",
            sa.String(120),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )

    op.drop_index(
        "uq_instructor_alerts_open_idempotent", table_name="instructor_alerts"
    )
    op.create_index(
        "uq_instructor_alerts_open_idempotent",
        "instructor_alerts",
        ["course_id", "alert_type", "target_user_id", "dedupe_key"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
        postgresql_nulls_not_distinct=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_instructor_alerts_open_idempotent", table_name="instructor_alerts"
    )
    op.create_index(
        "uq_instructor_alerts_open_idempotent",
        "instructor_alerts",
        ["course_id", "alert_type", "target_user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.drop_column("instructor_alerts", "dedupe_key")
