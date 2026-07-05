"""phase 1 curriculum + calendar + syllabus

Revision ID: d8c3a1e7f9b4
Revises: e1d2f3a4b5c6
Create Date: 2026-04-28

Adds curriculum spine, calendar (course_meetings — distinct from LiveSession),
assignments + submissions, and the scoped syllabus parser machinery. All
additive — existing tables get nullable FKs and the new documents.kind column
defaults to 'lecture' so older rows backfill safely.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d8c3a1e7f9b4"
down_revision: Union[str, None] = "e1d2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------- course_modules ----------
    op.create_table(
        "course_modules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("id <> parent_id", name="ck_course_modules_no_self_parent"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["course_modules.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "idx_course_modules_course_order",
        "course_modules",
        ["course_id", sa.text("parent_id NULLS FIRST"), "order_index"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ---------- course_meetings ----------
    op.create_table(
        "course_meetings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("meeting_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'planned'")),
        sa.Column("pre_meeting_briefing", postgresql.JSONB(), nullable=True),
        sa.Column("post_meeting_summary", postgresql.JSONB(), nullable=True),
        sa.Column("canvas_event_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('planned','in_progress','taught','cancelled')",
            name="ck_course_meetings_status_valid",
        ),
        sa.UniqueConstraint("course_id", "meeting_index", name="uq_course_meetings_course_index"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["module_id"], ["course_modules.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "idx_course_meetings_course_scheduled",
        "course_meetings",
        ["course_id", "scheduled_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_course_meetings_upcoming",
        "course_meetings",
        ["scheduled_at"],
        postgresql_where=sa.text("deleted_at IS NULL AND status = 'planned'"),
    )

    # ---------- learning_objectives ----------
    op.create_table(
        "learning_objectives",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("statement", sa.String(), nullable=False),
        sa.Column("bloom_level", sa.String(20), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "NOT (module_id IS NOT NULL AND meeting_id IS NOT NULL)",
            name="ck_learning_objectives_scope_exclusive",
        ),
        sa.CheckConstraint(
            "bloom_level IS NULL OR bloom_level IN "
            "('remember','understand','apply','analyze','evaluate','create')",
            name="ck_learning_objectives_bloom_valid",
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["module_id"], ["course_modules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["meeting_id"], ["course_meetings.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_learning_objectives_course",
        "learning_objectives",
        ["course_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_learning_objectives_module",
        "learning_objectives",
        ["module_id"],
        postgresql_where=sa.text("module_id IS NOT NULL AND deleted_at IS NULL"),
    )
    op.create_index(
        "idx_learning_objectives_meeting",
        "learning_objectives",
        ["meeting_id"],
        postgresql_where=sa.text("meeting_id IS NOT NULL AND deleted_at IS NULL"),
    )

    # ---------- assignments ----------
    op.create_table(
        "assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("weight", sa.Numeric(5, 2), nullable=True),
        sa.Column("quiz_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("canvas_assignment_id", sa.String(100), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "kind IN ('essay','project','quiz','reading','presentation',"
            "'lab','problem_set','participation','other')",
            name="ck_assignments_kind_valid",
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["module_id"], ["course_modules.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["meeting_id"], ["course_meetings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["quiz_id"], ["quizzes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "idx_assignments_course_due",
        "assignments",
        ["course_id", "due_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_assignments_upcoming",
        "assignments",
        ["due_at"],
        postgresql_where=sa.text("deleted_at IS NULL AND is_published = true"),
    )

    # ---------- assignment_submissions ----------
    op.create_table(
        "assignment_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("score", sa.Numeric(6, 2), nullable=True),
        sa.Column("feedback", sa.String(), nullable=True),
        sa.Column("submission_payload", postgresql.JSONB(), nullable=True),
        sa.Column("canvas_submission_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assignment_id", "user_id", name="uq_assignment_submissions_user"),
        sa.CheckConstraint(
            "status IN ('not_started','in_progress','submitted','late','graded','excused')",
            name="ck_assignment_submissions_status_valid",
        ),
        sa.ForeignKeyConstraint(["assignment_id"], ["assignments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_assignment_submissions_user_status",
        "assignment_submissions",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_assignment_submissions_assignment_status",
        "assignment_submissions",
        ["assignment_id", "status"],
    )

    # ---------- syllabus_imports ----------
    op.create_table(
        "syllabus_imports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("raw_text", sa.String(), nullable=False),
        sa.Column("parsed_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('pending','parsed','applied','failed','superseded')",
            name="ck_syllabus_imports_status_valid",
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["applied_by"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_syllabus_imports_course",
        "syllabus_imports",
        ["course_id", sa.text("created_at DESC")],
    )

    # ---------- ALTER documents: add kind ----------
    op.add_column(
        "documents",
        sa.Column("kind", sa.String(20), nullable=False, server_default=sa.text("'lecture'")),
    )
    op.create_check_constraint(
        "ck_documents_kind_valid",
        "documents",
        "kind IN ('lecture','syllabus','reading','reference','other')",
    )
    op.create_index(
        "idx_documents_course_kind",
        "documents",
        ["course_id", "kind"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ---------- ALTER content tables: link to meeting/module ----------
    for tbl in ("documents", "quizzes", "flashcard_sets", "pronunciation_sets"):
        op.add_column(
            tbl,
            sa.Column("meeting_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.add_column(
            tbl,
            sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_foreign_key(
            f"{tbl}_meeting_id_fkey", tbl, "course_meetings",
            ["meeting_id"], ["id"], ondelete="SET NULL",
        )
        op.create_foreign_key(
            f"{tbl}_module_id_fkey", tbl, "course_modules",
            ["module_id"], ["id"], ondelete="SET NULL",
        )

    op.create_index(
        "idx_documents_meeting", "documents", ["meeting_id"],
        postgresql_where=sa.text("meeting_id IS NOT NULL"),
    )
    op.create_index(
        "idx_quizzes_meeting", "quizzes", ["meeting_id"],
        postgresql_where=sa.text("meeting_id IS NOT NULL"),
    )


def downgrade() -> None:
    # Drop indexes on meeting_id/module_id columns BEFORE dropping those columns
    op.drop_index("idx_documents_meeting", table_name="documents")
    op.drop_index("idx_quizzes_meeting", table_name="quizzes")

    for tbl in ("documents", "quizzes", "flashcard_sets", "pronunciation_sets"):
        op.drop_constraint(f"{tbl}_meeting_id_fkey", tbl, type_="foreignkey")
        op.drop_constraint(f"{tbl}_module_id_fkey", tbl, type_="foreignkey")
        op.drop_column(tbl, "meeting_id")
        op.drop_column(tbl, "module_id")

    op.drop_index("idx_documents_course_kind", table_name="documents")
    op.drop_constraint("ck_documents_kind_valid", "documents", type_="check")
    op.drop_column("documents", "kind")

    op.drop_index("ix_syllabus_imports_course", table_name="syllabus_imports")
    op.drop_table("syllabus_imports")
    op.drop_index("ix_assignment_submissions_user_status", table_name="assignment_submissions")
    op.drop_index("ix_assignment_submissions_assignment_status", table_name="assignment_submissions")
    op.drop_table("assignment_submissions")
    op.drop_table("assignments")
    op.drop_table("learning_objectives")
    op.drop_table("course_meetings")
    op.drop_table("course_modules")
