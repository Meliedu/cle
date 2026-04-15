"""quiz_folders table + quizzes.folder_id

Revision ID: a7e2d91c4b6f
Revises: f1c8a3b5d2e4
Create Date: 2026-04-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a7e2d91c4b6f"
down_revision: Union[str, None] = "f1c8a3b5d2e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quiz_folders",
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
            sa.ForeignKey("quiz_folders.id", ondelete="SET NULL"),
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
        "ix_quiz_folders_course_id_parent_id",
        "quiz_folders",
        ["course_id", "parent_id"],
    )

    op.add_column(
        "quizzes",
        sa.Column("folder_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_quizzes_folder_id",
        "quizzes",
        "quiz_folders",
        ["folder_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_quizzes_folder_id",
        "quizzes",
        ["folder_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_quizzes_folder_id", table_name="quizzes")
    op.drop_constraint("fk_quizzes_folder_id", "quizzes", type_="foreignkey")
    op.drop_column("quizzes", "folder_id")
    op.drop_index("ix_quiz_folders_course_id_parent_id", table_name="quiz_folders")
    op.drop_table("quiz_folders")
