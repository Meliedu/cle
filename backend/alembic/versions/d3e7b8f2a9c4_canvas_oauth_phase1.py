"""canvas oauth phase 1

Revision ID: d3e7b8f2a9c4
Revises: c2e5f8a1b3d9
Create Date: 2026-04-14

Adds per-user Canvas OAuth credential storage, pending-enrollment pre-provisioning,
sync event log, and Canvas-origin tracking on documents. Replaces the legacy
per-course PAT flow (existing canvas_integrations rows are wiped).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "d3e7b8f2a9c4"
down_revision: Union[str, None] = "c2e5f8a1b3d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DELETE FROM canvas_integrations")

    op.create_table(
        "canvas_user_credentials",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("canvas_base_url", sa.String(500), nullable=False),
        sa.Column("canvas_user_id", sa.String(100), nullable=False),
        sa.Column("access_token_encrypted", sa.String(1000), nullable=False),
        sa.Column("refresh_token_encrypted", sa.String(1000), nullable=False),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "pending_enrollments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "course_id",
            UUID(as_uuid=True),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("canvas_user_id", sa.String(100), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("invited_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("course_id", "email", name="uq_pending_enrollments_course_email"),
    )
    op.create_index("ix_pending_enrollments_email", "pending_enrollments", ["email"])

    op.create_table(
        "canvas_sync_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "course_id",
            UUID(as_uuid=True),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_canvas_sync_events_course_created",
        "canvas_sync_events",
        ["course_id", "created_at"],
    )

    op.add_column(
        "canvas_integrations",
        sa.Column(
            "connected_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
    )
    op.add_column("canvas_integrations", sa.Column("last_roster_sync_at", sa.DateTime(timezone=True)))
    op.add_column("canvas_integrations", sa.Column("last_file_scan_at", sa.DateTime(timezone=True)))
    op.drop_column("canvas_integrations", "access_token_encrypted")

    op.add_column("documents", sa.Column("canvas_file_id", sa.String(100)))
    op.add_column("documents", sa.Column("canvas_file_etag", sa.String(100)))
    op.create_index(
        "idx_documents_canvas_file",
        "documents",
        ["course_id", "canvas_file_id"],
        unique=True,
        postgresql_where=sa.text("canvas_file_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_documents_canvas_file", table_name="documents")
    op.drop_column("documents", "canvas_file_etag")
    op.drop_column("documents", "canvas_file_id")

    op.add_column("canvas_integrations", sa.Column("access_token_encrypted", sa.String(500)))
    op.drop_column("canvas_integrations", "last_file_scan_at")
    op.drop_column("canvas_integrations", "last_roster_sync_at")
    op.drop_column("canvas_integrations", "connected_by_user_id")

    op.drop_index("ix_canvas_sync_events_course_created", table_name="canvas_sync_events")
    op.drop_table("canvas_sync_events")
    op.drop_index("ix_pending_enrollments_email", table_name="pending_enrollments")
    op.drop_table("pending_enrollments")
    op.drop_table("canvas_user_credentials")
