"""checkpoint_responses table + RLS

Revision ID: a1f3c7e29b04
Revises: d94257fc717c
Create Date: 2026-07-07 10:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1f3c7e29b04'
down_revision: Union[str, None] = 'd94257fc717c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # checkpoint_responses — a student-owned card-answer table (P3 Task 2,
    # Decision 2). confidence is the −2..+2 scale (NULL for final_comments text
    # cards); status is on_time/late derived at submission. One row per
    # (card_id, user_id) — a resubmit upserts in place.
    op.create_table(
        "checkpoint_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "checkpoint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("checkpoints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "card_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("checkpoint_cards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("text_response", sa.String(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "submitted_at",
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
            "confidence IS NULL OR confidence BETWEEN -2 AND 2",
            name="ck_checkpoint_responses_confidence_range",
        ),
        sa.CheckConstraint(
            "status IN ('on_time','late')",
            name="ck_checkpoint_responses_status_valid",
        ),
        sa.UniqueConstraint(
            "card_id", "user_id", name="uq_checkpoint_responses_card_user"
        ),
    )
    # checkpoint_id lookup index for teacher-side / checkpoint-scoped result reads.
    # (The unique constraint above already indexes the (card_id, user_id) prefix,
    # covering owner lookups.)
    op.create_index(
        "ix_checkpoint_responses_checkpoint_id",
        "checkpoint_responses",
        ["checkpoint_id"],
    )

    # RLS — student-owned table (Decision 2; pattern 28236be3d7b3 / d94257fc717c).
    # Owner is user_id; enforcement runs under non-superuser meli_app (postgres
    # has BYPASSRLS, set in 28236be3d7b3). The app.current_user_id GUC is set per
    # request by deps.py::get_current_user via set_config(...).
    op.execute("ALTER TABLE checkpoint_responses ENABLE ROW LEVEL SECURITY")
    op.execute(
        "DROP POLICY IF EXISTS checkpoint_responses_owner_isolation "
        "ON checkpoint_responses"
    )
    op.execute(
        "CREATE POLICY checkpoint_responses_owner_isolation ON checkpoint_responses "
        "FOR ALL "
        "USING (user_id = current_setting('app.current_user_id', true)::uuid) "
        "WITH CHECK (user_id = current_setting('app.current_user_id', true)::uuid)"
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS checkpoint_responses_owner_isolation "
        "ON checkpoint_responses"
    )
    op.execute("ALTER TABLE checkpoint_responses DISABLE ROW LEVEL SECURITY")
    op.drop_index(
        "ix_checkpoint_responses_checkpoint_id", table_name="checkpoint_responses"
    )
    op.drop_table("checkpoint_responses")
