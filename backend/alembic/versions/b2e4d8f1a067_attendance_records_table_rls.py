"""attendance_records table + RLS

Revision ID: b2e4d8f1a067
Revises: a1f3c7e29b04
Create Date: 2026-07-07 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b2e4d8f1a067'
down_revision: Union[str, None] = 'a1f3c7e29b04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # attendance_records — a student-owned meeting-attendance table (P3 Task 3,
    # Decision 2). Participation ONLY, never mastery. status is
    # present|late|excused|absent; source is qr|manual_override. The override
    # fields are NULL for QR check-ins and set only on teacher manual override.
    # One row per (meeting_id, user_id) — a repeat scan is an idempotent no-op.
    op.create_table(
        "attendance_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "meeting_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("course_meetings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("override_reason", sa.String(), nullable=True),
        sa.Column(
            "override_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "checked_in_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('present','late','excused','absent')",
            name="ck_attendance_records_status_valid",
        ),
        sa.CheckConstraint(
            "source IN ('qr','manual_override')",
            name="ck_attendance_records_source_valid",
        ),
        sa.UniqueConstraint(
            "meeting_id", "user_id", name="uq_attendance_records_meeting_user"
        ),
    )
    # meeting_id lookup index for teacher-side roster reads. (The unique
    # constraint above already indexes the (meeting_id, user_id) prefix, but the
    # roster read filters by meeting_id alone; keep an explicit index parallel to
    # ix_checkpoint_responses_checkpoint_id.)
    op.create_index(
        "ix_attendance_records_meeting_id",
        "attendance_records",
        ["meeting_id"],
    )

    # RLS — student-owned table (Decision 2; pattern 28236be3d7b3 / d94257fc717c
    # / a1f3c7e29b04). Owner is user_id; enforcement runs under non-superuser
    # meli_app (postgres has BYPASSRLS, set in 28236be3d7b3). The
    # app.current_user_id GUC is set per request by deps.py::get_current_user via
    # set_config(...).
    op.execute("ALTER TABLE attendance_records ENABLE ROW LEVEL SECURITY")
    op.execute(
        "DROP POLICY IF EXISTS attendance_records_owner_isolation "
        "ON attendance_records"
    )
    op.execute(
        "CREATE POLICY attendance_records_owner_isolation ON attendance_records "
        "FOR ALL "
        "USING (user_id = current_setting('app.current_user_id', true)::uuid) "
        "WITH CHECK (user_id = current_setting('app.current_user_id', true)::uuid)"
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS attendance_records_owner_isolation "
        "ON attendance_records"
    )
    op.execute("ALTER TABLE attendance_records DISABLE ROW LEVEL SECURITY")
    op.drop_index(
        "ix_attendance_records_meeting_id", table_name="attendance_records"
    )
    op.drop_table("attendance_records")
