"""audit_events append-only audit table

Revision ID: c3f9a1d7b482
Revises: a1f3c8d5b2e7
Create Date: 2026-07-08 17:00:00.000000

P7 Task B2 (spec §8, Decision 4): ``audit_events`` is the NEW **general
append-only** audit log — every audited action (report approve/send/export,
memory decide, checkpoint publish, …) appends exactly one row via
``services/audit.py::record_audit_event``, inside the caller's transaction.
Mirrors the P5 ``grade_exports`` append-only shape: UUID PK + a plain
``created_at`` only — **NO ``updated_at``, NO soft-delete, NO update/delete
path.** ``grade_exports`` stays as the CSV-export-specific log; ``audit_events``
is the general log the H4 coverage check enumerates.

The ``actor_id`` FK carries **no ``ondelete``** (audit FK pattern) so the trail
outlives the acting user. The JSONB payload column is named ``metadata`` in the
DB (spec ``metadata JSONB``); the ORM attribute is ``event_metadata`` because
``metadata`` is reserved on the Declarative ``Base``.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c3f9a1d7b482'
down_revision: Union[str, None] = 'a1f3c8d5b2e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "course_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # No ondelete — audit FK pattern: the trail outlives the actor.
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("target_kind", sa.String(length=40), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_audit_events_course_id", "audit_events", ["course_id"])
    op.create_index(
        "ix_audit_events_target", "audit_events", ["target_kind", "target_id"]
    )
    # No RLS — course-scoped / teacher-owned (owner-guarded endpoints). No
    # soft-delete, no update/delete path — append-only audit log.


def downgrade() -> None:
    op.drop_index("ix_audit_events_target", table_name="audit_events")
    op.drop_index("ix_audit_events_course_id", table_name="audit_events")
    op.drop_table("audit_events")
