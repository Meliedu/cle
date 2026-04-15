"""quiz_folders.purpose + flashcard_folders + flashcard_sets.folder_id

Revision ID: b3f94e2a1c07
Revises: a7e2d91c4b6f
Create Date: 2026-04-15 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b3f94e2a1c07"
down_revision: Union[str, None] = "a7e2d91c4b6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- quiz_folders.purpose ----------------------------------------
    # All existing quiz_folders rows were created via the live-quiz bank UI,
    # so backfill them to 'live'. New folders can be 'after_class' too.
    op.add_column(
        "quiz_folders",
        sa.Column(
            "purpose",
            sa.String(length=20),
            nullable=False,
            server_default="live",
        ),
    )
    op.create_check_constraint(
        "ck_quiz_folders_purpose_valid",
        "quiz_folders",
        "purpose IN ('after_class', 'live')",
    )
    op.create_index(
        "ix_quiz_folders_course_id_purpose",
        "quiz_folders",
        ["course_id", "purpose"],
    )

    # ---- flashcard_folders table ------------------------------------
    op.create_table(
        "flashcard_folders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "course_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("flashcard_folders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_flashcard_folders_course_id_parent_id",
        "flashcard_folders",
        ["course_id", "parent_id"],
    )

    # ---- flashcard_sets.folder_id -----------------------------------
    op.add_column(
        "flashcard_sets",
        sa.Column("folder_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_flashcard_sets_folder_id",
        "flashcard_sets",
        "flashcard_folders",
        ["folder_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_flashcard_sets_folder_id",
        "flashcard_sets",
        ["folder_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_flashcard_sets_folder_id", table_name="flashcard_sets")
    op.drop_constraint(
        "fk_flashcard_sets_folder_id", "flashcard_sets", type_="foreignkey"
    )
    op.drop_column("flashcard_sets", "folder_id")
    op.drop_index(
        "ix_flashcard_folders_course_id_parent_id", table_name="flashcard_folders"
    )
    op.drop_table("flashcard_folders")
    op.drop_index("ix_quiz_folders_course_id_purpose", table_name="quiz_folders")
    op.drop_constraint(
        "ck_quiz_folders_purpose_valid", "quiz_folders", type_="check"
    )
    op.drop_column("quiz_folders", "purpose")
