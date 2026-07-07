# P2 — Student Entry & Enrollment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. TDD is mandatory: failing test first for every backend behavior.

**Goal:** Ship the student join funnel and its server-side join gate. Add an `enrollments.status` lifecycle (`pending`/`active`/`rejected`) so `join_mode='code_plus_approval'` courses require teacher approval; introduce `readiness_responses` — the FIRST student-owned table in this build, so **RLS lands here** (pattern migration `28236be3d7b3`); drive the eligibility-survey / ready-check / diagnostic / recommendation funnel from the **pilot config** (not the DB); reuse `assert_course_open` (P1) as the join gate; and build the student join funnel `/student/join` (Figma S003–S013) plus the teacher course-overview / schedule / enrollment / roster / join-approval / code-modal / score-categories screens (Figma T029–T035).

**Architecture:** Extend-in-place. Enrollment gains a `status` column and a CHECK; `enroll-by-code` becomes gate-aware (`assert_course_open` → `SETUP_NOT_OPEN`), code-state-aware (`enroll_code_active` → `JOIN_CODE_INACTIVE`), and `join_mode`-aware (`code` → `active` = instant join; `code_plus_approval` → `pending` = awaits approval). A new `readiness.py` router persists survey answers to `readiness_responses` (RLS-protected, owner-isolated on `user_id`) and computes a config-driven recommendation whose claim-limit copy comes from `pilot.claim_limits`. `courses.py` grows join-request approve/deny + roster endpoints. The frontend join funnel is a `StepWizard` (P1 pattern) reading readiness definitions from `usePilotConfig`.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic + Pydantic v2 + pytest; Next.js 16 App Router + React 19 + TanStack Query + next-intl + Playwright/vitest.

---

## Session bootstrap (read before any code)

1. Read `docs/superpowers/plans/2026-07-07-meli-cle-roadmap.md` — **Global Rules** + the P2 brief + the P1 handoff log (what P1 shipped that P2 builds on).
2. Read the spec `docs/superpowers/specs/2026-07-06-meli-cle-checkpoint-loop-design.md` §3.4 (gates — `SETUP_NOT_OPEN` reused), §4.7 (`readiness_responses` + join approval), §4.8 (setup gate), §5 (`readiness.py` + courses.py extend rows).
3. Read this plan top-to-bottom, plus the real files each task names — **do not guess signatures**.
4. Windows dev env: backend venv at `backend/.venv`; Docker Postgres 17 + pgvector up (`docker compose up -d`); `langassistant_test` DB created with the same creds. Backend tests run from `backend/` as `.\.venv\Scripts\python.exe -m pytest`. Frontend runs from `frontend/` via `npx`.
5. Branch: `feat/cle-p0-shell` (P2 commits land here until the phase PR — same branch P0/P1 used).
6. **conftest fixtures are REAL — use them, do not invent names.** `backend/tests/conftest.py` provides: `db_session` (creates/drops all tables via `Base.metadata.create_all` on `langassistant_test`), `test_instructor`, `test_student`, `logged_in_user` (instructor), `async_client` (overrides `get_db` + `get_current_user` → `logged_in_user`), `client` (raw, no auth override), `async_engine` (the real dev `langassistant` engine, migrations applied — used by RLS tests). There is **no** `instructor_client` / `student_client` / `seed_course` / `owned_course` fixture — add local fixtures/helpers in each test module (create a `Course` + `Enrollment` with `db_session`) or override `get_current_user` inline, exactly as the existing `test_*` modules do (grep `tests/test_enroll_code_controls.py` + `tests/test_course_setup_columns.py` for the real patterns).
7. **Migrations are HAND-WRITTEN.** Autogenerate drifts (invents diffs from unrelated models) **and** omits CHECK constraints, partial indexes, and RLS/policy statements entirely. For each schema task: run `alembic revision -m "..."` to get a stamped empty file (or `--autogenerate` then **discard the drift**), then hand-write `upgrade`/`downgrade`. Set `down_revision` to the current head — P1 ended at `6500885d2cfc`; confirm with `.\.venv\Scripts\python.exe -m alembic heads` before writing. Apply with `.\.venv\Scripts\python.exe -m alembic upgrade head`.
8. **Figma:** file key `EhzLyFCTZBIGU4iNyHUqvl`, page `final` (`1372:2`). Student funnel group `1372:198` ("Student flow group - 1. Entry and Readiness"); teacher group `1372:66` ("Teacher flow group - 3. Course Overview and Enrollment"). Node ids pulled at plan-write time (tables below); call `get_design_context` per node before building each screen. Wireframes are abstract — follow flow + content structure, apply our enterprise visual design with tokens only.

**Figma node ids — student funnel (S003–S013, group `1372:198`):**

| Screen | Node id | Screen | Node id |
|---|---|---|---|
| S003 join-course-code | `1372:204` | S009 recommendation-result | `1372:216` |
| S004 invalid-inactive-join-code | `1372:206` | S010 deep-course-preview | `1372:218` |
| S005 short-course-preview | `1372:208` | S011 readiness-summary | `1372:220` |
| S006 eligibility-survey | `1372:210` | S012 course-not-open-yet | `1372:222` |
| S007 ready-check | `1372:212` | S013 join-success | `1372:224` |
| S008 optional-diagnostic-task | `1372:214` | | |

> S001/S002 (`1372:200`/`1372:202`) are the student sign-in / forgot-password screens — already shipped in P0; not in P2 scope.

**Figma node ids — teacher overview/enrollment (T029–T035, group `1372:66`):**

| Screen | Node id | Screen | Node id |
|---|---|---|---|
| T029 course-overview | `1372:68` | T033 join-request-approval | `1372:76` |
| T030 course-schedule-table | `1372:70` | T034 course-code-modal | `1372:78` |
| T031 enrollment-overview | `1372:72` | T035 course-score-categories | `1372:80` |
| T032 class-roster-detail | `1372:74` | | |

> T036 course-memory-summary (`1372:82`) is **deferred to P7** (course memory) — do not build it here.

---

## Decisions (reconciliation of spec vs existing schema — read first)

### Decision 1 — `enrollments.status` is NEW; `join_mode` maps to it (spec §4.7 vs `models/course.py`)

Spec §4.7 claims "`enrollments.status` already supports `pending`". **It does not** — `models/course.py::Enrollment` has only `role` (no status column). P2 **adds** `status ('pending'|'active'|'rejected')` with a CHECK constraint and `server_default='active'`.

**Decision:** Default `'active'` so every existing enrollment row (instructor self-enrollment on course create, prior student joins, Canvas roster claims in `deps.py`, `PendingEnrollment` claims) is backfilled `active` with zero behavior change — nothing today expects `pending`. `join_mode` (a P1 column) maps at join time:
- `join_mode='code'` → new enrollment created `status='active'` → instant join (S013 join-success).
- `join_mode='code_plus_approval'` → new enrollment created `status='pending'` → awaits teacher approval (pending-approval screen); approve → `active`, deny → `rejected`.

Instructor self-enrollment (`create_course`) and Canvas/`PendingEnrollment` claims always write `status='active'` explicitly. Access checks that currently do "is there an Enrollment row?" (e.g. `get_course` in `courses.py`, `list_courses` join) must be tightened to "is there an **active** Enrollment row?" so a `pending` student cannot read the workspace before approval — covered by tests in Task 6/7.

### Decision 2 — `readiness_responses` is the FIRST student-owned table → RLS lands in P2 (Global Rules; migration `28236be3d7b3` pattern)

P1 deliberately shipped no student-owned row tables, so RLS was deferred. P2's `readiness_responses` is student-owned (`user_id` is the owner), so this phase introduces the RLS migration for it, **hand-written** exactly like `28236be3d7b3_rls_student_owned_tables.py`:

```
ALTER TABLE readiness_responses ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS readiness_responses_owner_isolation ON readiness_responses;
CREATE POLICY readiness_responses_owner_isolation ON readiness_responses
  FOR ALL
  USING (user_id = current_setting('app.current_user_id', true)::uuid)
  WITH CHECK (user_id = current_setting('app.current_user_id', true)::uuid);
```

The GUC `app.current_user_id` is already set on every request by `deps.py::get_current_user` (`SELECT set_config('app.current_user_id', :uid, false)`). Enforcement runs under the non-superuser `meli_app` role (migration `6eb0c6b144eb`); `postgres` has `BYPASSRLS`. **Test-DB caveat:** the `db_session` fixture builds schema via `Base.metadata.create_all` (which never emits RLS/policies) as the `postgres` superuser, so it cannot enforce RLS. The RLS **isolation** test therefore runs against `async_engine` (the migrated dev DB) with `SET ROLE meli_app`, mirroring the existing `tests/test_rls_isolation.py` precedent — see Task 8 (with a skip-guard if the `meli_app` role is absent offline, matching the P0/P1 infra-limited-test convention). ORM models never declare RLS; it lives only in the migration.

### Decision 3 — reuse `assert_course_open` as the join gate (Decision 1 of P1 — single authority)

P1 exported `services/setup.py::assert_course_open(course)` which raises `SetupGateError("SETUP_NOT_OPEN", ...)` unless `course.context_status == 'approved'`. P2's `enroll-by-code` calls it **before** creating any enrollment, so students cannot join (or preview deeply / view the workspace) until the teacher published setup. No new gate logic; `context_status` stays the single authority. The router maps `SETUP_NOT_OPEN` → HTTP 409 with `detail={"code": "SETUP_NOT_OPEN", ...}`, which the funnel renders as S012 (course-not-open-yet). A parallel `JOIN_CODE_INACTIVE` code (from `enroll_code_active=False`) renders as S004.

### Decision 4 — readiness definitions come from pilot config, not the DB (spec §4.7; forward-compatible)

Survey / ready-check question definitions live in `pilot.readiness` (`ReadinessPhaseDef` list), NOT in a DB table. The backend validates a submitted phase against the config's known phases and stores raw `answers` + a computed `result` (JSONB). This keeps the funnel config-driven and forward-compatible: a future full placement test adds a new `phase` value (e.g. `placement_test`) + richer `result` with **no schema change**. Two config gaps to reconcile at build time:
- `pilot.readiness` currently defines only `eligibility_survey` + `ready_check` (see `pilot/cle.py`). The `readiness_responses.phase` CHECK must still accept `diagnostic` and `recommendation` (spec §4.7 enum) even though CLE ships no `diagnostic` question set today — the funnel treats diagnostic as **optional/skippable** (S008) and `recommendation` is **computed server-side**, not a question set.
- `ReadinessPhaseDef.phase` in `pilot/base.py` is typed `Literal["eligibility_survey", "ready_check", "diagnostic"]` — it already permits `diagnostic`; no config type change needed. `recommendation` is never a `ReadinessPhaseDef` (it has no questions), so leave the Literal as-is.

**Sub-decision (evidence seam):** readiness submissions are **pre-enrollment** and carry no concept tags, so they do **not** emit `learning_event`s or enqueue mastery tasks (the evidence seam is course-scoped, post-enrollment). This is a deliberate data-minimization boundary — documented so a reviewer doesn't flag a "missing evidence emission". `recommendation.result` carries `pilot.claim_limits['recommendation']` verbatim so the UI never fabricates placement authority.

---

### Task 1: `enrollments.status` — migration + model + schema (Decision 1)

**Files:**
- Modify: `backend/app/models/course.py`
- Modify: `backend/app/schemas/course.py` (`EnrollmentResponse` + create paths)
- Modify: `backend/app/api/courses.py` (`create_course` instructor enrollment sets `status='active'`), `backend/app/api/deps.py` (`PendingEnrollment` claim sets `status='active'`)
- Create: Alembic migration (hand-written)
- Test: `backend/tests/test_enrollment_status.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_enrollment_status.py
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.course import Course, Enrollment


async def _course(db_session, instructor):
    course = Course(
        name="LANG1511", language="zh", instructor_id=instructor.id,
        enroll_code="ABCD2345",
    )
    db_session.add(course)
    await db_session.flush()
    return course


@pytest.mark.asyncio
async def test_enrollment_defaults_active(db_session, test_instructor, test_student):
    course = await _course(db_session, test_instructor)
    e = Enrollment(course_id=course.id, user_id=test_student.id, role="student")
    db_session.add(e)
    await db_session.commit()
    await db_session.refresh(e)
    assert e.status == "active"


@pytest.mark.asyncio
async def test_enrollment_can_be_pending(db_session, test_instructor, test_student):
    course = await _course(db_session, test_instructor)
    e = Enrollment(
        course_id=course.id, user_id=test_student.id, role="student", status="pending",
    )
    db_session.add(e)
    await db_session.commit()
    await db_session.refresh(e)
    assert e.status == "pending"


@pytest.mark.asyncio
async def test_enrollment_status_check_constraint(db_session, test_instructor, test_student):
    course = await _course(db_session, test_instructor)
    e = Enrollment(
        course_id=course.id, user_id=test_student.id, role="student", status="nonsense",
    )
    db_session.add(e)
    with pytest.raises(IntegrityError):
        await db_session.commit()
```

- [ ] **Step 2: Run to verify FAIL** — from `backend/`: `.\.venv\Scripts\python.exe -m pytest tests/test_enrollment_status.py -v` → `TypeError`/`AttributeError` on the unknown `status`.

- [ ] **Step 3: Extend the model** — in `backend/app/models/course.py`, add to `Enrollment.__table_args__` (alongside the existing `UniqueConstraint`):

```python
        CheckConstraint(
            "status IN ('pending','active','rejected')",
            name="ck_enrollments_status_valid",
        ),
```

and the column (imports `CheckConstraint` and `text` already exist at the top of the file):

```python
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default=text("'active'")
    )
```

- [ ] **Step 4: Migration** — `.\.venv\Scripts\python.exe -m alembic revision -m "enrollments status column"`, then hand-write:

```python
def upgrade() -> None:
    op.add_column(
        "enrollments",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
    )
    op.create_check_constraint(
        "ck_enrollments_status_valid", "enrollments",
        "status IN ('pending','active','rejected')",
    )

def downgrade() -> None:
    op.drop_constraint("ck_enrollments_status_valid", "enrollments", type_="check")
    op.drop_column("enrollments", "status")
```

Set `down_revision` to the current head (`alembic heads`; expected `6500885d2cfc`). Apply: `.\.venv\Scripts\python.exe -m alembic upgrade head`.

- [ ] **Step 5: Callers write explicit `status='active'`** — in `api/courses.py::create_course` the instructor `Enrollment(...)` and in `api/deps.py` the `PendingEnrollment` claim `Enrollment(...)` — add `status="active"` explicitly (defensive; the server_default already covers it but the intent must be legible). Add `status: str` to `EnrollmentResponse` in `schemas/course.py`.

- [ ] **Step 6: Run to verify PASS** — `.\.venv\Scripts\python.exe -m pytest tests/test_enrollment_status.py tests/test_courses.py tests/test_pending_enrollment_claim.py -v` (run the existing enrollment suites to catch regressions).

- [ ] **Step 7: Commit** — `git add backend/app/models/course.py backend/app/schemas/course.py backend/app/api/courses.py backend/app/api/deps.py backend/alembic/versions backend/tests/test_enrollment_status.py && git commit -m "feat(enrollment): enrollments.status (pending|active|rejected) column + gate mapping"`

---

### Task 2: `readiness_responses` model + RLS migration (Decision 2, Decision 4)

**Files:**
- Create: `backend/app/models/readiness.py`
- Modify: `backend/app/models/__init__.py` (export `ReadinessResponse`)
- Create: Alembic migration (hand-written — table + CHECKs + partial unique index + RLS/policy)
- Test: `backend/tests/test_readiness_model.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_readiness_model.py
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.course import Course
from app.models.readiness import ReadinessResponse


async def _course(db_session, instructor):
    c = Course(name="LANG1511", language="zh", instructor_id=instructor.id, enroll_code="ABCD2345")
    db_session.add(c)
    await db_session.flush()
    return c


@pytest.mark.asyncio
async def test_readiness_defaults(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)
    r = ReadinessResponse(
        user_id=test_student.id, course_id=c.id, phase="eligibility_survey",
        answers={"prior_study": "1-3 years"},
    )
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)
    assert r.status == "in_progress"
    assert r.result == {}


@pytest.mark.asyncio
async def test_readiness_phase_check(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)
    r = ReadinessResponse(user_id=test_student.id, course_id=c.id, phase="bogus", answers={})
    db_session.add(r)
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_readiness_one_row_per_user_course_phase(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)
    db_session.add(ReadinessResponse(user_id=test_student.id, course_id=c.id, phase="ready_check", answers={}))
    await db_session.flush()
    db_session.add(ReadinessResponse(user_id=test_student.id, course_id=c.id, phase="ready_check", answers={}))
    with pytest.raises(IntegrityError):
        await db_session.commit()
```

- [ ] **Step 2: FAIL run** — `.\.venv\Scripts\python.exe -m pytest tests/test_readiness_model.py -v` → `ModuleNotFoundError`.

- [ ] **Step 3: `models/readiness.py`** — the `phase` CHECK accepts all four spec §4.7 values (forward-compatible per Decision 4); `answers`/`result` are JSONB; unique on `(user_id, course_id, phase)` so a resubmit upserts the latest (Task 3). No `SoftDeleteMixin` — readiness rows are not user-facing soft-deletable artifacts.

```python
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ReadinessResponse(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "readiness_responses"
    __table_args__ = (
        CheckConstraint(
            "phase IN ('eligibility_survey','ready_check','diagnostic','recommendation')",
            name="ck_readiness_responses_phase_valid",
        ),
        CheckConstraint(
            "status IN ('in_progress','completed')",
            name="ck_readiness_responses_status_valid",
        ),
        UniqueConstraint(
            "user_id", "course_id", "phase", name="uq_readiness_user_course_phase",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    phase: Mapped[str] = mapped_column(String(30), nullable=False)
    answers: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    result: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="in_progress",
        server_default=text("'in_progress'"),
    )
```

- [ ] **Step 4: Register model** — add `from app.models.readiness import ReadinessResponse` + `"ReadinessResponse"` to `__all__` in `backend/app/models/__init__.py`, following the existing export style (so `Base.metadata` includes the table for `create_all` in tests).

- [ ] **Step 5: Migration (table + RLS)** — `.\.venv\Scripts\python.exe -m alembic revision -m "readiness_responses table + RLS"`, hand-write `create_table` with both CHECKs + the unique constraint, then append the RLS block **exactly** mirroring `28236be3d7b3`:

```python
def upgrade() -> None:
    op.create_table(
        "readiness_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phase", sa.String(length=30), nullable=False),
        sa.Column("answers", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("result", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'in_progress'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("phase IN ('eligibility_survey','ready_check','diagnostic','recommendation')", name="ck_readiness_responses_phase_valid"),
        sa.CheckConstraint("status IN ('in_progress','completed')", name="ck_readiness_responses_status_valid"),
        sa.UniqueConstraint("user_id", "course_id", "phase", name="uq_readiness_user_course_phase"),
    )
    # RLS — first P2 student-owned table (Decision 2; pattern 28236be3d7b3).
    op.execute("ALTER TABLE readiness_responses ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS readiness_responses_owner_isolation ON readiness_responses")
    op.execute(
        "CREATE POLICY readiness_responses_owner_isolation ON readiness_responses "
        "FOR ALL "
        "USING (user_id = current_setting('app.current_user_id', true)::uuid) "
        "WITH CHECK (user_id = current_setting('app.current_user_id', true)::uuid)"
    )

def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS readiness_responses_owner_isolation ON readiness_responses")
    op.execute("ALTER TABLE readiness_responses DISABLE ROW LEVEL SECURITY")
    op.drop_table("readiness_responses")
```

Import `from sqlalchemy.dialects import postgresql` in the migration. The `meli_app` default-privilege grants (`6eb0c6b144eb`) already cover future tables, so no extra `GRANT` needed. Apply: `.\.venv\Scripts\python.exe -m alembic upgrade head`.

- [ ] **Step 6: PASS run** — `.\.venv\Scripts\python.exe -m pytest tests/test_readiness_model.py -v` → 3 passed. (The model tests run under `postgres` via `create_all`, so RLS is not exercised here — that's Task 8.)

- [ ] **Step 7: Commit** — `git commit -am "feat(readiness): readiness_responses model + RLS migration (first P2 student-owned table)"`

---

### Task 3: readiness service — config-driven phase validation + recommendation (Decision 4)

**Files:**
- Create: `backend/app/services/readiness.py`
- Test: `backend/tests/test_readiness_service.py`

The service validates a submitted phase against `pilot.readiness` (known question sets) + the computed phases (`recommendation`), upserts a `readiness_responses` row (unique `(user, course, phase)`), and for `recommendation` composes a `result` carrying `pilot.claim_limits['recommendation']`. Owns typed errors reusing the P1 `SetupGateError` shape or a local `ReadinessError`.

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_readiness_service.py
import pytest

from app.models.course import Course
from app.models.readiness import ReadinessResponse
from app.services.readiness import ReadinessError, submit_phase, build_summary
from sqlalchemy import select


async def _course(db_session, instructor):
    c = Course(name="LANG1511", language="zh", instructor_id=instructor.id, enroll_code="ABCD2345")
    db_session.add(c)
    await db_session.flush()
    return c


@pytest.mark.asyncio
async def test_submit_eligibility_survey_completes(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)
    row = await submit_phase(
        db_session, user=test_student, course=c, phase="eligibility_survey",
        answers={"prior_study": "1-3 years", "goals": ["Everyday conversation"]},
    )
    assert row.status == "completed"
    assert row.phase == "eligibility_survey"


@pytest.mark.asyncio
async def test_submit_unknown_phase_rejected(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)
    with pytest.raises(ReadinessError) as exc:
        await submit_phase(db_session, user=test_student, course=c, phase="bogus", answers={})
    assert exc.value.code == "UNKNOWN_PHASE"


@pytest.mark.asyncio
async def test_resubmit_upserts_not_duplicates(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)
    await submit_phase(db_session, user=test_student, course=c, phase="ready_check", answers={"conf_listening": 1})
    await submit_phase(db_session, user=test_student, course=c, phase="ready_check", answers={"conf_listening": 2})
    rows = (await db_session.execute(
        select(ReadinessResponse).where(
            ReadinessResponse.user_id == test_student.id,
            ReadinessResponse.course_id == c.id,
            ReadinessResponse.phase == "ready_check",
        )
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].answers["conf_listening"] == 2


@pytest.mark.asyncio
async def test_recommendation_carries_claim_limit_copy(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)
    await submit_phase(db_session, user=test_student, course=c, phase="eligibility_survey",
                       answers={"prior_study": "Never", "goals": []})
    await submit_phase(db_session, user=test_student, course=c, phase="ready_check",
                       answers={"conf_listening": -2, "conf_speaking": -1})
    rec = await submit_phase(db_session, user=test_student, course=c, phase="recommendation", answers={})
    assert "not a placement decision" in rec.result["claim_limit"].lower()
    assert rec.result["level_hint"]  # some coarse bucket string


@pytest.mark.asyncio
async def test_build_summary_lists_completed_phases(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)
    await submit_phase(db_session, user=test_student, course=c, phase="eligibility_survey", answers={})
    summary = await build_summary(db_session, user=test_student, course=c)
    assert "eligibility_survey" in summary["completed_phases"]
    assert summary["recommendation"] is None  # not yet computed
```

- [ ] **Step 2: FAIL run** — `.\.venv\Scripts\python.exe -m pytest tests/test_readiness_service.py -v`.

- [ ] **Step 3: Implement `services/readiness.py`**

```python
"""Readiness funnel service (spec §4.7): config-driven survey/recommendation.

Phase question sets come from ``pilot.readiness`` (Decision 4), never the DB.
``recommendation`` is computed server-side (no question set) and carries the
pilot's claim-limit copy so the UI never fabricates a placement decision.
Rows are upserted on ``(user, course, phase)`` — a resubmit overwrites answers.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import Course
from app.models.readiness import ReadinessResponse
from app.models.user import User
from app.pilot import get_pilot_profile

# Phases the API accepts. Question-backed phases come from config; the extra
# two are computed/optional (Decision 4) but still valid ``phase`` values.
_COMPUTED_PHASES = {"recommendation"}
_OPTIONAL_PHASES = {"diagnostic"}


class ReadinessError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _known_phases() -> set[str]:
    cfg = {p.phase for p in get_pilot_profile().readiness}
    return cfg | _COMPUTED_PHASES | _OPTIONAL_PHASES


def _recommendation_result(db_answers: dict[str, dict]) -> dict[str, Any]:
    """Coarse, non-authoritative level hint from ready-check confidence.

    Deliberately simple: average the ready_check scale answers into a 3-bucket
    hint. This is guidance copy, NOT a placement — hence the claim-limit.
    """
    profile = get_pilot_profile()
    ready = db_answers.get("ready_check", {}) or {}
    scores = [v for v in ready.values() if isinstance(v, (int, float))]
    avg = sum(scores) / len(scores) if scores else 0.0
    if avg < -0.5:
        level_hint = "foundation"
    elif avg < 1.0:
        level_hint = "intermediate"
    else:
        level_hint = "advanced"
    return {
        "level_hint": level_hint,
        "confidence_average": avg,
        "claim_limit": profile.claim_limits.get("recommendation", ""),
    }


async def _existing_answers(db: AsyncSession, user: User, course: Course) -> dict[str, dict]:
    rows = (await db.execute(
        select(ReadinessResponse).where(
            ReadinessResponse.user_id == user.id,
            ReadinessResponse.course_id == course.id,
        )
    )).scalars().all()
    return {r.phase: (r.answers or {}) for r in rows}


async def submit_phase(
    db: AsyncSession, *, user: User, course: Course, phase: str, answers: dict[str, Any]
) -> ReadinessResponse:
    if phase not in _known_phases():
        raise ReadinessError("UNKNOWN_PHASE", f"Unknown readiness phase '{phase}'")

    if phase in _COMPUTED_PHASES:
        prior = await _existing_answers(db, user, course)
        result = _recommendation_result(prior)
        answers = {}  # recommendation has no submitted answers
    else:
        result = {}

    # Upsert on the unique (user, course, phase). ON CONFLICT overwrites answers
    # + result + status (a resubmit is authoritative).
    stmt = (
        pg_insert(ReadinessResponse)
        .values(
            user_id=user.id, course_id=course.id, phase=phase,
            answers=answers, result=result, status="completed",
        )
        .on_conflict_do_update(
            index_elements=["user_id", "course_id", "phase"],
            set_={"answers": answers, "result": result, "status": "completed"},
        )
        .returning(ReadinessResponse.id)
    )
    row_id = (await db.execute(stmt)).scalar_one()
    await db.commit()
    return await db.get(ReadinessResponse, row_id)


async def build_summary(
    db: AsyncSession, *, user: User, course: Course
) -> dict[str, Any]:
    rows = (await db.execute(
        select(ReadinessResponse).where(
            ReadinessResponse.user_id == user.id,
            ReadinessResponse.course_id == course.id,
        )
    )).scalars().all()
    by_phase = {r.phase: r for r in rows}
    rec = by_phase.get("recommendation")
    return {
        "completed_phases": [p for p, r in by_phase.items() if r.status == "completed"],
        "recommendation": rec.result if rec else None,
        "answers": {p: r.answers for p, r in by_phase.items()},
    }
```

> **Reconcile at build time:** confirm `pg_insert(...).on_conflict_do_update(...).returning(...)` re-fetch works under the async session (mirror `services/mastery.py::_get_or_create_mastery`, the documented race-safe upsert). If `db.get` after commit returns a detached instance, `await db.refresh` it inside the same session or re-select. Validate `answers` shape against config questions only loosely (presence of known question ids) — do not hard-reject unknown keys (forward-compat).

- [ ] **Step 4: PASS run** — `.\.venv\Scripts\python.exe -m pytest tests/test_readiness_service.py -v`.

- [ ] **Step 5: Commit** — `git commit -am "feat(readiness): readiness service (config-driven phases + recommendation claim-limit)"`

---

### Task 4: `readiness.py` router — submit phase, summary, preview (gate + code tests)

**Files:**
- Create: `backend/app/api/readiness.py`, `backend/app/schemas/readiness.py`
- Modify: `backend/app/api/__init__.py` (register)
- Test: `backend/tests/test_readiness_api.py`

Endpoints (spec §5 `readiness.py`): `POST /courses/{id}/readiness/{phase}`, `GET /courses/{id}/readiness/summary`, `GET /courses/{id}/preview` (short/deep, gated on a valid code passed as a query param). Student-scoped (any authenticated student may submit readiness for a course they can see by code — enrollment is NOT required yet, that's the point of the funnel). Ownership/visibility: the student must supply a valid `code` (matching `course.enroll_code`) OR already have an enrollment row; otherwise 404 (don't leak course existence).

- [ ] **Step 1: Failing test** (override `get_current_user` → a student inline; create a published + a draft course locally)

```python
# backend/tests/test_readiness_api.py
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models.course import Course


async def _course(db_session, instructor, *, open_=True, code="ABCD2345", active=True, mode="code"):
    c = Course(
        name="LANG1511", language="zh", instructor_id=instructor.id, enroll_code=code,
        context_status="approved" if open_ else "draft",
        enroll_code_active=active, join_mode=mode,
    )
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


def _student_client(db_session, student):
    async def _db():
        yield db_session
    async def _user():
        return student
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                       headers={"Authorization": "Bearer t"})


@pytest.mark.asyncio
async def test_submit_phase_persists(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)
    async with _student_client(db_session, test_student) as ac:
        r = await ac.post(f"/api/courses/{c.id}/readiness/eligibility_survey",
                          json={"answers": {"prior_study": "Never"}})
    app.dependency_overrides.clear()
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "completed"


@pytest.mark.asyncio
async def test_unknown_phase_422(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)
    async with _student_client(db_session, test_student) as ac:
        r = await ac.post(f"/api/courses/{c.id}/readiness/bogus", json={"answers": {}})
    app.dependency_overrides.clear()
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "UNKNOWN_PHASE"


@pytest.mark.asyncio
async def test_short_preview_requires_valid_code(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor, code="ABCD2345")
    async with _student_client(db_session, test_student) as ac:
        ok = await ac.get(f"/api/courses/{c.id}/preview?code=ABCD2345&depth=short")
        bad = await ac.get(f"/api/courses/{c.id}/preview?code=WRONG999&depth=short")
    app.dependency_overrides.clear()
    assert ok.status_code == 200
    assert bad.status_code == 404


@pytest.mark.asyncio
async def test_summary_lists_completed(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)
    async with _student_client(db_session, test_student) as ac:
        await ac.post(f"/api/courses/{c.id}/readiness/eligibility_survey", json={"answers": {}})
        r = await ac.get(f"/api/courses/{c.id}/readiness/summary")
    app.dependency_overrides.clear()
    assert r.status_code == 200
    assert "eligibility_survey" in r.json()["data"]["completed_phases"]
```

- [ ] **Step 2: FAIL run** — `.\.venv\Scripts\python.exe -m pytest tests/test_readiness_api.py -v` → 404s.

- [ ] **Step 3: Implement `schemas/readiness.py`**

```python
from typing import Any

from pydantic import BaseModel


class ReadinessSubmit(BaseModel):
    answers: dict[str, Any] = {}


class ReadinessResponseOut(BaseModel):
    phase: str
    status: str
    answers: dict[str, Any]
    result: dict[str, Any]

    model_config = {"from_attributes": True}


class ReadinessSummaryOut(BaseModel):
    completed_phases: list[str]
    recommendation: dict[str, Any] | None
    answers: dict[str, Any]


class CoursePreviewOut(BaseModel):
    id: str
    name: str
    code: str | None
    language: str
    description: str | None
    is_open: bool
    join_mode: str
    depth: str
    # deep preview adds a schedule/ILO teaser (populated only when depth='deep')
    detail: dict[str, Any] | None = None
```

- [ ] **Step 4: Implement `api/readiness.py`** — resolve+guard course by id, gate the preview on a valid `code`. Map `ReadinessError.code` to 422 structured detail.

```python
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.course import Course, Enrollment
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.readiness import (
    CoursePreviewOut, ReadinessResponseOut, ReadinessSubmit, ReadinessSummaryOut,
)
from app.services.readiness import ReadinessError, build_summary, submit_phase

router = APIRouter(prefix="/courses/{course_id}", tags=["readiness"])


async def _visible_course(course_id: uuid.UUID, code: str | None, user: User, db: AsyncSession) -> Course:
    """A course the student may see via a valid code OR an existing enrollment.

    404 (never 403) so we don't leak course existence to a bad code.
    """
    course = (await db.execute(
        select(Course).where(Course.id == course_id, Course.deleted_at.is_(None))
    )).scalar_one_or_none()
    if course is None:
        raise HTTPException(404, "Course not found")
    if code and _norm(code) == course.enroll_code:
        return course
    enrolled = (await db.execute(
        select(Enrollment).where(Enrollment.course_id == course_id, Enrollment.user_id == user.id)
    )).scalar_one_or_none()
    if enrolled:
        return course
    raise HTTPException(404, "Course not found")


def _norm(raw: str) -> str:
    return "".join(ch for ch in raw.upper() if ch.isalnum())


@router.post("/readiness/{phase}", response_model=APIResponse[ReadinessResponseOut])
async def submit_readiness(
    course_id: uuid.UUID, phase: str, body: ReadinessSubmit,
    code: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    course = await _visible_course(course_id, code, user, db)
    try:
        row = await submit_phase(db, user=user, course=course, phase=phase, answers=body.answers)
    except ReadinessError as exc:
        raise HTTPException(422, detail={"code": exc.code, "message": exc.message})
    return APIResponse(success=True, data=ReadinessResponseOut.model_validate(row))


@router.get("/readiness/summary", response_model=APIResponse[ReadinessSummaryOut])
async def readiness_summary(
    course_id: uuid.UUID, code: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    course = await _visible_course(course_id, code, user, db)
    summary = await build_summary(db, user=user, course=course)
    return APIResponse(success=True, data=ReadinessSummaryOut(**summary))


@router.get("/preview", response_model=APIResponse[CoursePreviewOut])
async def course_preview(
    course_id: uuid.UUID,
    code: str | None = Query(default=None),
    depth: Literal["short", "deep"] = Query(default="short"),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    course = await _visible_course(course_id, code, user, db)
    detail = None
    if depth == "deep":
        # Deep preview teaser: meeting count + ILO count (read-only, non-PII).
        detail = await _deep_preview_detail(db, course)
    return APIResponse(success=True, data=CoursePreviewOut(
        id=str(course.id), name=course.name, code=course.code, language=course.language,
        description=course.description, is_open=course.context_status == "approved",
        join_mode=course.join_mode, depth=depth, detail=detail,
    ))
```

Implement `_deep_preview_detail` (count `CourseMeeting` + `LearningObjective` rows for the course; return `{"sessions": n, "objectives": m}`). Register in `backend/app/api/__init__.py`: `from app.api.readiness import router as readiness_router` + `api_router.include_router(readiness_router)`.

> **Note the router prefix collision:** `readiness_router` uses prefix `/courses/{course_id}` which overlaps `courses.py`'s `/courses`. FastAPI resolves by full path, so `/courses/{id}/preview` and `/courses/{id}/readiness/...` won't clash with existing `courses.py` routes — but verify route ordering after registration (run the API test) and, if any 405/404 surprises appear, give `readiness_router` a distinct sub-path segment.

- [ ] **Step 5: PASS run** — `.\.venv\Scripts\python.exe -m pytest tests/test_readiness_api.py -v`.

- [ ] **Step 6: Commit** — `git commit -am "feat(readiness): readiness.py router (submit phase, summary, code-gated preview)"`

---

### Task 5: `enroll-by-code` — join_mode + setup gate + status (Decision 1, Decision 3)

**Files:**
- Modify: `backend/app/api/courses.py` (`enroll_by_code`), `backend/app/schemas/course.py` (result schema)
- Test: `backend/tests/test_enroll_by_code_gate.py`

`enroll-by-code` becomes the terminal join action. Order of checks: normalize+validate format → resolve course → **code active?** (`JOIN_CODE_INACTIVE`) → **course open?** (`assert_course_open` → `SETUP_NOT_OPEN`) → already enrolled? (idempotent) → create enrollment with status from `join_mode`. Return a result that tells the funnel whether it landed `active` (S013) or `pending` (pending-approval screen).

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_enroll_by_code_gate.py
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models.course import Course, Enrollment
from sqlalchemy import select


async def _course(db_session, instructor, **kw):
    defaults = dict(name="LANG1511", language="zh", instructor_id=instructor.id,
                    enroll_code="ABCD2345", context_status="approved",
                    enroll_code_active=True, join_mode="code")
    defaults.update(kw)
    c = Course(**defaults)
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


def _client(db_session, student):
    async def _db():
        yield db_session
    async def _user():
        return student
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                       headers={"Authorization": "Bearer t"})


@pytest.mark.asyncio
async def test_code_mode_enrolls_active(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor, join_mode="code")
    async with _client(db_session, test_student) as ac:
        r = await ac.post("/api/courses/enroll-by-code", json={"enroll_code": "ABCD2345"})
    app.dependency_overrides.clear()
    assert r.status_code in (200, 201)
    assert r.json()["data"]["enrollment_status"] == "active"


@pytest.mark.asyncio
async def test_approval_mode_enrolls_pending(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor, join_mode="code_plus_approval")
    async with _client(db_session, test_student) as ac:
        r = await ac.post("/api/courses/enroll-by-code", json={"enroll_code": "ABCD2345"})
    app.dependency_overrides.clear()
    assert r.json()["data"]["enrollment_status"] == "pending"
    row = (await db_session.execute(select(Enrollment).where(Enrollment.course_id == c.id))).scalar_one()
    assert row.status == "pending"


@pytest.mark.asyncio
async def test_not_open_blocks_join(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor, context_status="draft")
    async with _client(db_session, test_student) as ac:
        r = await ac.post("/api/courses/enroll-by-code", json={"enroll_code": "ABCD2345"})
    app.dependency_overrides.clear()
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "SETUP_NOT_OPEN"


@pytest.mark.asyncio
async def test_inactive_code_blocks_join(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor, enroll_code_active=False)
    async with _client(db_session, test_student) as ac:
        r = await ac.post("/api/courses/enroll-by-code", json={"enroll_code": "ABCD2345"})
    app.dependency_overrides.clear()
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "JOIN_CODE_INACTIVE"
```

- [ ] **Step 2: FAIL run** — `.\.venv\Scripts\python.exe -m pytest tests/test_enroll_by_code_gate.py -v`.

- [ ] **Step 3: Implement** — add `EnrollByCodeResult` to `schemas/course.py` (`course: CourseResponse`, `enrollment_status: str`), then rewrite `enroll_by_code` in `api/courses.py`:

```python
from app.services.setup import SetupGateError, assert_course_open
# ... inside enroll_by_code, after resolving `course` (404 if none):

    if not course.enroll_code_active:
        raise HTTPException(status_code=409, detail={
            "code": "JOIN_CODE_INACTIVE",
            "message": "This join code is no longer active.",
        })
    try:
        assert_course_open(course)
    except SetupGateError as exc:  # SETUP_NOT_OPEN
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": exc.message})

    existing = (await db.execute(select(Enrollment).where(
        Enrollment.course_id == course.id, Enrollment.user_id == user.id,
    ))).scalar_one_or_none()
    if existing:
        return APIResponse(success=True, data=EnrollByCodeResult(
            course=CourseResponse.model_validate(course),
            enrollment_status=existing.status,
        ))

    new_status = "pending" if course.join_mode == "code_plus_approval" else "active"
    db.add(Enrollment(course_id=course.id, user_id=user.id, role=user.role, status=new_status))
    await db.commit()
    return APIResponse(success=True, data=EnrollByCodeResult(
        course=CourseResponse.model_validate(course), enrollment_status=new_status,
    ))
```

Update the `response_model` on the route to `APIResponse[EnrollByCodeResult]`. **Tighten workspace visibility:** in `api/courses.py::get_course` and `list_courses`, the enrollment filter must require `Enrollment.status == "active"` so a `pending` student cannot read the course row (add a test asserting a pending student gets 404 on `GET /courses/{id}` — put it in this module). Instructor access is via `Course.instructor_id`, unaffected.

- [ ] **Step 4: PASS run** — `.\.venv\Scripts\python.exe -m pytest tests/test_enroll_by_code_gate.py tests/test_courses.py -v`.

- [ ] **Step 5: Commit** — `git commit -am "feat(enrollment): enroll-by-code respects join_mode + setup gate + active-only visibility"`

---

### Task 6: join-requests (list / approve / deny) + roster endpoints

**Files:**
- Modify: `backend/app/api/courses.py`
- Modify: `backend/app/schemas/course.py` (roster + join-request rows)
- Test: `backend/tests/test_join_requests_api.py`

Teacher endpoints (owner-guarded via `get_owned_course`): `GET /courses/{id}/join-requests` (pending enrollments + user info), `POST /courses/{id}/join-requests/{enrollment_id}/approve` (pending→active), `POST /.../deny` (pending→rejected), `GET /courses/{id}/roster` (active enrollments + user info). Approve/deny only act on `pending` rows (409 otherwise).

- [ ] **Step 1: Failing test** — assert: owner lists exactly the pending rows; approve flips to `active` and the student then reads `GET /courses/{id}` (200); deny flips to `rejected`; approving an already-active row → 409; a non-owner instructor → 404. Build a pending enrollment locally (`Enrollment(..., status="pending")`) and an owner client (override `get_current_user` → `test_instructor` who owns the course) + a student client.

- [ ] **Step 2: FAIL run** — `.\.venv\Scripts\python.exe -m pytest tests/test_join_requests_api.py -v`.

- [ ] **Step 3: Implement** — schemas `JoinRequestOut` (`enrollment_id`, `user_id`, `full_name`, `email`, `requested_at=enrolled_at`, `status`) and `RosterEntryOut` (same shape, active rows). Endpoints in `courses.py`:

```python
@router.get("/{course_id}/join-requests", response_model=APIResponse[list[JoinRequestOut]])
async def list_join_requests(db=Depends(get_db), course=Depends(get_owned_course)):
    rows = (await db.execute(
        select(Enrollment, User).join(User, User.id == Enrollment.user_id).where(
            Enrollment.course_id == course.id, Enrollment.status == "pending",
        ).order_by(Enrollment.enrolled_at.asc())
    )).all()
    return APIResponse(success=True, data=[_join_request_out(e, u) for e, u in rows])


@router.post("/{course_id}/join-requests/{enrollment_id}/approve",
             response_model=APIResponse[JoinRequestOut])
async def approve_join_request(enrollment_id: uuid.UUID, db=Depends(get_db),
                               course=Depends(get_owned_course)):
    return await _decide_join_request(db, course, enrollment_id, "active")


@router.post("/{course_id}/join-requests/{enrollment_id}/deny",
             response_model=APIResponse[JoinRequestOut])
async def deny_join_request(enrollment_id: uuid.UUID, db=Depends(get_db),
                            course=Depends(get_owned_course)):
    return await _decide_join_request(db, course, enrollment_id, "rejected")
```

`_decide_join_request`: load the enrollment scoped to `course.id`; 404 if missing; 409 `{"code": "NOT_PENDING"}` if `status != 'pending'`; else set status + commit. `GET /roster` mirrors `list_join_requests` with `status == "active"`. Reuse `get_owned_course` (already imported).

- [ ] **Step 4: PASS run** — `.\.venv\Scripts\python.exe -m pytest tests/test_join_requests_api.py -v`.

- [ ] **Step 5: Commit** — `git commit -am "feat(enrollment): join-request list/approve/deny + roster endpoints"`

---

### Task 7: backend regression + code review

**Files:** none (verification task)

- [ ] **Step 1: Full backend suite** — `.\.venv\Scripts\python.exe -m pytest -q`. Confirm only the KNOWN pre-existing failures from the P1 handoff remain (`test_alerts_evaluator` ~5, `test_scheduler_integration` ~3 errors, `test_canvas_coverage` ~2, `test_live_quiz_service` ~1); **zero new** failures from P2. If any new failure traces to the `Enrollment.status`/`active`-only visibility tightening (Task 5) in an existing test, fix the caller (it likely creates an enrollment without status and then expects visibility — add `status="active"`).

- [ ] **Step 2: Review** — run `/code-review` (or code-reviewer agent) over the Task 1–6 diff. Fix CRITICAL/HIGH. Focus: gate ordering in `enroll-by-code`, the `active`-only visibility change not breaking instructor paths, RLS migration correctness, no secrets, readiness input validation at the boundary.

- [ ] **Step 3: Commit** — `git commit -am "chore(p2): backend regression pass + review fixes"` (only if fixes were made).

---

### Task 8: RLS isolation test for `readiness_responses` (Decision 2)

**Files:**
- Test: `backend/tests/test_readiness_rls.py`

Verifies owner isolation is actually enforced by the policy (not just declared). Runs against `async_engine` (the migrated dev DB, where the policy exists) under `SET ROLE meli_app` (non-superuser, no `BYPASSRLS`), mirroring `tests/test_rls_isolation.py`. Skip-guard if the `meli_app` role is unavailable offline (matches P0/P1 infra-limited-test convention).

- [ ] **Step 1: Write the test**

```python
# backend/tests/test_readiness_rls.py
import uuid
import pytest
from sqlalchemy import text


async def _role_missing(conn) -> bool:
    exists = (await conn.execute(
        text("SELECT 1 FROM pg_roles WHERE rolname = 'meli_app'")
    )).scalar()
    return exists is None


@pytest.mark.asyncio
async def test_readiness_rls_owner_isolation(async_engine):
    """A row inserted as user A must be invisible when the GUC names user B.

    Runs under meli_app (BYPASSRLS off). Requires the readiness_responses RLS
    migration to be applied to the dev DB async_engine points at.
    """
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    async with async_engine.connect() as conn:
        if await _role_missing(conn):
            pytest.skip("meli_app role not present in this environment")
        # Pre-req rows (users + course) must exist for the FKs; create minimal
        # fixtures here as the superuser BEFORE dropping to meli_app, then clean
        # up in a finally. (Insert a user A, user B, instructor + course; ids
        # captured. Omitted here for brevity — see helper below.)
        ...
        await conn.execute(text("SET ROLE meli_app"))
        try:
            # Act as user A: insert a readiness row.
            await conn.execute(text("SELECT set_config('app.current_user_id', :u, false)").bindparams(u=user_a))
            await conn.execute(text(
                "INSERT INTO readiness_responses (id, user_id, course_id, phase, answers, result, status) "
                "VALUES (:id, :u, :c, 'ready_check', '{}'::jsonb, '{}'::jsonb, 'completed')"
            ).bindparams(id=str(uuid.uuid4()), u=user_a, c=course_id))
            visible_to_a = (await conn.execute(text("SELECT count(*) FROM readiness_responses"))).scalar()
            assert visible_to_a == 1
            # Switch to user B: the row must vanish under the owner-isolation policy.
            await conn.execute(text("SELECT set_config('app.current_user_id', :u, false)").bindparams(u=user_b))
            visible_to_b = (await conn.execute(text("SELECT count(*) FROM readiness_responses"))).scalar()
            assert visible_to_b == 0
        finally:
            await conn.execute(text("RESET ROLE"))
            # cleanup inserted rows as superuser
            ...
```

> **Reconcile at build time:** flesh out the pre-req fixture inserts (users A/B, an instructor user, a course whose `enroll_code` is unique) using raw SQL as the superuser before `SET ROLE meli_app`, capturing `course_id`. Wrap the whole body so cleanup (`DELETE FROM readiness_responses/courses/users`) runs in `finally` even on assertion failure, since `async_engine` is the shared dev DB (not the disposable test DB). If seeding on the shared dev DB is undesirable, an acceptable alternative is to assert the policy EXISTS + is enforced via `SELECT relrowsecurity FROM pg_class WHERE relname='readiness_responses'` and `SELECT polname FROM pg_policies WHERE tablename='readiness_responses'` — document which path you took. Prefer the real enforcement test when `meli_app` is available.

- [ ] **Step 2: Run** — `.\.venv\Scripts\python.exe -m pytest tests/test_readiness_rls.py -v` (passes or skips cleanly).

- [ ] **Step 3: Commit** — `git commit -am "test(readiness): RLS owner-isolation test for readiness_responses"`

---

### Task 9: student `use-readiness` + `use-enrollment` hooks + join funnel scaffold (S003/S004)

**Files:**
- Create: `frontend/src/hooks/use-readiness.ts`, `frontend/src/hooks/use-enrollment.ts`
- Create: `frontend/src/app/(app)/student/join/page.tsx`, `frontend/src/app/(app)/student/join/join-funnel.tsx` (client orchestrator)
- Create: `frontend/src/components/join/step-code-entry.tsx` (S003), `frontend/src/components/join/state-invalid-code.tsx` (S004)
- Modify: `frontend/messages/en.json` (add `student.join.*` keys)
- Figma: `get_design_context` for S003 (`1372:204`), S004 (`1372:206`).

Design rules (Global Rules): tokens only (`var(--color-*)`, `--space-*`); reuse `StepWizard` + `StateBanner` + `EmptyState` patterns; one visual treatment per state. Invoke `frontend-design:frontend-design` + `ui-ux-pro-max:ui-ux-pro-max` before styling.

- [ ] **Step 1** — `use-readiness.ts` (follow `use-authed-query.ts` + `use-courses.ts` exactly):
  - `useCoursePreview(courseId, code, depth)` → `useAuthedQuery<CoursePreview>({ queryKey: ["preview", courseId, depth], path: \`/courses/${courseId}/preview?code=${code}&depth=${depth}\`, enabled: !!courseId && !!code })`.
  - `useReadinessSummary(courseId, code)` → GET `/courses/${courseId}/readiness/summary?code=`.
  - `useSubmitPhase(courseId, code)` → mutation POST `/courses/${courseId}/readiness/{phase}?code=`, body `{answers}`; invalidates `["readiness-summary", courseId]`.
  Map a `422 {code:"UNKNOWN_PHASE"}` to a typed error.

- [ ] **Step 2** — `use-enrollment.ts`:
  - `useEnrollByCode()` — replace/extend the existing `useEnrollByCode` in `use-courses.ts` to return `{ course, enrollment_status }` (the new `EnrollByCodeResult`). Map gate errors: `409 {code:"SETUP_NOT_OPEN"}` → `"not_open"`, `409 {code:"JOIN_CODE_INACTIVE"}` → `"inactive"`, `404` → `"not_found"`. **Do not break** the existing `JoinCourseDialog` consumer — keep the mutation shape backward-compatible or update that dialog in the same commit (it currently routes to `/dashboard/courses/...`; leave it working).
  - `useLookupCode(code)` — a light resolver the funnel uses to turn a typed code into a `courseId` + `{ is_open, join_mode, code_active }` for the S003→S004/S005 branch. Implement as `GET /courses/enroll-by-code` preflight? No — reuse `useCoursePreview` after a resolve. Since preview needs a `courseId`, add a tiny backend resolver `GET /api/courses/lookup?code=XXXX` (owner-agnostic, returns `{course_id, is_open, join_mode, code_active}` or 404) — **add this to Task 5's `courses.py`** if not already present, with a test. (If you prefer to avoid a new endpoint, have S003 call `enroll-by-code` only at the very end and drive previews via a `courseId` captured from `lookup`. The `lookup` endpoint is the cleaner UX — it lets S004 distinguish invalid vs inactive before the student invests in the survey.)

  > **Cross-task note:** if you add `GET /courses/lookup`, fold its failing test + impl into Task 5 (it belongs with the join/gate logic) and reference it here. Keep it code-gated and non-leaky (404 for unknown code; 200 with `code_active:false` for a known-but-inactive code so S004 can show the right copy).

- [ ] **Step 3** — `join-funnel.tsx`: `"use client"`; a `StepWizard`-driven flow with local state for `courseId`, `code`, and the current step. Steps derive from a funnel step list (`code → preview → survey → ready_check → diagnostic? → recommendation → deep_preview → summary → terminal`). Uses `usePilotConfig()` for readiness definitions (Task 10). The scaffold in THIS task wires only S003 (code entry) → on valid code, advance to preview (placeholder) → on invalid/inactive, render S004.

- [ ] **Step 4** — `step-code-entry.tsx` (S003): 8-char code input (reuse the `normalize` + masked/mono styling from `join-course-dialog.tsx`); submit → `useLookupCode`; on 404 → `state-invalid-code` with `reason="not_found"`; on `code_active:false` → `state-invalid-code` with `reason="inactive"`; on ok → advance. `state-invalid-code.tsx` (S004): `StateBanner tone="blocked"` with reason-specific copy + a "try another code" action.

- [ ] **Step 5: Verify** — from `frontend/`: `npx tsc --noEmit && npm run lint` clean; add a vitest for the funnel step-derivation logic (pure function) if extracted. `npm run dev`, type a bad code → S004; a good code → advances.

- [ ] **Step 6: Commit** — `git commit -am "feat(join): readiness/enrollment hooks + join funnel scaffold (code entry + invalid-code)"`

---

### Task 10: short preview + eligibility survey + ready check (S005/S006/S007) — config-driven

**Files:**
- Create: `frontend/src/components/join/step-short-preview.tsx` (S005), `frontend/src/components/join/step-readiness-phase.tsx` (reusable survey renderer for S006/S007), `frontend/src/components/join/readiness-question.tsx`
- Modify: `frontend/src/app/(app)/student/join/join-funnel.tsx`, `frontend/messages/en.json`
- Figma: S005 (`1372:208`), S006 (`1372:210`), S007 (`1372:212`).

The survey renderer is **config-driven**: it reads `usePilotConfig().config.readiness` (the `ReadinessPhaseDef[]`) and renders each `ReadinessQuestion` by `kind` (`single_choice`, `multi_choice`, `scale`, `short_text`). `scale` uses the pilot `confidence_scale` (−2..+2, labels). One renderer serves both eligibility-survey and ready-check — the phase selects which config block.

- [ ] **Step 1** — `readiness-question.tsx`: a controlled input per `kind`. `scale` renders the `confidence_scale.labels` as a radio/segmented control (this is a precursor to P3's `ConfidenceScaleInput`; keep it local to join for now — do NOT prematurely extract the shared pattern). Tokens only.

- [ ] **Step 2** — `step-readiness-phase.tsx`: props `{ phase, courseId, code, onDone }`. Finds the matching `ReadinessPhaseDef` in config; renders `title`, `intro`, each question; collects `answers`; "Continue" calls `useSubmitPhase(courseId, code)` with `{answers}` for that phase, then `onDone()`. Waiting/blocked → `StateBanner`. If config has no def for the phase (e.g. `diagnostic` absent in CLE), render nothing / auto-skip (Task 11 handles the optional branch).

- [ ] **Step 3** — `step-short-preview.tsx` (S005): renders `useCoursePreview(courseId, code, "short")` — name, language, short description, `is_open` note. "Start readiness" advances to eligibility-survey. If `is_open === false`, offer the S012 branch (course-not-open) early (server re-checks at join anyway).

- [ ] **Step 4** — wire S005→S006→S007 into `join-funnel.tsx` step order.

- [ ] **Step 5: Verify** — `npx tsc --noEmit && npm run lint`; add a vitest asserting `readiness-question` renders a `scale` question with the 5 confidence labels from a mocked pilot config. Manual: walk code→preview→survey→ready-check, answers POST (network tab).

- [ ] **Step 6: Commit** — `git commit -am "feat(join): short preview + config-driven eligibility survey + ready check (S005-S007)"`

---

### Task 11: optional diagnostic + recommendation + deep preview + readiness summary (S008–S011)

**Files:**
- Create: `frontend/src/components/join/step-diagnostic.tsx` (S008), `frontend/src/components/join/step-recommendation.tsx` (S009), `frontend/src/components/join/step-deep-preview.tsx` (S010), `frontend/src/components/join/step-readiness-summary.tsx` (S011)
- Modify: `frontend/src/app/(app)/student/join/join-funnel.tsx`, `frontend/messages/en.json`
- Figma: S008 (`1372:214`), S009 (`1372:216`), S010 (`1372:218`), S011 (`1372:220`).

- [ ] **Step 1** — `step-diagnostic.tsx` (S008): **optional/skippable**. If pilot config has a `diagnostic` `ReadinessPhaseDef`, render it via the Task 10 `step-readiness-phase` renderer; otherwise show a "Skip — no diagnostic for this course" `EmptyState` with a Continue that advances. Never blocks.

- [ ] **Step 2** — `step-recommendation.tsx` (S009): on entry, POST the `recommendation` phase via `useSubmitPhase(courseId, code)` (empty answers — server computes) and render `result`: the `level_hint` bucket + `confidence_average`, and prominently the `result.claim_limit` copy verbatim (from pilot config) in a `StateBanner tone="info"`. This is the claim-limit surface — it must be visible, not buried.

- [ ] **Step 3** — `step-deep-preview.tsx` (S010): `useCoursePreview(courseId, code, "deep")` — the fuller teaser (`detail.sessions`, `detail.objectives`). "Continue" → summary.

- [ ] **Step 4** — `step-readiness-summary.tsx` (S011): `useReadinessSummary(courseId, code)` — lists `completed_phases`, echoes the recommendation, and shows the primary CTA "Join course" which triggers the terminal enroll (Task 12). Claim-limit copy repeated near the CTA.

- [ ] **Step 5** — wire S008–S011 into the funnel; the diagnostic step is conditionally inserted only when its config exists (else auto-advance).

- [ ] **Step 6: Verify** — `npx tsc --noEmit && npm run lint`; vitest: recommendation step renders the claim-limit copy from a mocked config + result. Manual walk.

- [ ] **Step 7: Commit** — `git commit -am "feat(join): diagnostic + recommendation (claim-limit) + deep preview + readiness summary (S008-S011)"`

---

### Task 12: terminal join states — course-not-open + pending approval + join success (S012/S013)

**Files:**
- Create: `frontend/src/components/join/state-course-not-open.tsx` (S012), `frontend/src/components/join/state-pending-approval.tsx`, `frontend/src/components/join/state-join-success.tsx` (S013)
- Modify: `frontend/src/app/(app)/student/join/join-funnel.tsx`, `frontend/messages/en.json`
- Figma: S012 (`1372:222`), S013 (`1372:224`).

The summary CTA calls `useEnrollByCode()`; the returned `enrollment_status` (or a mapped gate error) selects the terminal screen:
- error `"not_open"` (SETUP_NOT_OPEN) → S012 course-not-open (`StateBanner tone="warning"` + "we'll email you when it opens" copy + back to dashboard).
- error `"inactive"` (JOIN_CODE_INACTIVE) → reuse S004 invalid-code copy.
- `enrollment_status === "pending"` → pending-approval screen (`StateBanner tone="info"`: "Your request is awaiting your instructor's approval").
- `enrollment_status === "active"` → S013 join-success (`StateBanner tone="success"` + CTA into the course workspace `/student/courses` or the course page).

- [ ] **Step 1** — implement the three state components (tokens + patterns only; each has a reason + a next action, never a blank div).

- [ ] **Step 2** — in `join-funnel.tsx`, on the summary "Join course" action: await `enroll.mutateAsync`, then `switch` on status/error → set the terminal step. Idempotent re-join (already `active`/`pending`) routes to the matching terminal screen.

- [ ] **Step 3** — thread `/student/join?code=XXXX` deep-link support: if the page loads with a `?code=` query, prefill S003 (so an emailed invite link lands mid-funnel). Read Next.js 16 `searchParams` handling from `node_modules/next/dist/docs/` (async — differs from training data).

- [ ] **Step 4: Verify** — `npx tsc --noEmit && npm run lint`; vitest: funnel terminal-branch selection given mocked `enrollByCode` results (`active`→success, `pending`→pending, `not_open`→S012). Manual: join a `code` course (success), a `code_plus_approval` course (pending), a draft course (S012).

- [ ] **Step 5: Commit** — `git commit -am "feat(join): terminal states — course-not-open + pending approval + join success (S012-S013)"`

---

### Task 13: teacher course overview (T029) + schedule table (T030)

**Files:**
- Create: `frontend/src/app/(app)/teacher/courses/[id]/overview/page.tsx` (T029), `frontend/src/app/(app)/teacher/courses/[id]/schedule/page.tsx` (T030)
- Create: `frontend/src/components/course/course-overview.tsx`, `frontend/src/components/course/course-schedule-table.tsx`
- Modify: `frontend/messages/en.json`
- Figma: T029 (`1372:68`), T030 (`1372:70`).

- [ ] **Step 1** — T029 overview: `PageHeader` + summary cards reading `useCourse(courseId)` (setup_status, context_status, join_mode, enroll_code_active) + counts (roster size via Task 14 roster hook, session count via `use-meetings.ts`). Surfaces the course state (draft/published) with a `StateBanner` and a link into `/teacher/courses/[id]/setup` if not yet published.

- [ ] **Step 2** — T030 schedule table: read meetings via `use-meetings.ts` (`GET /courses/{id}/meetings`); render a table of session_no (`meeting_index`), topic (`topic_summary`/title), venue (`location`), `scheduled_at`, `release_state`. Read-only view here (editing is the P1 setup schedule step). Empty state when no meetings.

- [ ] **Step 3** — server components read async `params` (Next.js 16 — verify in `node_modules/next/dist/docs/`); render the client components.

- [ ] **Step 4: Verify** — `npx tsc --noEmit && npm run lint`; manual: overview + schedule render for a published course.

- [ ] **Step 5: Commit** — `git commit -am "feat(teacher): course overview + schedule table (T029-T030)"`

---

### Task 14: teacher enrollment overview (T031) + roster detail (T032)

**Files:**
- Create: `frontend/src/app/(app)/teacher/courses/[id]/enrollment/page.tsx` (hosts T031/T032/T033/T034 tabs or sections)
- Create: `frontend/src/components/course/enrollment-overview.tsx` (T031), `frontend/src/components/course/roster-detail.tsx` (T032)
- Modify: `frontend/src/hooks/use-enrollment.ts` (add teacher roster/join-request hooks)
- Figma: T031 (`1372:72`), T032 (`1372:74`).

- [ ] **Step 1** — extend `use-enrollment.ts`: `useRoster(courseId)` → GET `/courses/${courseId}/roster`; `useJoinRequests(courseId)` → GET `/courses/${courseId}/join-requests`; `useApproveJoinRequest(courseId)` / `useDenyJoinRequest(courseId)` → POST the approve/deny endpoints, invalidating both `["roster", courseId]` and `["join-requests", courseId]`.

- [ ] **Step 2** — `enrollment-overview.tsx` (T031): counts (active roster size, pending count) + entry points into roster detail + join-request approval. `StateBanner` if there are pending requests ("N students awaiting approval").

- [ ] **Step 3** — `roster-detail.tsx` (T032): table of active students (name, email, joined date) from `useRoster`. Empty state when no students yet.

- [ ] **Step 4: Verify** — `npx tsc --noEmit && npm run lint`; manual: seed an active enrollment, see it in the roster.

- [ ] **Step 5: Commit** — `git commit -am "feat(teacher): enrollment overview + roster detail (T031-T032)"`

---

### Task 15: teacher join-request approval (T033) + course-code modal (T034) + score-categories view (T035)

**Files:**
- Create: `frontend/src/components/course/join-request-approval.tsx` (T033), `frontend/src/components/course/course-code-modal.tsx` (T034), `frontend/src/components/course/score-categories-view.tsx` (T035)
- Modify: `frontend/src/app/(app)/teacher/courses/[id]/enrollment/page.tsx`, `frontend/messages/en.json`
- Figma: T033 (`1372:76`), T034 (`1372:78`), T035 (`1372:80`).

- [ ] **Step 1** — `join-request-approval.tsx` (T033): list pending requests (`useJoinRequests`) with Approve/Deny buttons per row → `useApproveJoinRequest` / `useDenyJoinRequest`. Optimistic-ish: on success the row leaves the pending list and (for approve) appears in the roster. Empty state "No pending requests".

- [ ] **Step 2** — `course-code-modal.tsx` (T034): reveal (masked by default) / rotate / deactivate the enroll code — **reuse the existing `useRotateEnrollCode` / `useDeactivateEnrollCode` hooks** (`use-courses.ts`) + the P1 `enroll-code-card.tsx` treatment. Also surface `join_mode` (code vs code+approval) read-only here (a `join_mode` editor is out of P2 scope — note it as a P-later toggle; the column exists but no PATCH endpoint yet). Show whether the code is active.

  > **Reconcile:** if a `join_mode` toggle is desired in T034, it needs a backend `PATCH /courses/{id}` field or a dedicated endpoint — `CourseUpdate` currently has no `join_mode`. Keep it **read-only** in P2 (out of scope); do not invent an endpoint. Flag for a later phase.

- [ ] **Step 3** — `score-categories-view.tsx` (T035): **read-only** list of score categories via the P1 `scores.py` `GET /courses/{id}/score-categories` (reuse the `useScoreCategories` hook from P1's `use-setup.ts`). Editing lives in the P1 setup score-policy step; this is the overview surface. Link to the setup step to edit.

- [ ] **Step 4** — mount T033/T034/T035 into the enrollment page (tabs/sections alongside T031/T032).

- [ ] **Step 5: Verify** — `npx tsc --noEmit && npm run lint`; manual: approve a pending request (moves to roster), reveal/rotate the code, view score categories.

- [ ] **Step 6: Commit** — `git commit -am "feat(teacher): join-request approval + course-code modal + score-categories view (T033-T035)"`

---

### Task 16: happy-path spec + full regression + P2 close-out

**Files:**
- Create: `frontend/e2e/join-funnel.spec.ts` (or a vitest orchestration test if e2e infra is unavailable — see P0/P1 handoff limitation)
- Modify: `docs/superpowers/plans/2026-07-07-meli-cle-roadmap.md` (tracker + handoff), `docs/superpowers/RESUME.md`

- [ ] **Step 1: Happy-path test** — drive the join funnel end-to-end. If backend/session e2e infra is unavailable (per the P0/P1 `role-routing` limitation — the e2e webServer runs `npm run dev` only, no backend/session), add a **vitest** that renders `JoinFunnel` against mocked `use-readiness`/`use-enrollment` hooks and asserts: bad code → S004; good code (`code` mode) → survey → ready-check → recommendation (claim-limit visible) → summary → join success (S013); good code (`code_plus_approval`) → pending-approval terminal; draft course → S012. Document which path you took.

- [ ] **Step 2: Full regression** — backend `.\.venv\Scripts\python.exe -m pytest -q` (only known pre-existing failures remain; zero new); frontend `npx tsc --noEmit`, `npx vitest run`, `npm run build`, `npm run lint` (confirm zero NEW lint issues — the P0/P1 baseline is 22 problems all in pre-existing untouched files). Run `/code-review` over the full P2 diff; fix CRITICAL/HIGH. Run `frontend-design`/`design-review` polish pass over the join funnel + teacher enrollment screens.

- [ ] **Step 3: Close out** — check P2 in the roadmap Phase Tracker; append a Handoff Log entry (date, commits, gotchas, "NEXT: write P3 plan — checkpoint loop core; P3 builds on P2's active enrollments + P1's checkpoint drafts, and adds `checkpoint_responses` (+RLS following the readiness_responses pattern established here)"); update `RESUME.md`. `git add -f docs/superpowers/... && git commit -m "docs(roadmap): P2 complete — handoff for P3"`.

---

## Self-review checklist (confirm before marking P2 done)

**Spec §4.7 (readiness):**
- [ ] `readiness_responses` (`user_id`, `course_id`, `phase`, `answers` JSONB, `result` JSONB, `status`, timestamps) with the full four-value `phase` CHECK (forward-compatible for a future placement test — Decision 4) — Task 2.
- [ ] Survey/ready-check definitions come from pilot config, not the DB; the funnel renders `ReadinessPhaseDef` by question `kind`; `scale` uses `confidence_scale` — Task 3 (service) + Task 10 (renderer).
- [ ] `recommendation.result` carries `pilot.claim_limits['recommendation']` verbatim and the UI surfaces it prominently (S009 + S011) — Task 3 + Task 11.
- [ ] `readiness.py` router: `POST /courses/{id}/readiness/{phase}`, `GET .../readiness/summary`, `GET .../preview` (short/deep, code-gated) — Task 4.
- [ ] Readiness is pre-enrollment → NO `learning_event` / mastery emission (deliberate data-minimization boundary) — Decision 4 sub-decision.

**Spec §4.7 (join approval) + §4.8 (setup gate):**
- [ ] `enrollments.status (pending|active|rejected)` column + CHECK, default `active` (backfills existing rows) — Task 1.
- [ ] `join_mode='code'` → active (S013); `join_mode='code_plus_approval'` → pending; approve→active / deny→rejected — Task 5 + Task 6.
- [ ] `enroll-by-code` reuses `assert_course_open` (Decision 3) → `SETUP_NOT_OPEN` (S012); `enroll_code_active=False` → `JOIN_CODE_INACTIVE` (S004) — Task 5.
- [ ] A `pending` student cannot read the course workspace (`active`-only visibility in `get_course`/`list_courses`) — Task 5.
- [ ] Teacher join-request list/approve/deny + roster endpoints, owner-guarded — Task 6.

**RLS (Global Rules — first P2 student-owned table):**
- [ ] `readiness_responses` RLS migration hand-written to the `28236be3d7b3` pattern (ENABLE RLS + `owner_isolation` policy on `user_id`, `app.current_user_id` GUC) — Task 2.
- [ ] RLS owner-isolation enforced under `meli_app` (isolation test against `async_engine`, skip-guarded offline) — Task 8.

**Cross-cutting (Global Rules):**
- [ ] TDD: failing test first for every backend behavior (Tasks 1–6, 8). `APIResponse[T]` envelope; UUID PKs + Timestamp mixin; Postgres CHECK enums; upsert via `pg_insert(...).on_conflict_do_update` (Task 3, matching `services/mastery.py`).
- [ ] Frontend: join funnel reuses `StepWizard` + `StateBanner` + `EmptyState`; config-driven from `usePilotConfig`; tokens only; i18n keys under `student.join.*` / `teacher.*`; vitest where logic exists (Tasks 9–12, 16). Figma S003–S013 + T029–T035.
- [ ] Existing `JoinCourseDialog` consumer of `useEnrollByCode` kept working after the result-shape change (Task 9).
- [ ] Migrations hand-written (autogenerate drift discarded); Windows venv + `alembic heads` chained on `6500885d2cfc`.

**Open reconciliation flags for the executor:**
- Verify `pg_insert(...).on_conflict_do_update(...).returning(...)` re-fetch under async session (Task 3 note; mirror `mastery.py`).
- Confirm the `readiness_router` prefix (`/courses/{course_id}`) doesn't shadow existing `courses.py` routes after registration (Task 4 note).
- Decide the `GET /courses/lookup?code=` endpoint (Task 9 Step 2): add it (fold test+impl into Task 5) or drive previews from an id captured differently — the endpoint is the cleaner S004 UX.
- Flesh out the RLS test pre-req fixtures + `finally` cleanup on the shared dev DB, or fall back to the `pg_policies`/`relrowsecurity` assertion (Task 8 note).
- `join_mode` stays read-only in T034 (no PATCH endpoint in P2) — do not invent one (Task 15 note).
