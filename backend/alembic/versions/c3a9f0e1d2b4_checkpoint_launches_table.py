"""checkpoint_launches table (no RLS)

Revision ID: c3a9f0e1d2b4
Revises: b2e4d8f1a067
Create Date: 2026-07-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c3a9f0e1d2b4'
down_revision: Union[str, None] = 'b2e4d8f1a067'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # checkpoint_launches — an operational / teacher-owned QR-launch table (P3
    # Task 4, Decision 3). Unlike checkpoint_responses / attendance_records this
    # is NOT student-owned: it carries the signed launch token (minted in T9),
    # not per-student data, so it gets NO RLS and is guarded at the endpoint
    # layer. status is active|closed. A partial unique index on
    # (checkpoint_id) WHERE status='active' enforces a single active launch per
    # checkpoint; a rotate closes the prior launch then issues a fresh active row.
    op.create_table(
        "checkpoint_launches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "checkpoint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("checkpoints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "meeting_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("course_meetings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("jti", sa.String(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "launched_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('active','closed')",
            name="ck_checkpoint_launches_status_valid",
        ),
    )
    # Single active launch per checkpoint (Decision 3). Partial unique index so
    # closed rows are excluded and rotation never trips the constraint.
    op.create_index(
        "uq_checkpoint_launches_one_active",
        "checkpoint_launches",
        ["checkpoint_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    # meeting_id lookup index for teacher-side launch reads (parallel to
    # ix_attendance_records_meeting_id).
    op.create_index(
        "ix_checkpoint_launches_meeting_id",
        "checkpoint_launches",
        ["meeting_id"],
    )
    # No RLS — operational/teacher-owned (Decision 3).


def downgrade() -> None:
    op.drop_index(
        "ix_checkpoint_launches_meeting_id", table_name="checkpoint_launches"
    )
    op.drop_index(
        "uq_checkpoint_launches_one_active", table_name="checkpoint_launches"
    )
    op.drop_table("checkpoint_launches")
