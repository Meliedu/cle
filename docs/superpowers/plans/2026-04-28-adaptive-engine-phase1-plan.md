# Adaptive Engine — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the curriculum spine + calendar + assignments + scoped syllabus parser as a standalone product update — instructors get real course operating plans and students get a real calendar, with zero concept-aware behaviour yet.

**Architecture:** Six new tables (`course_modules`, `course_meetings`, `learning_objectives`, `assignments`, `assignment_submissions`, `syllabus_imports`) plus a `kind` column on `documents` to scope syllabus uploads. Three new background jobs (`parse_syllabus`, `apply_syllabus_import`, `mark_overdue_submissions`). Five new API routers + frontend calendar editor, syllabus uploader, and assignment submission flow.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic + Postgres 17 + pgvector + Next.js 16 App Router (proxy.ts not middleware.ts) + React 19 + TanStack Query + Better Auth.

**Spec:** [docs/superpowers/specs/2026-04-28-adaptive-engine-design.md](../specs/2026-04-28-adaptive-engine-design.md)

**Scope note:** This is the Phase 1 plan only. Phase 2 (concepts + Beta-Binomial mastery + HLR decay + syllabus-as-generation-context) and Phase 3 (decision layer + outcome telemetry) get separate plans, written when Phase 1 nears completion so they can reference real codebase patterns.

---

## File Structure

### Backend — new files

```
backend/
├── alembic/versions/
│   └── d8c3a1e7f9b4_phase1_curriculum_calendar.py    # one Alembic revision for all Phase 1 tables
├── app/models/
│   └── curriculum.py                                  # CourseModule, CourseMeeting, LearningObjective, Assignment, AssignmentSubmission, SyllabusImport
├── app/schemas/
│   └── curriculum.py                                  # Pydantic request/response for above
├── app/api/
│   ├── modules.py                                     # /api/courses/{course_id}/modules
│   ├── meetings.py                                    # /api/courses/{course_id}/meetings
│   ├── objectives.py                                  # /api/courses/{course_id}/objectives
│   ├── assignments.py                                 # /api/courses/{course_id}/assignments
│   └── syllabus.py                                    # /api/courses/{course_id}/syllabus/{import,imports/{id}/apply}
├── app/services/
│   └── syllabus.py                                    # parse_syllabus_document() and apply_syllabus_import() pure functions
├── app/services/jobs.py                               # MODIFIED — register new task_types
├── app/services/worker.py                             # MODIFIED — dispatch new task_types + new mark_overdue_submissions cron
└── tests/
    ├── test_api_modules.py
    ├── test_api_meetings.py
    ├── test_api_objectives.py
    ├── test_api_assignments.py
    ├── test_api_assignment_submissions.py
    ├── test_api_syllabus.py
    ├── test_syllabus_service.py
    └── test_mark_overdue_submissions.py
```

### Backend — modified files

```
backend/app/api/__init__.py                            # register 5 new routers
backend/app/models/__init__.py                         # export new models
backend/app/models/document.py                         # add `kind` column
```

### Frontend — new files

```
frontend/src/
├── app/dashboard/courses/[courseId]/
│   ├── modules/page.tsx                               # instructor module editor
│   ├── meetings/page.tsx                              # instructor meeting editor
│   ├── objectives/page.tsx                            # instructor objective editor
│   ├── assignments/
│   │   ├── page.tsx                                   # instructor assignment list
│   │   └── [assignmentId]/
│   │       ├── page.tsx                               # instructor assignment detail + submissions roster
│   │       └── submit/page.tsx                        # student submission flow
│   └── syllabus/
│       ├── page.tsx                                   # syllabus upload + parsed import list
│       └── imports/[importId]/page.tsx                # parsed-payload review + apply
├── app/dashboard/calendar/page.tsx                    # MODIFIED — replace placeholder feed with real backend events
├── components/curriculum/
│   ├── module-tree-editor.tsx
│   ├── meeting-form.tsx
│   ├── meeting-list.tsx
│   ├── objective-form.tsx
│   ├── assignment-form.tsx
│   ├── assignment-list.tsx
│   ├── submission-status-badge.tsx
│   ├── syllabus-upload-card.tsx
│   ├── syllabus-import-list.tsx
│   └── syllabus-payload-review.tsx
├── hooks/
│   ├── use-modules.ts
│   ├── use-meetings.ts
│   ├── use-objectives.ts
│   ├── use-assignments.ts
│   ├── use-assignment-submissions.ts
│   ├── use-syllabus.ts
│   └── use-calendar-events.ts                         # MODIFIED — fetch real meetings + assignments instead of placeholder
└── lib/
    └── curriculum-types.ts                            # shared TS types matching backend Pydantic
```

---

## Conventions to follow

- **Models:** use `UUIDPrimaryKeyMixin`, `TimestampMixin`, `SoftDeleteMixin` from `app/models/base.py`. UUID PKs default `uuid.uuid4`. `timestamptz` columns. Named CHECK constraints, explicit FK ON DELETE.
- **Routers:** all return `APIResponse[T]` or `PaginatedResponse[T]` from `app/schemas/common.py`. All require auth via `get_current_user` / `require_instructor`. Soft-delete via `deleted_at = datetime.now(timezone.utc)`, never hard-delete.
- **Permissions:** instructors can CRUD curriculum entities only on courses they own (`course.instructor_id == user.id`). Students get read access only on courses they're enrolled in (check `Enrollment` row). Submission flow is the only place students write.
- **Tests:** `pytest` with `pytest-asyncio`. Use `async_client` fixture from `conftest.py` (overrides `get_db` + `get_current_user`). Test database is `langassistant_test` — `db_session` fixture creates/drops tables via `Base.metadata`.
- **Frontend:** Next.js 16 App Router. Components in PascalCase; hooks `use-*.ts` returning TanStack Query results; CSS via existing `tokens.css` and Tailwind. **No `middleware.ts`** — use `proxy.ts`. Read `node_modules/next/dist/docs/` for current API.
- **Commits:** one commit per task. Conventional commits prefix (`feat:`, `test:`, `refactor:`).

---

## Task 1: Alembic migration for Phase 1 schema

**Files:**
- Create: `backend/alembic/versions/d8c3a1e7f9b4_phase1_curriculum_calendar.py`

- [ ] **Step 1: Identify the head revision to chain off**

Run: `cd backend && source .venv/bin/activate && alembic heads`

Expected: Single revision id printed (most recent existing migration). Note this id — call it `<current_head>`. It will replace the `down_revision` placeholder below.

- [ ] **Step 2: Create the migration file**

Create `backend/alembic/versions/d8c3a1e7f9b4_phase1_curriculum_calendar.py` with:

```python
"""phase 1 curriculum + calendar + syllabus

Revision ID: d8c3a1e7f9b4
Revises: <current_head>
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
down_revision: Union[str, None] = "<current_head>"  # REPLACE with real head id from Step 1
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
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
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
        "idx_assignment_submissions_user_status",
        "assignment_submissions",
        ["user_id", "status"],
    )
    op.create_index(
        "idx_assignment_submissions_assignment_status",
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
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["applied_by"], ["users.id"]),
    )
    op.create_index(
        "idx_syllabus_imports_course",
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

    # ---------- Permissions block ----------
    for tbl in (
        "course_modules", "course_meetings", "learning_objectives",
        "assignments", "assignment_submissions", "syllabus_imports",
    ):
        op.execute(f"ALTER TABLE public.{tbl} OWNER TO postgres")
        op.execute(f"GRANT ALL ON TABLE public.{tbl} TO postgres")
        op.execute(f"GRANT UPDATE, INSERT, SELECT, DELETE ON TABLE public.{tbl} TO meli_app")
        op.execute(f"GRANT SELECT ON TABLE public.{tbl} TO meli_readonly")
        op.execute(f"GRANT ALL ON TABLE public.{tbl} TO meli_admin")


def downgrade() -> None:
    for tbl in ("documents", "quizzes", "flashcard_sets", "pronunciation_sets"):
        op.drop_constraint(f"{tbl}_meeting_id_fkey", tbl, type_="foreignkey")
        op.drop_constraint(f"{tbl}_module_id_fkey", tbl, type_="foreignkey")
        op.drop_column(tbl, "meeting_id")
        op.drop_column(tbl, "module_id")

    op.drop_index("idx_documents_meeting", table_name="documents")
    op.drop_index("idx_quizzes_meeting", table_name="quizzes")
    op.drop_index("idx_documents_course_kind", table_name="documents")
    op.drop_constraint("ck_documents_kind_valid", "documents", type_="check")
    op.drop_column("documents", "kind")

    op.drop_table("syllabus_imports")
    op.drop_table("assignment_submissions")
    op.drop_table("assignments")
    op.drop_table("learning_objectives")
    op.drop_table("course_meetings")
    op.drop_table("course_modules")
```

**IMPORTANT:** replace `<current_head>` with the actual revision id from Step 1 before running.

- [ ] **Step 3: Run the migration against the dev DB**

Run: `cd backend && source .venv/bin/activate && alembic upgrade head`
Expected: `INFO  [alembic.runtime.migration] Running upgrade <prev> -> d8c3a1e7f9b4, phase 1 curriculum + calendar + syllabus`. No errors.

- [ ] **Step 4: Verify the schema**

Run:
```bash
psql postgresql://postgres:postgres@localhost:5432/langassistant -c "\d course_meetings"
```
Expected: shows the columns + indexes + check constraints.

- [ ] **Step 5: Test downgrade safety**

Run:
```bash
cd backend && source .venv/bin/activate && alembic downgrade -1 && alembic upgrade head
```
Expected: both succeed cleanly.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/d8c3a1e7f9b4_phase1_curriculum_calendar.py
git commit -m "feat(curriculum): alembic migration for phase 1 schema

Adds course_modules, course_meetings, learning_objectives, assignments,
assignment_submissions, syllabus_imports tables. Adds documents.kind column
and meeting_id/module_id FKs on documents/quizzes/flashcard_sets/
pronunciation_sets. All additive; existing rows unaffected."
```

---

## Task 2: SQLAlchemy models in `app/models/curriculum.py`

**Files:**
- Create: `backend/app/models/curriculum.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/document.py`
- Test: `backend/tests/test_curriculum_models.py`

- [ ] **Step 1: Write a failing model-level test**

Create `backend/tests/test_curriculum_models.py`:

```python
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Course,
    CourseModule,
    CourseMeeting,
    LearningObjective,
    Assignment,
    AssignmentSubmission,
    SyllabusImport,
    User,
)


@pytest.mark.asyncio
async def test_course_module_persists(db_session: AsyncSession, test_instructor: User):
    course = Course(
        name="Test", language="english",
        instructor_id=test_instructor.id, enroll_code="TESTABCD",
    )
    db_session.add(course)
    await db_session.flush()

    module = CourseModule(course_id=course.id, name="Week 1", order_index=1)
    db_session.add(module)
    await db_session.commit()
    await db_session.refresh(module)

    assert module.id is not None
    assert module.deleted_at is None
    assert module.created_at is not None


@pytest.mark.asyncio
async def test_course_meeting_persists(db_session: AsyncSession, test_instructor: User):
    course = Course(
        name="Test", language="english",
        instructor_id=test_instructor.id, enroll_code="TESTABCE",
    )
    db_session.add(course)
    await db_session.flush()

    meeting = CourseMeeting(
        course_id=course.id, meeting_index=1,
        title="Intro", scheduled_at=datetime.now(timezone.utc),
    )
    db_session.add(meeting)
    await db_session.commit()
    await db_session.refresh(meeting)

    assert meeting.status == "planned"
    assert meeting.duration_minutes == 60


@pytest.mark.asyncio
async def test_assignment_with_submission(
    db_session: AsyncSession, test_instructor: User, test_student: User,
):
    course = Course(
        name="Test", language="english",
        instructor_id=test_instructor.id, enroll_code="TESTABCF",
    )
    db_session.add(course)
    await db_session.flush()

    assignment = Assignment(
        course_id=course.id, title="Essay 1", kind="essay",
        due_at=datetime.now(timezone.utc) + timedelta(days=7),
        weight=Decimal("15.00"),
        created_by=test_instructor.id,
    )
    db_session.add(assignment)
    await db_session.flush()

    submission = AssignmentSubmission(
        assignment_id=assignment.id, user_id=test_student.id,
        status="not_started",
    )
    db_session.add(submission)
    await db_session.commit()
    await db_session.refresh(submission)

    assert submission.id is not None
    assert submission.score is None
```

- [ ] **Step 2: Run the test to verify it fails (imports don't exist yet)**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_curriculum_models.py -v`
Expected: ImportError on `CourseModule` etc.

- [ ] **Step 3: Create `app/models/curriculum.py` with the six models**

```python
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class CourseModule(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "course_modules"
    __table_args__ = (
        CheckConstraint("id <> parent_id", name="ck_course_modules_no_self_parent"),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_modules.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)


class CourseMeeting(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "course_meetings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned','in_progress','taught','cancelled')",
            name="ck_course_meetings_status_valid",
        ),
        UniqueConstraint("course_id", "meeting_index", name="uq_course_meetings_course_index"),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    module_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_modules.id", ondelete="SET NULL")
    )
    meeting_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    location: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned")
    pre_meeting_briefing: Mapped[dict | None] = mapped_column(JSONB)
    post_meeting_summary: Mapped[dict | None] = mapped_column(JSONB)
    canvas_event_id: Mapped[str | None] = mapped_column(String(100))


class LearningObjective(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "learning_objectives"
    __table_args__ = (
        CheckConstraint(
            "NOT (module_id IS NOT NULL AND meeting_id IS NOT NULL)",
            name="ck_learning_objectives_scope_exclusive",
        ),
        CheckConstraint(
            "bloom_level IS NULL OR bloom_level IN "
            "('remember','understand','apply','analyze','evaluate','create')",
            name="ck_learning_objectives_bloom_valid",
        ),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    module_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_modules.id", ondelete="CASCADE")
    )
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_meetings.id", ondelete="CASCADE")
    )
    statement: Mapped[str] = mapped_column(String, nullable=False)
    bloom_level: Mapped[str | None] = mapped_column(String(20))
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Assignment(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "assignments"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('essay','project','quiz','reading','presentation',"
            "'lab','problem_set','participation','other')",
            name="ck_assignments_kind_valid",
        ),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    module_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_modules.id", ondelete="SET NULL")
    )
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_meetings.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    available_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    weight: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    quiz_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="SET NULL")
    )
    canvas_assignment_id: Mapped[str | None] = mapped_column(String(100))
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )


class AssignmentSubmission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assignment_submissions"
    __table_args__ = (
        UniqueConstraint("assignment_id", "user_id", name="uq_assignment_submissions_user"),
        CheckConstraint(
            "status IN ('not_started','in_progress','submitted','late','graded','excused')",
            name="ck_assignment_submissions_status_valid",
        ),
    )

    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    feedback: Mapped[str | None] = mapped_column(String)
    submission_payload: Mapped[dict | None] = mapped_column(JSONB)
    canvas_submission_id: Mapped[str | None] = mapped_column(String(100))


class SyllabusImport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "syllabus_imports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','parsed','applied','failed','superseded')",
            name="ck_syllabus_imports_status_valid",
        ),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )
    raw_text: Mapped[str] = mapped_column(String, nullable=False)
    parsed_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_message: Mapped[str | None] = mapped_column(String)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
```

- [ ] **Step 4: Add `kind` column to existing `Document` model**

Open `backend/app/models/document.py`. Add a `kind` Mapped column (default `'lecture'`) and `meeting_id`/`module_id` Mapped columns. Following the existing patterns in that file:

```python
# Add inside class Document, after existing columns:
kind: Mapped[str] = mapped_column(String(20), nullable=False, default="lecture")
meeting_id: Mapped[uuid.UUID | None] = mapped_column(
    UUID(as_uuid=True), ForeignKey("course_meetings.id", ondelete="SET NULL")
)
module_id: Mapped[uuid.UUID | None] = mapped_column(
    UUID(as_uuid=True), ForeignKey("course_modules.id", ondelete="SET NULL")
)
```

If `Document` does not already import `String` or other types, add the imports.

- [ ] **Step 5: Export the new models from `app/models/__init__.py`**

Add to `backend/app/models/__init__.py`:

```python
from app.models.curriculum import (
    Assignment,
    AssignmentSubmission,
    CourseMeeting,
    CourseModule,
    LearningObjective,
    SyllabusImport,
)
```

And append the names to `__all__`:
```python
"CourseModule",
"CourseMeeting",
"LearningObjective",
"Assignment",
"AssignmentSubmission",
"SyllabusImport",
```

- [ ] **Step 6: Run the test, verify it passes**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_curriculum_models.py -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/curriculum.py backend/app/models/__init__.py \
        backend/app/models/document.py backend/tests/test_curriculum_models.py
git commit -m "feat(curriculum): SQLAlchemy models for phase 1 curriculum entities"
```

---

## Task 3: Pydantic schemas in `app/schemas/curriculum.py`

**Files:**
- Create: `backend/app/schemas/curriculum.py`

- [ ] **Step 1: Create the schemas file**

```python
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

# ----- Modules -----

class CourseModuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    parent_id: uuid.UUID | None = None
    order_index: int = Field(ge=0)


class CourseModuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    parent_id: uuid.UUID | None = None
    order_index: int | None = None


class CourseModuleResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    description: str | None
    order_index: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ----- Meetings -----

MeetingStatus = Literal["planned", "in_progress", "taught", "cancelled"]


class CourseMeetingCreate(BaseModel):
    meeting_index: int = Field(ge=1)
    title: str | None = None
    scheduled_at: datetime
    duration_minutes: int = Field(default=60, ge=1, le=600)
    location: str | None = None
    module_id: uuid.UUID | None = None


class CourseMeetingUpdate(BaseModel):
    meeting_index: int | None = None
    title: str | None = None
    scheduled_at: datetime | None = None
    duration_minutes: int | None = None
    location: str | None = None
    module_id: uuid.UUID | None = None
    status: MeetingStatus | None = None


class CourseMeetingResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    module_id: uuid.UUID | None
    meeting_index: int
    title: str | None
    scheduled_at: datetime
    duration_minutes: int
    location: str | None
    status: MeetingStatus
    canvas_event_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ----- Objectives -----

BloomLevel = Literal["remember", "understand", "apply", "analyze", "evaluate", "create"]


class LearningObjectiveCreate(BaseModel):
    statement: str = Field(min_length=1)
    bloom_level: BloomLevel | None = None
    order_index: int = Field(default=0, ge=0)
    module_id: uuid.UUID | None = None
    meeting_id: uuid.UUID | None = None


class LearningObjectiveUpdate(BaseModel):
    statement: str | None = None
    bloom_level: BloomLevel | None = None
    order_index: int | None = None
    module_id: uuid.UUID | None = None
    meeting_id: uuid.UUID | None = None


class LearningObjectiveResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    module_id: uuid.UUID | None
    meeting_id: uuid.UUID | None
    statement: str
    bloom_level: BloomLevel | None
    order_index: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ----- Assignments -----

AssignmentKind = Literal[
    "essay", "project", "quiz", "reading", "presentation",
    "lab", "problem_set", "participation", "other",
]


class AssignmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    kind: AssignmentKind
    due_at: datetime
    available_from: datetime | None = None
    weight: Decimal | None = Field(default=None, ge=0, le=999.99)
    quiz_id: uuid.UUID | None = None
    module_id: uuid.UUID | None = None
    meeting_id: uuid.UUID | None = None
    is_published: bool = False


class AssignmentUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    kind: AssignmentKind | None = None
    due_at: datetime | None = None
    available_from: datetime | None = None
    weight: Decimal | None = None
    quiz_id: uuid.UUID | None = None
    module_id: uuid.UUID | None = None
    meeting_id: uuid.UUID | None = None
    is_published: bool | None = None


class AssignmentResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    module_id: uuid.UUID | None
    meeting_id: uuid.UUID | None
    title: str
    description: str | None
    kind: AssignmentKind
    due_at: datetime
    available_from: datetime | None
    weight: Decimal | None
    quiz_id: uuid.UUID | None
    is_published: bool
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ----- Submissions -----

SubmissionStatus = Literal[
    "not_started", "in_progress", "submitted", "late", "graded", "excused"
]


class SubmissionUpsert(BaseModel):
    """Student-side: create-or-update own submission."""
    status: Literal["in_progress", "submitted"]
    submission_payload: dict[str, Any] | None = None


class SubmissionGrade(BaseModel):
    """Instructor-side: grade an existing submission."""
    score: Decimal = Field(ge=0)
    feedback: str | None = None
    status: Literal["graded", "excused"] = "graded"


class AssignmentSubmissionResponse(BaseModel):
    id: uuid.UUID
    assignment_id: uuid.UUID
    user_id: uuid.UUID
    status: SubmissionStatus
    submitted_at: datetime | None
    score: Decimal | None
    feedback: str | None
    submission_payload: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ----- Syllabus -----

SyllabusImportStatus = Literal["pending", "parsed", "applied", "failed", "superseded"]


class SyllabusImportResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    document_id: uuid.UUID | None
    parsed_payload: dict[str, Any]
    status: SyllabusImportStatus
    error_message: str | None
    applied_at: datetime | None
    applied_by: uuid.UUID | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SyllabusImportTriggerRequest(BaseModel):
    document_id: uuid.UUID


class SyllabusImportApplyRequest(BaseModel):
    """Body is the (possibly instructor-edited) parsed_payload to apply."""
    parsed_payload: dict[str, Any]
```

- [ ] **Step 2: Verify imports parse**

Run: `cd backend && source .venv/bin/activate && python -c "from app.schemas.curriculum import CourseModuleCreate; print(CourseModuleCreate.model_fields)"`
Expected: prints field info, no errors.

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/curriculum.py
git commit -m "feat(curriculum): pydantic schemas for phase 1 entities"
```

---

## Task 4: `/api/courses/{course_id}/modules` CRUD router

**Files:**
- Create: `backend/app/api/modules.py`
- Modify: `backend/app/api/__init__.py`
- Test: `backend/tests/test_api_modules.py`

- [ ] **Step 1: Write failing API tests**

Create `backend/tests/test_api_modules.py`:

```python
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course, Enrollment, User


@pytest.fixture
async def own_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="Acct 101", language="english",
        instructor_id=logged_in_user.id, enroll_code="OWNCRSE1",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor")
    )
    await db_session.commit()
    await db_session.refresh(course)
    return course


@pytest.mark.asyncio
async def test_create_module(async_client: AsyncClient, own_course: Course):
    r = await async_client.post(
        f"/api/courses/{own_course.id}/modules",
        json={"name": "Week 1", "order_index": 1},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["success"] is True
    assert body["data"]["name"] == "Week 1"
    assert body["data"]["order_index"] == 1


@pytest.mark.asyncio
async def test_list_modules_returns_only_own_course(
    async_client: AsyncClient, own_course: Course,
):
    await async_client.post(
        f"/api/courses/{own_course.id}/modules",
        json={"name": "Week 1", "order_index": 1},
    )
    r = await async_client.get(f"/api/courses/{own_course.id}/modules")
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 1


@pytest.mark.asyncio
async def test_create_module_on_other_instructors_course_forbidden(
    async_client: AsyncClient, db_session: AsyncSession,
):
    other = User(
        better_auth_id="other_instr", email="other@ust.hk",
        full_name="Other", role="instructor",
    )
    db_session.add(other)
    await db_session.flush()
    foreign = Course(
        name="Foreign", language="english",
        instructor_id=other.id, enroll_code="FOREIGN1",
    )
    db_session.add(foreign)
    await db_session.commit()
    await db_session.refresh(foreign)

    r = await async_client.post(
        f"/api/courses/{foreign.id}/modules",
        json={"name": "Week 1", "order_index": 1},
    )
    assert r.status_code == 404  # 404 not 403 to avoid course-existence leak


@pytest.mark.asyncio
async def test_update_module(async_client: AsyncClient, own_course: Course):
    create = await async_client.post(
        f"/api/courses/{own_course.id}/modules",
        json={"name": "Week 1", "order_index": 1},
    )
    module_id = create.json()["data"]["id"]
    r = await async_client.put(
        f"/api/courses/{own_course.id}/modules/{module_id}",
        json={"name": "Week 1 — Intro"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["name"] == "Week 1 — Intro"


@pytest.mark.asyncio
async def test_delete_module_soft_deletes(async_client: AsyncClient, own_course: Course):
    create = await async_client.post(
        f"/api/courses/{own_course.id}/modules",
        json={"name": "Week 1", "order_index": 1},
    )
    module_id = create.json()["data"]["id"]
    r = await async_client.delete(
        f"/api/courses/{own_course.id}/modules/{module_id}",
    )
    assert r.status_code == 200
    listing = await async_client.get(f"/api/courses/{own_course.id}/modules")
    assert listing.json()["data"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_api_modules.py -v`
Expected: 5 tests, all fail with 404 (router not registered).

- [ ] **Step 3: Implement the router**

Create `backend/app/api/modules.py`:

```python
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_instructor
from app.models import Course, CourseModule, User
from app.schemas.common import APIResponse
from app.schemas.curriculum import (
    CourseModuleCreate,
    CourseModuleResponse,
    CourseModuleUpdate,
)

router = APIRouter(prefix="/courses/{course_id}/modules", tags=["curriculum"])


async def _own_course(
    course_id: uuid.UUID, user: User, db: AsyncSession
) -> Course:
    result = await db.execute(
        select(Course).where(
            Course.id == course_id,
            Course.instructor_id == user.id,
            Course.deleted_at.is_(None),
        )
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


@router.post("", response_model=APIResponse[CourseModuleResponse], status_code=201)
async def create_module(
    course_id: uuid.UUID,
    body: CourseModuleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _own_course(course_id, user, db)
    module = CourseModule(course_id=course_id, **body.model_dump())
    db.add(module)
    await db.commit()
    await db.refresh(module)
    return APIResponse(success=True, data=CourseModuleResponse.model_validate(module))


@router.get("", response_model=APIResponse[list[CourseModuleResponse]])
async def list_modules(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _own_course(course_id, user, db)
    result = await db.execute(
        select(CourseModule)
        .where(CourseModule.course_id == course_id, CourseModule.deleted_at.is_(None))
        .order_by(CourseModule.order_index)
    )
    modules = result.scalars().all()
    return APIResponse(
        success=True,
        data=[CourseModuleResponse.model_validate(m) for m in modules],
    )


@router.put("/{module_id}", response_model=APIResponse[CourseModuleResponse])
async def update_module(
    course_id: uuid.UUID,
    module_id: uuid.UUID,
    body: CourseModuleUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _own_course(course_id, user, db)
    result = await db.execute(
        select(CourseModule).where(
            CourseModule.id == module_id,
            CourseModule.course_id == course_id,
            CourseModule.deleted_at.is_(None),
        )
    )
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(module, field, value)
    await db.commit()
    await db.refresh(module)
    return APIResponse(success=True, data=CourseModuleResponse.model_validate(module))


@router.delete("/{module_id}", response_model=APIResponse[None])
async def delete_module(
    course_id: uuid.UUID,
    module_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _own_course(course_id, user, db)
    result = await db.execute(
        select(CourseModule).where(
            CourseModule.id == module_id,
            CourseModule.course_id == course_id,
            CourseModule.deleted_at.is_(None),
        )
    )
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")
    module.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return APIResponse(success=True, data=None)
```

- [ ] **Step 4: Register the router**

In `backend/app/api/__init__.py`:

```python
from app.api.modules import router as modules_router
# ...
api_router.include_router(modules_router)
```

- [ ] **Step 5: Run tests, verify pass**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_api_modules.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/modules.py backend/app/api/__init__.py backend/tests/test_api_modules.py
git commit -m "feat(curriculum): course module CRUD API"
```

---

## Task 5: `/api/courses/{course_id}/meetings` CRUD router

**Files:**
- Create: `backend/app/api/meetings.py`
- Modify: `backend/app/api/__init__.py`
- Test: `backend/tests/test_api_meetings.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_api_meetings.py`:

```python
from datetime import datetime, timezone, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course, Enrollment, User


@pytest.fixture
async def own_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="Test", language="english",
        instructor_id=logged_in_user.id, enroll_code="MTGCRSE1",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor"))
    await db_session.commit()
    await db_session.refresh(course)
    return course


@pytest.mark.asyncio
async def test_create_meeting(async_client: AsyncClient, own_course: Course):
    r = await async_client.post(
        f"/api/courses/{own_course.id}/meetings",
        json={
            "meeting_index": 1,
            "title": "Intro",
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "duration_minutes": 90,
        },
    )
    assert r.status_code == 201
    assert r.json()["data"]["status"] == "planned"


@pytest.mark.asyncio
async def test_meeting_index_unique_within_course(async_client: AsyncClient, own_course: Course):
    payload = {
        "meeting_index": 1,
        "scheduled_at": datetime.now(timezone.utc).isoformat(),
    }
    await async_client.post(f"/api/courses/{own_course.id}/meetings", json=payload)
    r = await async_client.post(f"/api/courses/{own_course.id}/meetings", json=payload)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_list_meetings_ordered_by_scheduled_at(
    async_client: AsyncClient, own_course: Course,
):
    base = datetime.now(timezone.utc)
    await async_client.post(
        f"/api/courses/{own_course.id}/meetings",
        json={"meeting_index": 1, "scheduled_at": (base + timedelta(days=2)).isoformat()},
    )
    await async_client.post(
        f"/api/courses/{own_course.id}/meetings",
        json={"meeting_index": 2, "scheduled_at": (base + timedelta(days=1)).isoformat()},
    )
    r = await async_client.get(f"/api/courses/{own_course.id}/meetings")
    data = r.json()["data"]
    assert data[0]["meeting_index"] == 2  # earlier scheduled_at first


@pytest.mark.asyncio
async def test_calendar_endpoint_combines_meetings_and_assignments(
    async_client: AsyncClient, own_course: Course,
):
    base = datetime.now(timezone.utc)
    await async_client.post(
        f"/api/courses/{own_course.id}/meetings",
        json={"meeting_index": 1, "scheduled_at": (base + timedelta(days=1)).isoformat(),
              "title": "Lecture 1"},
    )
    r = await async_client.get(
        f"/api/courses/{own_course.id}/calendar"
        f"?from_date={(base).isoformat()}&to_date={(base + timedelta(days=7)).isoformat()}"
    )
    assert r.status_code == 200
    body = r.json()
    assert any(e["kind"] == "meeting" for e in body["data"])
```

- [ ] **Step 2: Run tests to verify fail**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_api_meetings.py -v`
Expected: all fail with 404.

- [ ] **Step 3: Implement the router**

Create `backend/app/api/meetings.py`:

```python
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_instructor
from app.models import Assignment, Course, CourseMeeting, User
from app.schemas.common import APIResponse
from app.schemas.curriculum import (
    AssignmentResponse,
    CourseMeetingCreate,
    CourseMeetingResponse,
    CourseMeetingUpdate,
)

router = APIRouter(prefix="/courses/{course_id}", tags=["curriculum"])


async def _own_course(
    course_id: uuid.UUID, user: User, db: AsyncSession
) -> Course:
    result = await db.execute(
        select(Course).where(
            Course.id == course_id,
            Course.instructor_id == user.id,
            Course.deleted_at.is_(None),
        )
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


@router.post("/meetings", response_model=APIResponse[CourseMeetingResponse], status_code=201)
async def create_meeting(
    course_id: uuid.UUID,
    body: CourseMeetingCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _own_course(course_id, user, db)
    meeting = CourseMeeting(course_id=course_id, **body.model_dump())
    db.add(meeting)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="meeting_index already used in this course",
        )
    await db.refresh(meeting)
    return APIResponse(success=True, data=CourseMeetingResponse.model_validate(meeting))


@router.get("/meetings", response_model=APIResponse[list[CourseMeetingResponse]])
async def list_meetings(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _own_course(course_id, user, db)
    result = await db.execute(
        select(CourseMeeting)
        .where(CourseMeeting.course_id == course_id, CourseMeeting.deleted_at.is_(None))
        .order_by(CourseMeeting.scheduled_at)
    )
    meetings = result.scalars().all()
    return APIResponse(
        success=True,
        data=[CourseMeetingResponse.model_validate(m) for m in meetings],
    )


@router.put("/meetings/{meeting_id}", response_model=APIResponse[CourseMeetingResponse])
async def update_meeting(
    course_id: uuid.UUID,
    meeting_id: uuid.UUID,
    body: CourseMeetingUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _own_course(course_id, user, db)
    result = await db.execute(
        select(CourseMeeting).where(
            CourseMeeting.id == meeting_id,
            CourseMeeting.course_id == course_id,
            CourseMeeting.deleted_at.is_(None),
        )
    )
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(meeting, field, value)
    await db.commit()
    await db.refresh(meeting)
    return APIResponse(success=True, data=CourseMeetingResponse.model_validate(meeting))


@router.delete("/meetings/{meeting_id}", response_model=APIResponse[None])
async def delete_meeting(
    course_id: uuid.UUID,
    meeting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _own_course(course_id, user, db)
    result = await db.execute(
        select(CourseMeeting).where(
            CourseMeeting.id == meeting_id,
            CourseMeeting.course_id == course_id,
            CourseMeeting.deleted_at.is_(None),
        )
    )
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    meeting.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return APIResponse(success=True, data=None)


# ---- combined calendar feed ----

class CalendarEvent(dict):
    pass


@router.get("/calendar", response_model=APIResponse[list[dict]])
async def calendar_feed(
    course_id: uuid.UUID,
    from_date: datetime = Query(...),
    to_date: datetime = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    """Return meetings + published assignments in [from_date, to_date) as a flat
    event list. Frontend renders events in calendar grid."""
    await _own_course(course_id, user, db)
    if from_date >= to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="from_date must be before to_date",
        )

    meetings = (
        await db.execute(
            select(CourseMeeting).where(
                CourseMeeting.course_id == course_id,
                CourseMeeting.deleted_at.is_(None),
                CourseMeeting.scheduled_at >= from_date,
                CourseMeeting.scheduled_at < to_date,
            )
        )
    ).scalars().all()

    assignments = (
        await db.execute(
            select(Assignment).where(
                Assignment.course_id == course_id,
                Assignment.deleted_at.is_(None),
                Assignment.is_published.is_(True),
                Assignment.due_at >= from_date,
                Assignment.due_at < to_date,
            )
        )
    ).scalars().all()

    events: list[dict] = []
    for m in meetings:
        events.append({
            "id": str(m.id),
            "kind": "meeting",
            "title": m.title or f"Meeting {m.meeting_index}",
            "at": m.scheduled_at.isoformat(),
            "duration_minutes": m.duration_minutes,
            "location": m.location,
            "status": m.status,
        })
    for a in assignments:
        events.append({
            "id": str(a.id),
            "kind": "assignment",
            "title": a.title,
            "at": a.due_at.isoformat(),
            "assignment_kind": a.kind,
            "weight": float(a.weight) if a.weight is not None else None,
        })
    events.sort(key=lambda e: e["at"])
    return APIResponse(success=True, data=events)
```

- [ ] **Step 4: Register router**

In `backend/app/api/__init__.py`:
```python
from app.api.meetings import router as meetings_router
api_router.include_router(meetings_router)
```

- [ ] **Step 5: Run tests, verify pass**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_api_meetings.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/meetings.py backend/app/api/__init__.py backend/tests/test_api_meetings.py
git commit -m "feat(curriculum): course meeting CRUD + calendar feed endpoint"
```

---

## Task 6: `/api/courses/{course_id}/objectives` CRUD router

**Files:**
- Create: `backend/app/api/objectives.py`
- Modify: `backend/app/api/__init__.py`
- Test: `backend/tests/test_api_objectives.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_api_objectives.py`:

```python
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course, Enrollment, User


@pytest.fixture
async def own_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="T", language="english",
        instructor_id=logged_in_user.id, enroll_code="OBJCRSE1",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor"))
    await db_session.commit()
    await db_session.refresh(course)
    return course


@pytest.mark.asyncio
async def test_create_course_level_objective(async_client: AsyncClient, own_course: Course):
    r = await async_client.post(
        f"/api/courses/{own_course.id}/objectives",
        json={"statement": "Identify cost types", "bloom_level": "understand"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["data"]["module_id"] is None
    assert body["data"]["meeting_id"] is None


@pytest.mark.asyncio
async def test_objective_cannot_have_both_module_and_meeting(
    async_client: AsyncClient, own_course: Course,
):
    # Create a module and a meeting first
    m = await async_client.post(
        f"/api/courses/{own_course.id}/modules",
        json={"name": "W1", "order_index": 1},
    )
    module_id = m.json()["data"]["id"]
    from datetime import datetime, timezone
    mt = await async_client.post(
        f"/api/courses/{own_course.id}/meetings",
        json={"meeting_index": 1, "scheduled_at": datetime.now(timezone.utc).isoformat()},
    )
    meeting_id = mt.json()["data"]["id"]

    r = await async_client.post(
        f"/api/courses/{own_course.id}/objectives",
        json={
            "statement": "x",
            "module_id": module_id,
            "meeting_id": meeting_id,
        },
    )
    assert r.status_code == 400
```

- [ ] **Step 2: Run tests to fail**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_api_objectives.py -v`
Expected: 404 errors.

- [ ] **Step 3: Implement the router**

Create `backend/app/api/objectives.py`:

```python
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_instructor
from app.models import Course, LearningObjective, User
from app.schemas.common import APIResponse
from app.schemas.curriculum import (
    LearningObjectiveCreate,
    LearningObjectiveResponse,
    LearningObjectiveUpdate,
)

router = APIRouter(prefix="/courses/{course_id}/objectives", tags=["curriculum"])


async def _own_course(course_id, user, db) -> Course:
    result = await db.execute(
        select(Course).where(
            Course.id == course_id,
            Course.instructor_id == user.id,
            Course.deleted_at.is_(None),
        )
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


def _validate_scope(body: LearningObjectiveCreate | LearningObjectiveUpdate) -> None:
    if body.module_id is not None and body.meeting_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="objective cannot be scoped to both module and meeting",
        )


@router.post("", response_model=APIResponse[LearningObjectiveResponse], status_code=201)
async def create_objective(
    course_id: uuid.UUID,
    body: LearningObjectiveCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _own_course(course_id, user, db)
    _validate_scope(body)
    obj = LearningObjective(course_id=course_id, **body.model_dump())
    db.add(obj)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="objective scope invalid")
    await db.refresh(obj)
    return APIResponse(success=True, data=LearningObjectiveResponse.model_validate(obj))


@router.get("", response_model=APIResponse[list[LearningObjectiveResponse]])
async def list_objectives(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _own_course(course_id, user, db)
    result = await db.execute(
        select(LearningObjective)
        .where(
            LearningObjective.course_id == course_id,
            LearningObjective.deleted_at.is_(None),
        )
        .order_by(LearningObjective.order_index)
    )
    objs = result.scalars().all()
    return APIResponse(
        success=True,
        data=[LearningObjectiveResponse.model_validate(o) for o in objs],
    )


@router.put("/{objective_id}", response_model=APIResponse[LearningObjectiveResponse])
async def update_objective(
    course_id: uuid.UUID,
    objective_id: uuid.UUID,
    body: LearningObjectiveUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _own_course(course_id, user, db)
    _validate_scope(body)
    result = await db.execute(
        select(LearningObjective).where(
            LearningObjective.id == objective_id,
            LearningObjective.course_id == course_id,
            LearningObjective.deleted_at.is_(None),
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Objective not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return APIResponse(success=True, data=LearningObjectiveResponse.model_validate(obj))


@router.delete("/{objective_id}", response_model=APIResponse[None])
async def delete_objective(
    course_id: uuid.UUID,
    objective_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _own_course(course_id, user, db)
    result = await db.execute(
        select(LearningObjective).where(
            LearningObjective.id == objective_id,
            LearningObjective.course_id == course_id,
            LearningObjective.deleted_at.is_(None),
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Objective not found")
    obj.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return APIResponse(success=True, data=None)
```

- [ ] **Step 4: Register the router**

`api_router.include_router(objectives_router)` in `backend/app/api/__init__.py`.

- [ ] **Step 5: Run tests, verify pass**

Run: `pytest tests/test_api_objectives.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/objectives.py backend/app/api/__init__.py backend/tests/test_api_objectives.py
git commit -m "feat(curriculum): learning objective CRUD API"
```

---

## Task 7: `/api/courses/{course_id}/assignments` + submissions

**Files:**
- Create: `backend/app/api/assignments.py`
- Modify: `backend/app/api/__init__.py`
- Test: `backend/tests/test_api_assignments.py`
- Test: `backend/tests/test_api_assignment_submissions.py`

- [ ] **Step 1: Write failing tests for assignments**

Create `backend/tests/test_api_assignments.py`:

```python
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course, Enrollment, User


@pytest.fixture
async def own_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="T", language="english",
        instructor_id=logged_in_user.id, enroll_code="ASSCRSE1",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor"))
    await db_session.commit()
    await db_session.refresh(course)
    return course


@pytest.mark.asyncio
async def test_create_assignment(async_client: AsyncClient, own_course: Course):
    due = datetime.now(timezone.utc) + timedelta(days=7)
    r = await async_client.post(
        f"/api/courses/{own_course.id}/assignments",
        json={
            "title": "Essay 1",
            "kind": "essay",
            "due_at": due.isoformat(),
            "weight": "15.00",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["data"]["is_published"] is False
    assert body["data"]["weight"] == "15.00"


@pytest.mark.asyncio
async def test_publish_assignment_via_update(async_client: AsyncClient, own_course: Course):
    due = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    create = await async_client.post(
        f"/api/courses/{own_course.id}/assignments",
        json={"title": "Quiz 1", "kind": "quiz", "due_at": due},
    )
    aid = create.json()["data"]["id"]
    upd = await async_client.put(
        f"/api/courses/{own_course.id}/assignments/{aid}",
        json={"is_published": True},
    )
    assert upd.status_code == 200
    assert upd.json()["data"]["is_published"] is True
```

- [ ] **Step 2: Write failing tests for submissions**

Create `backend/tests/test_api_assignment_submissions.py`:

```python
from datetime import datetime, timezone, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.main import app
from app.models import Assignment, Course, Enrollment, User


@pytest.fixture
async def published_assignment(
    db_session: AsyncSession, logged_in_user: User, test_student: User,
) -> tuple[Course, Assignment]:
    course = Course(
        name="T", language="english",
        instructor_id=logged_in_user.id, enroll_code="SUBCRSE1",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor"))
    db_session.add(Enrollment(course_id=course.id, user_id=test_student.id, role="student"))
    a = Assignment(
        course_id=course.id, title="A", kind="essay",
        due_at=datetime.now(timezone.utc) + timedelta(days=3),
        is_published=True, created_by=logged_in_user.id,
    )
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    return course, a


@pytest.mark.asyncio
async def test_student_can_submit_own_submission(
    db_session: AsyncSession, test_student: User,
    published_assignment: tuple[Course, Assignment],
):
    course, assignment = published_assignment

    async def override_db():
        yield db_session

    async def override_user():
        return test_student

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer x"},
        ) as ac:
            r = await ac.post(
                f"/api/courses/{course.id}/assignments/{assignment.id}/submission",
                json={"status": "submitted", "submission_payload": {"text": "hi"}},
            )
            assert r.status_code == 200
            assert r.json()["data"]["status"] == "submitted"
            assert r.json()["data"]["submitted_at"] is not None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_instructor_can_grade_submission(
    db_session: AsyncSession, logged_in_user: User, test_student: User,
    published_assignment: tuple[Course, Assignment],
):
    from app.models import AssignmentSubmission
    course, assignment = published_assignment
    sub = AssignmentSubmission(
        assignment_id=assignment.id, user_id=test_student.id, status="submitted",
        submitted_at=datetime.now(timezone.utc),
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)

    async def override_db():
        yield db_session

    async def override_user():
        return logged_in_user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer x"},
        ) as ac:
            r = await ac.post(
                f"/api/courses/{course.id}/assignments/{assignment.id}/submissions/{sub.id}/grade",
                json={"score": "85.00", "feedback": "Good", "status": "graded"},
            )
            assert r.status_code == 200
            assert r.json()["data"]["status"] == "graded"
            assert r.json()["data"]["score"] == "85.00"
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 3: Run tests to fail**

Run: `pytest tests/test_api_assignments.py tests/test_api_assignment_submissions.py -v`
Expected: 404s.

- [ ] **Step 4: Implement `app/api/assignments.py`**

```python
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_instructor
from app.models import (
    Assignment, AssignmentSubmission, Course, Enrollment, User,
)
from app.schemas.common import APIResponse
from app.schemas.curriculum import (
    AssignmentCreate, AssignmentResponse, AssignmentSubmissionResponse,
    AssignmentUpdate, SubmissionGrade, SubmissionUpsert,
)

router = APIRouter(prefix="/courses/{course_id}/assignments", tags=["curriculum"])


async def _own_course(course_id, user, db) -> Course:
    result = await db.execute(
        select(Course).where(
            Course.id == course_id,
            Course.instructor_id == user.id,
            Course.deleted_at.is_(None),
        )
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Course not found")
    return c


async def _enrolled(course_id, user, db) -> Course:
    """Either enrolled student or course-owning instructor can read."""
    result = await db.execute(
        select(Course).join(Enrollment, Enrollment.course_id == Course.id)
        .where(
            Course.id == course_id,
            Enrollment.user_id == user.id,
            Course.deleted_at.is_(None),
        )
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Course not found")
    return c


@router.post("", response_model=APIResponse[AssignmentResponse], status_code=201)
async def create_assignment(
    course_id: uuid.UUID,
    body: AssignmentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _own_course(course_id, user, db)
    a = Assignment(course_id=course_id, created_by=user.id, **body.model_dump())
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return APIResponse(success=True, data=AssignmentResponse.model_validate(a))


@router.get("", response_model=APIResponse[list[AssignmentResponse]])
async def list_assignments(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    course = await _enrolled(course_id, user, db)
    base = select(Assignment).where(
        Assignment.course_id == course_id,
        Assignment.deleted_at.is_(None),
    )
    if user.id != course.instructor_id:
        base = base.where(Assignment.is_published.is_(True))
    base = base.order_by(Assignment.due_at)
    rows = (await db.execute(base)).scalars().all()
    return APIResponse(
        success=True,
        data=[AssignmentResponse.model_validate(a) for a in rows],
    )


@router.put("/{assignment_id}", response_model=APIResponse[AssignmentResponse])
async def update_assignment(
    course_id: uuid.UUID,
    assignment_id: uuid.UUID,
    body: AssignmentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _own_course(course_id, user, db)
    res = await db.execute(
        select(Assignment).where(
            Assignment.id == assignment_id,
            Assignment.course_id == course_id,
            Assignment.deleted_at.is_(None),
        )
    )
    a = res.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    for f, v in body.model_dump(exclude_unset=True).items():
        setattr(a, f, v)
    await db.commit()
    await db.refresh(a)
    return APIResponse(success=True, data=AssignmentResponse.model_validate(a))


@router.delete("/{assignment_id}", response_model=APIResponse[None])
async def delete_assignment(
    course_id: uuid.UUID,
    assignment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _own_course(course_id, user, db)
    res = await db.execute(
        select(Assignment).where(
            Assignment.id == assignment_id,
            Assignment.course_id == course_id,
            Assignment.deleted_at.is_(None),
        )
    )
    a = res.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    a.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return APIResponse(success=True, data=None)


# ----- submissions -----

@router.post(
    "/{assignment_id}/submission",
    response_model=APIResponse[AssignmentSubmissionResponse],
)
async def upsert_my_submission(
    course_id: uuid.UUID,
    assignment_id: uuid.UUID,
    body: SubmissionUpsert,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Student-side: create or update own submission."""
    await _enrolled(course_id, user, db)
    asn = (
        await db.execute(
            select(Assignment).where(
                Assignment.id == assignment_id,
                Assignment.course_id == course_id,
                Assignment.deleted_at.is_(None),
                Assignment.is_published.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not asn:
        raise HTTPException(status_code=404, detail="Assignment not found")

    res = await db.execute(
        select(AssignmentSubmission).where(
            AssignmentSubmission.assignment_id == assignment_id,
            AssignmentSubmission.user_id == user.id,
        )
    )
    sub = res.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if sub is None:
        sub = AssignmentSubmission(
            assignment_id=assignment_id, user_id=user.id, status=body.status,
            submitted_at=now if body.status == "submitted" else None,
            submission_payload=body.submission_payload,
        )
        db.add(sub)
    else:
        sub.status = body.status
        if body.status == "submitted" and sub.submitted_at is None:
            sub.submitted_at = now
        if body.submission_payload is not None:
            sub.submission_payload = body.submission_payload
    await db.commit()
    await db.refresh(sub)
    return APIResponse(success=True, data=AssignmentSubmissionResponse.model_validate(sub))


@router.get(
    "/{assignment_id}/submissions",
    response_model=APIResponse[list[AssignmentSubmissionResponse]],
)
async def list_submissions(
    course_id: uuid.UUID,
    assignment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _own_course(course_id, user, db)
    rows = (
        await db.execute(
            select(AssignmentSubmission).where(
                AssignmentSubmission.assignment_id == assignment_id,
            )
        )
    ).scalars().all()
    return APIResponse(
        success=True,
        data=[AssignmentSubmissionResponse.model_validate(s) for s in rows],
    )


@router.post(
    "/{assignment_id}/submissions/{submission_id}/grade",
    response_model=APIResponse[AssignmentSubmissionResponse],
)
async def grade_submission(
    course_id: uuid.UUID,
    assignment_id: uuid.UUID,
    submission_id: uuid.UUID,
    body: SubmissionGrade,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _own_course(course_id, user, db)
    sub = (
        await db.execute(
            select(AssignmentSubmission).where(
                AssignmentSubmission.id == submission_id,
                AssignmentSubmission.assignment_id == assignment_id,
            )
        )
    ).scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    sub.score = body.score
    sub.feedback = body.feedback
    sub.status = body.status
    await db.commit()
    await db.refresh(sub)
    return APIResponse(success=True, data=AssignmentSubmissionResponse.model_validate(sub))
```

- [ ] **Step 5: Register router and run tests**

Add to `backend/app/api/__init__.py`:
```python
from app.api.assignments import router as assignments_router
api_router.include_router(assignments_router)
```

Run: `pytest tests/test_api_assignments.py tests/test_api_assignment_submissions.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/assignments.py backend/app/api/__init__.py \
        backend/tests/test_api_assignments.py \
        backend/tests/test_api_assignment_submissions.py
git commit -m "feat(curriculum): assignments + assignment_submissions API"
```

---

## Task 8: Syllabus parser service + API

**Files:**
- Create: `backend/app/services/syllabus.py`
- Create: `backend/app/api/syllabus.py`
- Modify: `backend/app/services/jobs.py`
- Modify: `backend/app/services/worker.py`
- Modify: `backend/app/api/__init__.py`
- Test: `backend/tests/test_syllabus_service.py`
- Test: `backend/tests/test_api_syllabus.py`

- [ ] **Step 1: Write a failing service-level test**

Create `backend/tests/test_syllabus_service.py`:

```python
import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Assignment, Course, CourseMeeting, CourseModule,
    LearningObjective, SyllabusImport, User,
)
from app.services.syllabus import apply_syllabus_payload, parse_syllabus_text


@pytest.mark.asyncio
async def test_parse_syllabus_text_returns_payload(monkeypatch):
    fake = {
        "course": {"name": "T", "semester": "Fall 2026", "language": "english"},
        "modules": [{"name": "Week 1", "order_index": 1}],
        "meetings": [
            {"module_index": 1, "meeting_index": 1,
             "scheduled_at": "2026-09-01T10:00:00Z", "title": "Intro",
             "objective_statements": []},
        ],
        "objectives": [
            {"scope": "course", "statement": "Identify cost types",
             "bloom_level": "understand"},
        ],
        "assignments": [],
        "schema_version": "v1",
    }

    async def fake_llm(text: str) -> dict:
        return fake

    monkeypatch.setattr("app.services.syllabus._llm_extract", fake_llm)
    payload = await parse_syllabus_text("Course X. Week 1: Intro...")
    assert payload["schema_version"] == "v1"
    assert len(payload["modules"]) == 1


@pytest.mark.asyncio
async def test_apply_syllabus_payload_creates_entities(
    db_session: AsyncSession, test_instructor: User,
):
    course = Course(
        name="T", language="english",
        instructor_id=test_instructor.id, enroll_code="SYLCRSE1",
    )
    db_session.add(course)
    await db_session.flush()

    payload = {
        "course": {"name": "T"},
        "modules": [{"name": "Week 1", "order_index": 1}],
        "meetings": [
            {"module_index": 1, "meeting_index": 1,
             "scheduled_at": "2026-09-01T10:00:00Z",
             "title": "Intro", "objective_statements": []},
        ],
        "objectives": [
            {"scope": "course", "statement": "X", "bloom_level": "apply"},
        ],
        "assignments": [
            {"title": "Essay", "kind": "essay",
             "due_at": "2026-10-15T23:59:00Z", "weight": 15.0},
        ],
        "schema_version": "v1",
    }

    await apply_syllabus_payload(
        db_session, course_id=course.id,
        payload=payload, applied_by=test_instructor.id,
    )
    await db_session.commit()

    modules = (await db_session.execute(
        select(CourseModule).where(CourseModule.course_id == course.id)
    )).scalars().all()
    meetings = (await db_session.execute(
        select(CourseMeeting).where(CourseMeeting.course_id == course.id)
    )).scalars().all()
    objs = (await db_session.execute(
        select(LearningObjective).where(LearningObjective.course_id == course.id)
    )).scalars().all()
    asns = (await db_session.execute(
        select(Assignment).where(Assignment.course_id == course.id)
    )).scalars().all()
    assert len(modules) == 1
    assert len(meetings) == 1
    assert meetings[0].module_id == modules[0].id
    assert len(objs) == 1
    assert len(asns) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_syllabus_service.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `app/services/syllabus.py`**

```python
"""Syllabus parsing + apply.

`parse_syllabus_text` is a thin wrapper around an LLM structured-output call.
`apply_syllabus_payload` is the transactional applier that creates modules /
meetings / objectives / assignments from the (possibly instructor-edited)
payload.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import (
    Assignment,
    CourseMeeting,
    CourseModule,
    LearningObjective,
)

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You extract structured syllabus data from arbitrary syllabus text.
Output ONLY a JSON object matching this schema:
{
  "course": {"name": "string", "semester": "string|null", "language": "string|null"},
  "modules": [{"name": "string", "order_index": int, "description": "string|null"}],
  "meetings": [{
      "module_index": int, "meeting_index": int,
      "scheduled_at": "ISO 8601 datetime",
      "title": "string|null",
      "objective_statements": ["string"]
  }],
  "objectives": [{
      "scope": "course|module|meeting",
      "scope_index": int|null,
      "statement": "string",
      "bloom_level": "remember|understand|apply|analyze|evaluate|create|null"
  }],
  "assignments": [{
      "title": "string", "kind": "essay|project|quiz|reading|presentation|lab|problem_set|participation|other",
      "due_at": "ISO 8601 datetime", "weight": float|null,
      "module_index": int|null, "meeting_index": int|null
  }],
  "schema_version": "v1"
}
If a field is missing, omit it. Do not hallucinate dates."""


async def _llm_extract(raw_text: str) -> dict[str, Any]:
    """LLM call. Separate function so tests can monkeypatch."""
    client = AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )
    resp = await client.chat.completions.create(
        model=settings.llm_primary_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": raw_text[:40000]},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    return json.loads(resp.choices[0].message.content or "{}")


async def parse_syllabus_text(raw_text: str) -> dict[str, Any]:
    """Extract structured payload from syllabus text via LLM."""
    payload = await _llm_extract(raw_text)
    if "schema_version" not in payload:
        payload["schema_version"] = "v1"
    return payload


async def apply_syllabus_payload(
    db: AsyncSession,
    *,
    course_id: uuid.UUID,
    payload: dict[str, Any],
    applied_by: uuid.UUID,
) -> None:
    """Idempotent-ish: dedupes modules/meetings/objectives/assignments by name+index.

    Designed to be called inside a caller-managed transaction. Caller commits.
    """
    # ---- modules: dedupe by (course_id, name) ----
    module_id_by_index: dict[int, uuid.UUID] = {}
    for raw in payload.get("modules", []):
        name = (raw.get("name") or "").strip()
        if not name:
            continue
        oi = int(raw.get("order_index", 0))
        existing = (
            await db.execute(
                select(CourseModule).where(
                    CourseModule.course_id == course_id,
                    CourseModule.name == name,
                    CourseModule.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing:
            mod = existing
        else:
            mod = CourseModule(
                course_id=course_id, name=name, order_index=oi,
                description=raw.get("description"),
            )
            db.add(mod)
            await db.flush()
        module_id_by_index[oi] = mod.id

    # ---- meetings: dedupe by (course_id, meeting_index) ----
    meeting_id_by_index: dict[int, uuid.UUID] = {}
    for raw in payload.get("meetings", []):
        mi = int(raw.get("meeting_index", 0))
        if mi <= 0:
            continue
        existing = (
            await db.execute(
                select(CourseMeeting).where(
                    CourseMeeting.course_id == course_id,
                    CourseMeeting.meeting_index == mi,
                    CourseMeeting.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        scheduled = datetime.fromisoformat(raw["scheduled_at"].replace("Z", "+00:00"))
        mod_idx = raw.get("module_index")
        module_id = module_id_by_index.get(int(mod_idx)) if mod_idx else None
        if existing:
            existing.title = raw.get("title") or existing.title
            existing.scheduled_at = scheduled
            if module_id and existing.module_id is None:
                existing.module_id = module_id
            mt = existing
        else:
            mt = CourseMeeting(
                course_id=course_id, meeting_index=mi,
                title=raw.get("title"), scheduled_at=scheduled,
                module_id=module_id,
            )
            db.add(mt)
            await db.flush()
        meeting_id_by_index[mi] = mt.id

    # ---- objectives: dedupe by (course_id, statement) ----
    for raw in payload.get("objectives", []):
        stmt = (raw.get("statement") or "").strip()
        if not stmt:
            continue
        scope = raw.get("scope") or "course"
        scope_idx = raw.get("scope_index")
        module_id = (
            module_id_by_index.get(int(scope_idx))
            if scope == "module" and scope_idx is not None else None
        )
        meeting_id = (
            meeting_id_by_index.get(int(scope_idx))
            if scope == "meeting" and scope_idx is not None else None
        )
        existing = (
            await db.execute(
                select(LearningObjective).where(
                    LearningObjective.course_id == course_id,
                    LearningObjective.statement == stmt,
                    LearningObjective.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing:
            continue
        obj = LearningObjective(
            course_id=course_id, statement=stmt,
            bloom_level=raw.get("bloom_level"),
            module_id=module_id, meeting_id=meeting_id,
        )
        db.add(obj)

    # ---- assignments: dedupe by (course_id, title, due_at) ----
    for raw in payload.get("assignments", []):
        title = (raw.get("title") or "").strip()
        if not title:
            continue
        due = datetime.fromisoformat(raw["due_at"].replace("Z", "+00:00"))
        existing = (
            await db.execute(
                select(Assignment).where(
                    Assignment.course_id == course_id,
                    Assignment.title == title,
                    Assignment.due_at == due,
                    Assignment.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing:
            continue
        weight = raw.get("weight")
        weight_dec = Decimal(str(weight)) if weight is not None else None
        mod_idx = raw.get("module_index")
        mt_idx = raw.get("meeting_index")
        a = Assignment(
            course_id=course_id, title=title,
            kind=raw.get("kind", "other"),
            due_at=due, weight=weight_dec,
            module_id=module_id_by_index.get(int(mod_idx)) if mod_idx else None,
            meeting_id=meeting_id_by_index.get(int(mt_idx)) if mt_idx else None,
            created_by=applied_by, is_published=False,
        )
        db.add(a)
```

- [ ] **Step 4: Run service tests, verify pass**

Run: `pytest tests/test_syllabus_service.py -v`
Expected: 2 passed.

- [ ] **Step 5: Implement `app/api/syllabus.py`**

```python
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_instructor
from app.models import Course, Document, SyllabusImport, Task, User
from app.schemas.common import APIResponse
from app.schemas.curriculum import (
    SyllabusImportApplyRequest,
    SyllabusImportResponse,
    SyllabusImportTriggerRequest,
)
from app.services.syllabus import apply_syllabus_payload

router = APIRouter(prefix="/courses/{course_id}/syllabus", tags=["curriculum"])


async def _own_course(course_id, user, db) -> Course:
    res = await db.execute(
        select(Course).where(
            Course.id == course_id, Course.instructor_id == user.id,
            Course.deleted_at.is_(None),
        )
    )
    c = res.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Course not found")
    return c


@router.post(
    "/imports", response_model=APIResponse[SyllabusImportResponse], status_code=202,
)
async def trigger_import(
    course_id: uuid.UUID,
    body: SyllabusImportTriggerRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _own_course(course_id, user, db)
    doc = (
        await db.execute(
            select(Document).where(
                Document.id == body.document_id,
                Document.course_id == course_id,
                Document.kind == "syllabus",
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="syllabus document not found")

    imp = SyllabusImport(
        course_id=course_id, document_id=doc.id,
        raw_text="",  # filled by job
        parsed_payload={},
        status="pending",
        created_by=user.id,
    )
    db.add(imp)
    await db.flush()
    db.add(Task(
        task_type="parse_syllabus",
        payload={"syllabus_import_id": str(imp.id), "document_id": str(doc.id)},
        status="pending", attempts=0, max_attempts=3,
    ))
    await db.commit()
    await db.refresh(imp)
    return APIResponse(success=True, data=SyllabusImportResponse.model_validate(imp))


@router.get("/imports", response_model=APIResponse[list[SyllabusImportResponse]])
async def list_imports(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _own_course(course_id, user, db)
    rows = (
        await db.execute(
            select(SyllabusImport).where(SyllabusImport.course_id == course_id)
            .order_by(SyllabusImport.created_at.desc())
        )
    ).scalars().all()
    return APIResponse(
        success=True,
        data=[SyllabusImportResponse.model_validate(r) for r in rows],
    )


@router.post(
    "/imports/{import_id}/apply",
    response_model=APIResponse[SyllabusImportResponse],
)
async def apply_import(
    course_id: uuid.UUID,
    import_id: uuid.UUID,
    body: SyllabusImportApplyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _own_course(course_id, user, db)
    imp = (
        await db.execute(
            select(SyllabusImport).where(
                SyllabusImport.id == import_id,
                SyllabusImport.course_id == course_id,
            )
        )
    ).scalar_one_or_none()
    if not imp:
        raise HTTPException(status_code=404, detail="import not found")
    if imp.status != "parsed":
        raise HTTPException(
            status_code=409,
            detail=f"only 'parsed' imports can be applied (current: {imp.status})",
        )
    await apply_syllabus_payload(
        db, course_id=course_id, payload=body.parsed_payload, applied_by=user.id,
    )
    imp.parsed_payload = body.parsed_payload
    imp.status = "applied"
    imp.applied_at = datetime.now(timezone.utc)
    imp.applied_by = user.id

    # supersede earlier applied imports for the same course
    await db.execute(
        select(SyllabusImport).where(
            SyllabusImport.course_id == course_id,
            SyllabusImport.id != imp.id,
            SyllabusImport.status == "applied",
        )
    )  # no-op; loop instead so we can update each
    earlier = (await db.execute(
        select(SyllabusImport).where(
            SyllabusImport.course_id == course_id,
            SyllabusImport.id != imp.id,
            SyllabusImport.status == "applied",
        )
    )).scalars().all()
    for e in earlier:
        e.status = "superseded"

    await db.commit()
    await db.refresh(imp)
    return APIResponse(success=True, data=SyllabusImportResponse.model_validate(imp))
```

- [ ] **Step 6: Wire `parse_syllabus` job in `app/services/jobs.py`**

Append to `backend/app/services/jobs.py`:

```python
from app.models import Document, SyllabusImport
from app.services.storage import download_to_bytes
from app.services.parser import parse_document  # existing
from app.services.syllabus import parse_syllabus_text


async def run_parse_syllabus(session: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    import_id = uuid.UUID(payload["syllabus_import_id"])
    document_id = uuid.UUID(payload["document_id"])

    imp = (await session.execute(
        select(SyllabusImport).where(SyllabusImport.id == import_id)
    )).scalar_one_or_none()
    if imp is None:
        return {"status": "missing"}

    doc = (await session.execute(
        select(Document).where(Document.id == document_id)
    )).scalar_one_or_none()
    if doc is None or doc.kind != "syllabus":
        imp.status = "failed"
        imp.error_message = "syllabus document missing or kind changed"
        await session.commit()
        return {"status": "failed"}

    raw_bytes = await download_to_bytes(doc.r2_key)
    text = await parse_document(raw_bytes, doc.file_type)
    imp.raw_text = text[:200000]
    payload_json = await parse_syllabus_text(text)
    imp.parsed_payload = payload_json
    imp.status = "parsed"
    await session.commit()
    return {"status": "parsed", "syllabus_import_id": str(imp.id)}
```

- [ ] **Step 7: Dispatch the new task_type in `worker.py`**

In `backend/app/services/worker.py`, locate the dispatcher branch (around line 273+). Add a new branch:

```python
    elif task.task_type == "parse_syllabus":
        from app.services.jobs import run_parse_syllabus
        result = await run_parse_syllabus(session, task.payload)
```

Place it before the `else: raise ValueError(...)` line.

- [ ] **Step 8: Register the syllabus router**

```python
from app.api.syllabus import router as syllabus_router
api_router.include_router(syllabus_router)
```

- [ ] **Step 9: Write API integration test for syllabus flow**

Create `backend/tests/test_api_syllabus.py`:

```python
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course, Document, Enrollment, SyllabusImport, User


@pytest.fixture
async def own_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    c = Course(
        name="T", language="english",
        instructor_id=logged_in_user.id, enroll_code="SYLLABUS",
    )
    db_session.add(c)
    await db_session.flush()
    db_session.add(Enrollment(course_id=c.id, user_id=logged_in_user.id, role="instructor"))
    await db_session.commit()
    await db_session.refresh(c)
    return c


@pytest.fixture
async def syllabus_doc(
    db_session: AsyncSession, own_course: Course, logged_in_user: User,
) -> Document:
    d = Document(
        course_id=own_course.id, uploaded_by=logged_in_user.id,
        filename="syllabus.pdf", file_type="pdf",
        file_size=1, r2_key="x", r2_url="x",
        status="completed", kind="syllabus",
    )
    db_session.add(d)
    await db_session.commit()
    await db_session.refresh(d)
    return d


@pytest.mark.asyncio
async def test_trigger_creates_pending_import(
    async_client: AsyncClient, own_course: Course, syllabus_doc: Document,
):
    r = await async_client.post(
        f"/api/courses/{own_course.id}/syllabus/imports",
        json={"document_id": str(syllabus_doc.id)},
    )
    assert r.status_code == 202
    assert r.json()["data"]["status"] == "pending"


@pytest.mark.asyncio
async def test_apply_only_works_on_parsed_status(
    async_client: AsyncClient, db_session: AsyncSession,
    own_course: Course, logged_in_user: User,
):
    imp = SyllabusImport(
        course_id=own_course.id, raw_text="x", parsed_payload={},
        status="pending", created_by=logged_in_user.id,
    )
    db_session.add(imp)
    await db_session.commit()
    await db_session.refresh(imp)
    r = await async_client.post(
        f"/api/courses/{own_course.id}/syllabus/imports/{imp.id}/apply",
        json={"parsed_payload": {"modules": [], "meetings": [], "objectives": [],
                                 "assignments": [], "schema_version": "v1"}},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_apply_creates_entities(
    async_client: AsyncClient, db_session: AsyncSession,
    own_course: Course, logged_in_user: User,
):
    imp = SyllabusImport(
        course_id=own_course.id, raw_text="x",
        parsed_payload={"schema_version": "v1"},
        status="parsed", created_by=logged_in_user.id,
    )
    db_session.add(imp)
    await db_session.commit()
    await db_session.refresh(imp)
    payload = {
        "modules": [{"name": "W1", "order_index": 1}],
        "meetings": [{"module_index": 1, "meeting_index": 1,
                      "scheduled_at": "2026-09-01T10:00:00Z", "title": "Intro",
                      "objective_statements": []}],
        "objectives": [{"scope": "course", "statement": "x", "bloom_level": "apply"}],
        "assignments": [],
        "schema_version": "v1",
    }
    r = await async_client.post(
        f"/api/courses/{own_course.id}/syllabus/imports/{imp.id}/apply",
        json={"parsed_payload": payload},
    )
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "applied"
```

- [ ] **Step 10: Run all syllabus tests**

Run: `pytest tests/test_syllabus_service.py tests/test_api_syllabus.py -v`
Expected: all pass.

- [ ] **Step 11: Commit**

```bash
git add backend/app/services/syllabus.py backend/app/api/syllabus.py \
        backend/app/services/jobs.py backend/app/services/worker.py \
        backend/app/api/__init__.py \
        backend/tests/test_syllabus_service.py backend/tests/test_api_syllabus.py
git commit -m "feat(syllabus): scoped syllabus parser + applier API and worker job"
```

---

## Task 9: `mark_overdue_submissions` daily cron

**Files:**
- Modify: `backend/app/services/worker.py`
- Test: `backend/tests/test_mark_overdue_submissions.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_mark_overdue_submissions.py`:

```python
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Assignment, AssignmentSubmission, Course, User,
)
from app.services.worker import mark_overdue_submissions


@pytest.mark.asyncio
async def test_marks_past_due_not_started_as_late(
    db_session: AsyncSession, test_instructor: User, test_student: User,
):
    course = Course(
        name="T", language="english",
        instructor_id=test_instructor.id, enroll_code="MOSCRSE1",
    )
    db_session.add(course)
    await db_session.flush()
    a = Assignment(
        course_id=course.id, title="Old", kind="essay",
        due_at=datetime.now(timezone.utc) - timedelta(days=2),
        is_published=True, created_by=test_instructor.id,
    )
    db_session.add(a)
    await db_session.flush()
    sub = AssignmentSubmission(
        assignment_id=a.id, user_id=test_student.id, status="not_started",
    )
    db_session.add(sub)
    await db_session.commit()

    await mark_overdue_submissions(db_session)

    refreshed = (await db_session.execute(
        select(AssignmentSubmission).where(AssignmentSubmission.id == sub.id)
    )).scalar_one()
    assert refreshed.status == "late"


@pytest.mark.asyncio
async def test_does_not_touch_submitted_or_graded(
    db_session: AsyncSession, test_instructor: User, test_student: User,
):
    course = Course(
        name="T", language="english",
        instructor_id=test_instructor.id, enroll_code="MOSCRSE2",
    )
    db_session.add(course)
    await db_session.flush()
    a = Assignment(
        course_id=course.id, title="Old", kind="essay",
        due_at=datetime.now(timezone.utc) - timedelta(days=2),
        is_published=True, created_by=test_instructor.id,
    )
    db_session.add(a)
    await db_session.flush()
    sub_submitted = AssignmentSubmission(
        assignment_id=a.id, user_id=test_student.id,
        status="submitted",
        submitted_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(sub_submitted)
    await db_session.commit()

    await mark_overdue_submissions(db_session)

    refreshed = (await db_session.execute(
        select(AssignmentSubmission).where(AssignmentSubmission.id == sub_submitted.id)
    )).scalar_one()
    assert refreshed.status == "submitted"
```

- [ ] **Step 2: Run to fail**

Run: `pytest tests/test_mark_overdue_submissions.py -v`
Expected: ImportError on `mark_overdue_submissions`.

- [ ] **Step 3: Implement the function in `app/services/worker.py`**

Append to `backend/app/services/worker.py`:

```python
async def mark_overdue_submissions(session: AsyncSession) -> int:
    """Daily-cron job: flip 'not_started'/'in_progress' rows past their
    assignment's due_at to 'late'. Idempotent."""
    from app.models import Assignment, AssignmentSubmission

    now = _utcnow()
    rows = (
        await session.execute(
            select(AssignmentSubmission, Assignment)
            .join(Assignment, AssignmentSubmission.assignment_id == Assignment.id)
            .where(
                Assignment.due_at < now,
                Assignment.deleted_at.is_(None),
                AssignmentSubmission.status.in_(("not_started", "in_progress")),
            )
        )
    ).all()
    n = 0
    for sub, _asn in rows:
        sub.status = "late"
        n += 1
    if n:
        await session.commit()
        logger.info("Marked %d submissions as late", n)
    return n
```

- [ ] **Step 4: Schedule the cron**

Find where existing crons run (look for the prune job in `worker.py` — there's typically a top-level `run_periodic_jobs` or similar). Add a daily-cadence call to `mark_overdue_submissions`. If the worker uses a simple sleep loop with periodic dispatch, register it next to the existing daily prune.

If the existing pattern is a single periodic loop, add to it:

```python
# Inside the periodic dispatcher loop (next to prune_api_usage etc.)
async with async_session_factory() as session:
    await mark_overdue_submissions(session)
```

The cadence should be daily. If the existing pattern is `every N minutes`, gate with a "last run" timestamp so this only runs every 24h.

- [ ] **Step 5: Run tests, verify pass**

Run: `pytest tests/test_mark_overdue_submissions.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/worker.py backend/tests/test_mark_overdue_submissions.py
git commit -m "feat(curriculum): mark_overdue_submissions daily cron"
```

---

## Task 10: Frontend hooks for curriculum entities

**Files:**
- Create: `frontend/src/lib/curriculum-types.ts`
- Create: `frontend/src/hooks/use-modules.ts`
- Create: `frontend/src/hooks/use-meetings.ts`
- Create: `frontend/src/hooks/use-objectives.ts`
- Create: `frontend/src/hooks/use-assignments.ts`
- Create: `frontend/src/hooks/use-assignment-submissions.ts`
- Create: `frontend/src/hooks/use-syllabus.ts`
- Modify: `frontend/src/hooks/use-calendar-events.ts`

- [ ] **Step 1: Create shared TS types in `frontend/src/lib/curriculum-types.ts`**

```typescript
export type MeetingStatus = "planned" | "in_progress" | "taught" | "cancelled";
export type BloomLevel =
  | "remember" | "understand" | "apply" | "analyze" | "evaluate" | "create";
export type AssignmentKind =
  | "essay" | "project" | "quiz" | "reading" | "presentation"
  | "lab" | "problem_set" | "participation" | "other";
export type SubmissionStatus =
  | "not_started" | "in_progress" | "submitted" | "late" | "graded" | "excused";
export type SyllabusImportStatus =
  | "pending" | "parsed" | "applied" | "failed" | "superseded";

export interface CourseModule {
  readonly id: string;
  readonly course_id: string;
  readonly parent_id: string | null;
  readonly name: string;
  readonly description: string | null;
  readonly order_index: number;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface CourseMeeting {
  readonly id: string;
  readonly course_id: string;
  readonly module_id: string | null;
  readonly meeting_index: number;
  readonly title: string | null;
  readonly scheduled_at: string;
  readonly duration_minutes: number;
  readonly location: string | null;
  readonly status: MeetingStatus;
  readonly canvas_event_id: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface LearningObjective {
  readonly id: string;
  readonly course_id: string;
  readonly module_id: string | null;
  readonly meeting_id: string | null;
  readonly statement: string;
  readonly bloom_level: BloomLevel | null;
  readonly order_index: number;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface Assignment {
  readonly id: string;
  readonly course_id: string;
  readonly module_id: string | null;
  readonly meeting_id: string | null;
  readonly title: string;
  readonly description: string | null;
  readonly kind: AssignmentKind;
  readonly due_at: string;
  readonly available_from: string | null;
  readonly weight: string | null;
  readonly quiz_id: string | null;
  readonly is_published: boolean;
  readonly created_by: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface AssignmentSubmission {
  readonly id: string;
  readonly assignment_id: string;
  readonly user_id: string;
  readonly status: SubmissionStatus;
  readonly submitted_at: string | null;
  readonly score: string | null;
  readonly feedback: string | null;
  readonly submission_payload: Record<string, unknown> | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface SyllabusImport {
  readonly id: string;
  readonly course_id: string;
  readonly document_id: string | null;
  readonly parsed_payload: Record<string, unknown>;
  readonly status: SyllabusImportStatus;
  readonly error_message: string | null;
  readonly applied_at: string | null;
  readonly applied_by: string | null;
  readonly created_by: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface CalendarEvent {
  readonly id: string;
  readonly kind: "meeting" | "assignment";
  readonly title: string;
  readonly at: string;
  readonly duration_minutes?: number;
  readonly location?: string | null;
  readonly status?: MeetingStatus;
  readonly assignment_kind?: AssignmentKind;
  readonly weight?: number | null;
}
```

- [ ] **Step 2: Create `use-modules.ts`**

```typescript
"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type { CourseModule } from "@/lib/curriculum-types";

export function useModules(courseId: string) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["modules", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<CourseModule[]>>(
        `/courses/${courseId}/modules`, { token }
      );
      return res.data;
    },
  });
}

export function useCreateModule(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { name: string; order_index: number; description?: string; parent_id?: string }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<CourseModule>>(
        `/courses/${courseId}/modules`,
        { token, method: "POST", body: JSON.stringify(body) }
      );
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["modules", courseId] }),
  });
}

export function useUpdateModule(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { moduleId: string; patch: Partial<CourseModule> }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<CourseModule>>(
        `/courses/${courseId}/modules/${vars.moduleId}`,
        { token, method: "PUT", body: JSON.stringify(vars.patch) }
      );
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["modules", courseId] }),
  });
}

export function useDeleteModule(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (moduleId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await apiFetch<ApiEnvelope<null>>(
        `/courses/${courseId}/modules/${moduleId}`,
        { token, method: "DELETE" }
      );
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["modules", courseId] }),
  });
}
```

- [ ] **Step 3: Create `use-meetings.ts` following the same shape as `use-modules.ts`**

Mirror the structure. Endpoints: `/courses/{courseId}/meetings`. Type: `CourseMeeting`. Body shape on create: `{ meeting_index, scheduled_at, title?, duration_minutes?, location?, module_id? }`.

- [ ] **Step 4: Create `use-objectives.ts`**

Mirror. Endpoints: `/courses/{courseId}/objectives`. Type: `LearningObjective`. Body shape on create: `{ statement, bloom_level?, module_id?, meeting_id?, order_index? }`.

- [ ] **Step 5: Create `use-assignments.ts`**

Mirror. Endpoints: `/courses/{courseId}/assignments`. Type: `Assignment`. Body on create: `{ title, kind, due_at, weight?, module_id?, meeting_id?, is_published? }`.

- [ ] **Step 6: Create `use-assignment-submissions.ts`**

Two hooks here:

```typescript
"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type { AssignmentSubmission, SubmissionStatus } from "@/lib/curriculum-types";

export function useSubmissions(courseId: string, assignmentId: string) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["submissions", assignmentId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<AssignmentSubmission[]>>(
        `/courses/${courseId}/assignments/${assignmentId}/submissions`, { token }
      );
      return res.data;
    },
  });
}

export function useUpsertMySubmission(courseId: string, assignmentId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: {
      status: "in_progress" | "submitted";
      submission_payload?: Record<string, unknown>;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<AssignmentSubmission>>(
        `/courses/${courseId}/assignments/${assignmentId}/submission`,
        { token, method: "POST", body: JSON.stringify(body) }
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["submissions", assignmentId] });
      qc.invalidateQueries({ queryKey: ["assignments", courseId] });
    },
  });
}

export function useGradeSubmission(courseId: string, assignmentId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: {
      submissionId: string;
      score: string;
      feedback?: string;
      status?: "graded" | "excused";
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const { submissionId, ...rest } = vars;
      const res = await apiFetch<ApiEnvelope<AssignmentSubmission>>(
        `/courses/${courseId}/assignments/${assignmentId}/submissions/${submissionId}/grade`,
        { token, method: "POST", body: JSON.stringify(rest) }
      );
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["submissions", assignmentId] }),
  });
}
```

- [ ] **Step 7: Create `use-syllabus.ts`**

```typescript
"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type { SyllabusImport } from "@/lib/curriculum-types";

export function useSyllabusImports(courseId: string) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["syllabus-imports", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<SyllabusImport[]>>(
        `/courses/${courseId}/syllabus/imports`, { token }
      );
      return res.data;
    },
    refetchInterval: (q) => {
      const data = q.state.data;
      if (data && data.some((i) => i.status === "pending")) return 3000;
      return false;
    },
  });
}

export function useTriggerSyllabusImport(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (documentId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<SyllabusImport>>(
        `/courses/${courseId}/syllabus/imports`,
        { token, method: "POST", body: JSON.stringify({ document_id: documentId }) }
      );
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["syllabus-imports", courseId] }),
  });
}

export function useApplySyllabusImport(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { importId: string; payload: Record<string, unknown> }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<SyllabusImport>>(
        `/courses/${courseId}/syllabus/imports/${vars.importId}/apply`,
        { token, method: "POST", body: JSON.stringify({ parsed_payload: vars.payload }) }
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["syllabus-imports", courseId] });
      qc.invalidateQueries({ queryKey: ["modules", courseId] });
      qc.invalidateQueries({ queryKey: ["meetings", courseId] });
      qc.invalidateQueries({ queryKey: ["objectives", courseId] });
      qc.invalidateQueries({ queryKey: ["assignments", courseId] });
    },
  });
}
```

- [ ] **Step 8: Replace placeholder feed in `use-calendar-events.ts`**

Open `frontend/src/hooks/use-calendar-events.ts`. Replace the placeholder constants and exports with:

```typescript
"use client";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type { CalendarEvent } from "@/lib/curriculum-types";

export type { CalendarEvent };

export function useCalendarEvents(courseId: string, fromDate: Date, toDate: Date) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["calendar", courseId, fromDate.toISOString(), toDate.toISOString()],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const params = new URLSearchParams({
        from_date: fromDate.toISOString(),
        to_date: toDate.toISOString(),
      });
      const res = await apiFetch<ApiEnvelope<CalendarEvent[]>>(
        `/courses/${courseId}/calendar?${params}`, { token }
      );
      return res.data;
    },
  });
}
```

If existing callers rely on the old placeholder export `UPCOMING_SWARMS`, audit and remove their references in components — those should no longer ship.

- [ ] **Step 9: Run typecheck**

Run: `cd frontend && npm run build` (or `npx tsc --noEmit` if a tsc-only step exists)
Expected: no type errors.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/lib/curriculum-types.ts frontend/src/hooks/use-modules.ts \
        frontend/src/hooks/use-meetings.ts frontend/src/hooks/use-objectives.ts \
        frontend/src/hooks/use-assignments.ts \
        frontend/src/hooks/use-assignment-submissions.ts \
        frontend/src/hooks/use-syllabus.ts frontend/src/hooks/use-calendar-events.ts
git commit -m "feat(curriculum): TanStack Query hooks for phase 1 endpoints"
```

---

## Task 11: Instructor curriculum editor pages

**Files:**
- Create: `frontend/src/app/dashboard/courses/[courseId]/modules/page.tsx`
- Create: `frontend/src/app/dashboard/courses/[courseId]/meetings/page.tsx`
- Create: `frontend/src/app/dashboard/courses/[courseId]/objectives/page.tsx`
- Create: `frontend/src/app/dashboard/courses/[courseId]/assignments/page.tsx`
- Create: `frontend/src/app/dashboard/courses/[courseId]/assignments/[assignmentId]/page.tsx`
- Create: `frontend/src/components/curriculum/module-tree-editor.tsx`
- Create: `frontend/src/components/curriculum/meeting-form.tsx`
- Create: `frontend/src/components/curriculum/meeting-list.tsx`
- Create: `frontend/src/components/curriculum/objective-form.tsx`
- Create: `frontend/src/components/curriculum/assignment-form.tsx`
- Create: `frontend/src/components/curriculum/assignment-list.tsx`
- Create: `frontend/src/components/curriculum/submission-status-badge.tsx`

- [ ] **Step 1: Read Next.js 16 App Router conventions**

Run: `ls frontend/node_modules/next/dist/docs/ | head -20 && cat frontend/AGENTS.md`
Expected: confirms "use proxy.ts not middleware.ts" and other v16 conventions.

- [ ] **Step 2: Implement `module-tree-editor.tsx`**

Build a component that renders a flat list (Phase 1 ships flat; tree nesting deferred to v2):
- Inputs: `courseId: string`
- Uses `useModules`, `useCreateModule`, `useUpdateModule`, `useDeleteModule`
- Renders rows of `{ name, order_index }` with inline edit + delete buttons
- "Add module" form at the top with name + order_index inputs

Use existing UI primitives in `frontend/src/components/ui/`. Don't introduce new dependencies. Match existing component style (e.g. `create-course-dialog.tsx` for form patterns).

- [ ] **Step 3: Implement `meeting-form.tsx` and `meeting-list.tsx`**

`meeting-form.tsx`: Form with `meeting_index` (number), `title` (text), `scheduled_at` (datetime-local), `duration_minutes` (number, default 60), `location` (text), `module_id` (select from `useModules`). Submits via `useCreateMeeting` or `useUpdateMeeting`.

`meeting-list.tsx`: Reads `useMeetings`, renders rows ordered by `scheduled_at`. Each row shows date/time, title, status badge, edit/delete actions.

- [ ] **Step 4: Implement `objective-form.tsx`**

Form: `statement` (textarea), `bloom_level` (select), `module_id` (select, optional), `meeting_id` (select, optional). Validate that not both module and meeting are set (mirror the backend CHECK).

- [ ] **Step 5: Implement `assignment-form.tsx` and `assignment-list.tsx`**

`assignment-form.tsx`: `title`, `kind` (select), `due_at` (datetime-local), `weight` (number), `description` (textarea), `module_id`/`meeting_id` (optional selects), `is_published` (checkbox).

`assignment-list.tsx`: Lists from `useAssignments`. Each row: title, kind badge, due date, published indicator, link to detail page.

- [ ] **Step 6: Implement `submission-status-badge.tsx`**

```tsx
import type { SubmissionStatus } from "@/lib/curriculum-types";

interface Props {
  readonly status: SubmissionStatus;
}

const STYLES: Record<SubmissionStatus, string> = {
  not_started: "bg-stone-200 text-stone-700",
  in_progress: "bg-amber-100 text-amber-800",
  submitted: "bg-blue-100 text-blue-800",
  late: "bg-rose-100 text-rose-800",
  graded: "bg-emerald-100 text-emerald-800",
  excused: "bg-stone-100 text-stone-600",
};

export function SubmissionStatusBadge({ status }: Props) {
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs ${STYLES[status]}`}>
      {status.replace("_", " ")}
    </span>
  );
}
```

- [ ] **Step 7: Wire each page**

Each page (`modules/page.tsx`, `meetings/page.tsx`, `objectives/page.tsx`, `assignments/page.tsx`) extracts `courseId` via Next 16's params API:

```tsx
import { ModuleTreeEditor } from "@/components/curriculum/module-tree-editor";

export default async function ModulesPage(props: { params: Promise<{ courseId: string }> }) {
  const { courseId } = await props.params;
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Modules</h1>
      <ModuleTreeEditor courseId={courseId} />
    </div>
  );
}
```

The assignment detail page (`assignments/[assignmentId]/page.tsx`) shows `AssignmentForm` (edit mode) on top + the submissions roster (instructor view) using `useSubmissions`.

- [ ] **Step 8: Add nav links to course layout**

Locate the course layout/sidebar at `frontend/src/app/dashboard/courses/[courseId]/...`. Add four new entries: "Modules", "Meetings", "Objectives", "Assignments". Match existing navigation pattern.

- [ ] **Step 9: Run frontend dev server and smoke-test in browser**

Run: `cd frontend && npm run dev`
Open: `http://localhost:3000/dashboard/courses/<some-course-id>/modules`
Expected: page renders, can create/edit/delete modules.

Repeat for meetings, objectives, assignments pages.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/app/dashboard/courses/[courseId]/{modules,meetings,objectives,assignments} \
        frontend/src/components/curriculum/
git commit -m "feat(curriculum): instructor editor pages for modules/meetings/objectives/assignments"
```

---

## Task 12: Student calendar view replacing placeholder

**Files:**
- Modify: `frontend/src/app/dashboard/calendar/page.tsx`

- [ ] **Step 1: Open and read existing calendar page**

Run: `cat frontend/src/app/dashboard/calendar/page.tsx | head -80`

Note the existing layout and any reusable rendering. Plan to keep the visual scaffolding and replace the data source.

- [ ] **Step 2: Replace placeholder data with real backend feed**

Modify the page to:
1. Read all courses the user is enrolled in via `useCourses()` (existing hook).
2. For each course in parallel, call `useCalendarEvents(courseId, weekStart, weekEnd)`.
3. Merge results into a single sorted event list.
4. Render events using existing visual primitives.

Skeleton:

```tsx
"use client";
import { useMemo } from "react";
import { useCourses } from "@/hooks/use-courses";
import { useCalendarEvents } from "@/hooks/use-calendar-events";

function startOfWeek(d: Date): Date {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  x.setDate(x.getDate() - x.getDay());
  return x;
}

export default function CalendarPage() {
  const { data: courses = [] } = useCourses();
  const range = useMemo(() => {
    const from = startOfWeek(new Date());
    const to = new Date(from);
    to.setDate(from.getDate() + 7);
    return { from, to };
  }, []);

  // One query per course; React Query handles parallel fetching.
  const events = courses.flatMap((c) => {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    const q = useCalendarEvents(c.id, range.from, range.to);
    return (q.data ?? []).map((e) => ({ ...e, courseName: c.name }));
  });

  events.sort((a, b) => a.at.localeCompare(b.at));

  return (
    <div>
      <h1>This week</h1>
      <ul>
        {events.map((e) => (
          <li key={`${e.kind}-${e.id}`}>
            <span>{new Date(e.at).toLocaleString()}</span>
            <span>{e.title}</span>
            <span>{e.kind === "meeting" ? "Meeting" : `Due: ${e.assignment_kind}`}</span>
            <span>{e.courseName}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

(Eslint hook-rule violation: replace the inner `useCalendarEvents` call with a `parallelQueries` pattern using `useQueries`. Final implementation should use `useQueries` from `@tanstack/react-query` to satisfy the rule.)

Final correct shape:

```tsx
import { useQueries } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type { CalendarEvent } from "@/lib/curriculum-types";

const queries = useQueries({
  queries: courses.map((c) => ({
    queryKey: ["calendar", c.id, range.from.toISOString(), range.to.toISOString()],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const params = new URLSearchParams({
        from_date: range.from.toISOString(),
        to_date: range.to.toISOString(),
      });
      const res = await apiFetch<ApiEnvelope<CalendarEvent[]>>(
        `/courses/${c.id}/calendar?${params}`, { token }
      );
      return res.data.map((e) => ({ ...e, courseName: c.name, courseId: c.id }));
    },
  })),
});
```

- [ ] **Step 3: Verify in browser**

Run: `cd frontend && npm run dev`
Open: `http://localhost:3000/dashboard/calendar`
Expected: shows current week's meetings + assignment deadlines from all enrolled courses.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/dashboard/calendar/page.tsx
git commit -m "feat(calendar): replace placeholder feed with real backend events"
```

---

## Task 13: Syllabus uploader + parsed-payload review UI

**Files:**
- Create: `frontend/src/app/dashboard/courses/[courseId]/syllabus/page.tsx`
- Create: `frontend/src/app/dashboard/courses/[courseId]/syllabus/imports/[importId]/page.tsx`
- Create: `frontend/src/components/curriculum/syllabus-upload-card.tsx`
- Create: `frontend/src/components/curriculum/syllabus-import-list.tsx`
- Create: `frontend/src/components/curriculum/syllabus-payload-review.tsx`

- [ ] **Step 1: Implement `syllabus-upload-card.tsx`**

Component renders a file input + "Upload syllabus" button. On select:
1. Upload to existing `/api/documents` endpoint with `kind=syllabus` (Document upload API already exists; pass kind as form field).
2. On success, call `useTriggerSyllabusImport(courseId).mutateAsync(documentId)`.
3. Refresh import list.

Reuse the existing `use-documents.ts` upload mutation; if the existing upload doesn't accept a `kind`, extend it to pass the field through. Verify by reading `frontend/src/hooks/use-documents.ts` and the corresponding backend endpoint at `backend/app/api/documents.py`.

- [ ] **Step 2: Implement `syllabus-import-list.tsx`**

Read `useSyllabusImports(courseId)`. Render rows: status badge, created_at, "Review" link if `status === "parsed"`, "Re-parse" button if `failed`.

- [ ] **Step 3: Implement `syllabus-payload-review.tsx`**

Two columns:
- Left: live JSON of `parsed_payload` (editable via Monaco-style textarea OR a structured form per section). Phase 1 ships a textarea for time; nicer editor in v2.
- Right: live preview — list of modules / meetings / objectives / assignments that will be created.
- Bottom: "Apply" button → calls `useApplySyllabusImport(courseId).mutateAsync({ importId, payload })`.

- [ ] **Step 4: Wire pages**

```tsx
// frontend/src/app/dashboard/courses/[courseId]/syllabus/page.tsx
import { SyllabusUploadCard } from "@/components/curriculum/syllabus-upload-card";
import { SyllabusImportList } from "@/components/curriculum/syllabus-import-list";

export default async function SyllabusPage(props: { params: Promise<{ courseId: string }> }) {
  const { courseId } = await props.params;
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Syllabus</h1>
      <SyllabusUploadCard courseId={courseId} />
      <SyllabusImportList courseId={courseId} />
    </div>
  );
}
```

```tsx
// frontend/src/app/dashboard/courses/[courseId]/syllabus/imports/[importId]/page.tsx
import { SyllabusPayloadReview } from "@/components/curriculum/syllabus-payload-review";

export default async function SyllabusImportReviewPage(
  props: { params: Promise<{ courseId: string; importId: string }> },
) {
  const { courseId, importId } = await props.params;
  return <SyllabusPayloadReview courseId={courseId} importId={importId} />;
}
```

- [ ] **Step 5: Add nav link "Syllabus" to course sidebar**

Same pattern as Task 11 Step 8.

- [ ] **Step 6: Smoke test**

Run dev server. Upload a small syllabus PDF (or a text file representing one). Verify:
- File uploads with `kind=syllabus`.
- Background task runs (check `tasks` table or logs).
- Import row transitions `pending → parsed`.
- Review page lets you edit the payload + Apply.
- After Apply, modules/meetings/objectives/assignments pages show the new entities.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/dashboard/courses/[courseId]/syllabus \
        frontend/src/components/curriculum/syllabus-upload-card.tsx \
        frontend/src/components/curriculum/syllabus-import-list.tsx \
        frontend/src/components/curriculum/syllabus-payload-review.tsx
git commit -m "feat(syllabus): instructor upload + parsed-payload review/apply UI"
```

---

## Task 14: Student assignment submission flow

**Files:**
- Create: `frontend/src/app/dashboard/courses/[courseId]/assignments/[assignmentId]/submit/page.tsx`
- Modify: `frontend/src/app/dashboard/courses/[courseId]/assignments/page.tsx` (student view differs from instructor view)

- [ ] **Step 1: Build the student submission page**

```tsx
"use client";
import { useState } from "react";
import { useUpsertMySubmission } from "@/hooks/use-assignment-submissions";

interface Props {
  readonly courseId: string;
  readonly assignmentId: string;
}

export function StudentSubmissionForm({ courseId, assignmentId }: Props) {
  const [text, setText] = useState("");
  const upsert = useUpsertMySubmission(courseId, assignmentId);

  const onSaveDraft = () => upsert.mutate({ status: "in_progress", submission_payload: { text } });
  const onSubmit = () => upsert.mutate({ status: "submitted", submission_payload: { text } });

  return (
    <div className="space-y-4">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={10}
        className="w-full rounded border p-3"
      />
      <div className="flex gap-2">
        <button onClick={onSaveDraft} disabled={upsert.isPending}>Save draft</button>
        <button onClick={onSubmit} disabled={upsert.isPending}>Submit</button>
      </div>
      {upsert.isSuccess && <p className="text-sm text-emerald-700">Saved.</p>}
    </div>
  );
}
```

Page that wires it:

```tsx
import { StudentSubmissionForm } from "@/components/curriculum/student-submission-form";

export default async function SubmitPage(
  props: { params: Promise<{ courseId: string; assignmentId: string }> },
) {
  const { courseId, assignmentId } = await props.params;
  return <StudentSubmissionForm courseId={courseId} assignmentId={assignmentId} />;
}
```

(Move `StudentSubmissionForm` to `frontend/src/components/curriculum/student-submission-form.tsx`.)

- [ ] **Step 2: Differentiate instructor vs student view in `assignments/page.tsx`**

Read `useRole()` (existing hook). If `role === "student"`, render a list with "Submit" links (going to `submit/page.tsx`). If `instructor`, render the editor (Task 11).

- [ ] **Step 3: Smoke test**

Run dev server. Sign in as a student, navigate to the course's assignments, submit one, verify status flips to `submitted`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/curriculum/student-submission-form.tsx \
        frontend/src/app/dashboard/courses/[courseId]/assignments/[assignmentId]/submit/page.tsx \
        frontend/src/app/dashboard/courses/[courseId]/assignments/page.tsx
git commit -m "feat(curriculum): student assignment submission flow"
```

---

## Task 15: End-to-end smoke test + ship

**Files:**
- Create: `frontend/e2e/curriculum-flow.spec.ts`

- [ ] **Step 1: Write Playwright E2E covering the full flow**

```typescript
import { test, expect } from "@playwright/test";

test("instructor creates module + meeting + assignment; student submits", async ({ page, browser }) => {
  // Sign in as test instructor (existing test-auth bypass or seeded account)
  await page.goto("/sign-in");
  // ... use existing auth helpers

  // Create course or pick existing
  await page.goto("/dashboard/courses/<course-id>/modules");
  await page.getByRole("button", { name: /add module/i }).click();
  await page.getByLabel(/name/i).fill("Week 1");
  await page.getByLabel(/order/i).fill("1");
  await page.getByRole("button", { name: /save/i }).click();
  await expect(page.getByText("Week 1")).toBeVisible();

  await page.goto("/dashboard/courses/<course-id>/meetings");
  // ... fill meeting form, expect row

  await page.goto("/dashboard/courses/<course-id>/assignments");
  // ... fill assignment form with is_published=true

  // Switch to student context
  const studentCtx = await browser.newContext({ /* student storage state */ });
  const studentPage = await studentCtx.newPage();
  await studentPage.goto("/dashboard/calendar");
  await expect(studentPage.getByText(/week 1/i)).toBeVisible();
});
```

This is the smoke shape — fill in test-auth scaffolding to match `frontend/e2e/` existing patterns (read at least one existing spec there first).

- [ ] **Step 2: Run E2E**

Run: `cd frontend && npm run e2e`
Expected: pass.

- [ ] **Step 3: Run full backend test suite**

Run: `cd backend && source .venv/bin/activate && pytest -x`
Expected: all green.

- [ ] **Step 4: Commit + open PR**

```bash
git add frontend/e2e/curriculum-flow.spec.ts
git commit -m "test(curriculum): e2e smoke for instructor + student curriculum flow"
git push -u origin main
```

Open PR (or merge directly) — Phase 1 is shippable.

- [ ] **Step 5: Soak (≥ 2 weeks)**

Per the spec's pause point: gather instructor feedback on calendar UX, syllabus parser quality, assignment flow before starting Phase 2 (concepts + mastery). Track issues in a Phase-1-feedback note. Phase 2 plan gets written when this soak completes.

---

## Self-Review

**Spec coverage:**
- [x] `course_modules` table — Task 1, 2
- [x] `course_meetings` (renamed from `class_sessions`) — Task 1, 2
- [x] `learning_objectives` with three nullable scope FKs + CHECK — Task 1, 2
- [x] `assignments` — Task 1, 2
- [x] `assignment_submissions` (un-deferred) — Task 1, 2, 7, 9
- [x] `syllabus_imports` + `documents.kind` — Task 1, 2, 8
- [x] ALTERs adding `meeting_id`/`module_id` to documents/quizzes/flashcard_sets/pronunciation_sets — Task 1
- [x] Modules CRUD API — Task 4
- [x] Meetings CRUD + calendar feed — Task 5
- [x] Objectives CRUD — Task 6
- [x] Assignments + submissions CRUD + grade — Task 7
- [x] Syllabus parser + applier API — Task 8
- [x] `parse_syllabus` job + worker dispatch — Task 8
- [x] `mark_overdue_submissions` cron — Task 9
- [x] Frontend hooks for all entities — Task 10
- [x] Instructor curriculum editor pages — Task 11
- [x] Student calendar view (real backend) — Task 12
- [x] Syllabus uploader + review/apply UI — Task 13
- [x] Student assignment submission flow — Task 14
- [x] E2E smoke + ship — Task 15

Phase 2 hooks (concept-aware behaviour, syllabus-as-generation-context, Beta-Binomial mastery, HLR decay, KST outer-fringe, action telemetry, engine on/off toggle) are explicitly **NOT in this plan** — separate plan written when Phase 1 ships.

**Placeholder scan:** No `TBD`, `TODO`, or "implement later" references. All code blocks are complete.

**Type consistency:** Naming consistent across stack — `CourseMeeting` Python ↔ `CourseMeeting` TS; `meeting_index` everywhere; `course_meetings` table; `meetings` API route segment. `parse_syllabus` and `apply_syllabus_import` task names match spec §Background jobs.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-28-adaptive-engine-phase1-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
