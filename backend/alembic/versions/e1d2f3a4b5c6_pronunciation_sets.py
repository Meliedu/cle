"""pronunciation_sets / items / folders tables

Revision ID: e1d2f3a4b5c6
Revises: c8f5e2a4b6d3
Create Date: 2026-04-27 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e1d2f3a4b5c6"
down_revision: Union[str, None] = "c8f5e2a4b6d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pronunciation_folders",
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
            sa.ForeignKey("pronunciation_folders.id", ondelete="SET NULL"),
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
        "ix_pronunciation_folders_course_id_parent_id",
        "pronunciation_folders",
        ["course_id", "parent_id"],
    )

    op.create_table(
        "pronunciation_sets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "course_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "is_published",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "folder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pronunciation_folders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "difficulty",
            sa.String(length=10),
            nullable=False,
            server_default="medium",
        ),
        sa.Column("language", sa.String(length=20), nullable=False),
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
        "ix_pronunciation_sets_course_id",
        "pronunciation_sets",
        ["course_id"],
    )
    op.create_index(
        "ix_pronunciation_sets_folder_id",
        "pronunciation_sets",
        ["folder_id"],
    )

    op.create_table(
        "pronunciation_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "pronunciation_set_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pronunciation_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(length=1000), nullable=False),
        sa.Column("phonetic", sa.String(length=500), nullable=True),
        sa.Column("translation", sa.String(length=1000), nullable=True),
        sa.Column("tips", sa.String(length=2000), nullable=True),
        sa.Column("item_type", sa.String(length=10), nullable=False),
        sa.Column(
            "difficulty",
            sa.String(length=10),
            nullable=False,
            server_default="medium",
        ),
        sa.Column(
            "source_chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chunks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_pronunciation_items_set_idx",
        "pronunciation_items",
        ["pronunciation_set_id", "item_index"],
    )

    op.create_table(
        "pronunciation_set_documents",
        sa.Column(
            "pronunciation_set_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pronunciation_sets.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("pronunciation_set_documents")
    op.drop_index("ix_pronunciation_items_set_idx", table_name="pronunciation_items")
    op.drop_table("pronunciation_items")
    op.drop_index("ix_pronunciation_sets_folder_id", table_name="pronunciation_sets")
    op.drop_index("ix_pronunciation_sets_course_id", table_name="pronunciation_sets")
    op.drop_table("pronunciation_sets")
    op.drop_index(
        "ix_pronunciation_folders_course_id_parent_id",
        table_name="pronunciation_folders",
    )
    op.drop_table("pronunciation_folders")
