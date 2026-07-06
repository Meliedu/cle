# P1 — Course Setup Wizard & Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. TDD is mandatory: failing test first for every backend behavior.

**Goal:** Ship the teacher course-setup wizard and its server-side course-open gate. Extend `courses` and `course_meetings` in place; add `checkpoints`, `checkpoint_cards`, `score_categories`; add the `analyze_course_setup` + `generate_checkpoints` background jobs (grounded, concept-tagged, DRAFT-only); expose `setup.py` / `checkpoints.py` / `scores.py` routers with gate + state-machine tests; and build the `StepWizard` pattern component driving `/teacher/courses/[id]/setup` across Figma screens T014–T028.

**Architecture:** Extend-in-place. The setup wizard is a client-orchestrated `StepWizard` reading/writing a per-course `setup_checklist` JSONB and firing existing pipelines (syllabus import, document processing) plus two NEW task types. Checkpoints are generated grounded on the existing `retriever.py` + `syllabus_grounding.py` and concept-tagged via the existing `concept_tagger.py` inheritance path — created in `draft` state ONLY (the full publish state machine + student response tables are P3). The course-open gate reuses the EXISTING `courses.context_status` as the single authority (see Decision 1).

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic + Pydantic v2 + pytest; Next.js 16 App Router + React 19 + TanStack Query + next-intl + Playwright/vitest.

---

## Session bootstrap (read before any code)

1. Read `docs/superpowers/plans/2026-07-07-meli-cle-roadmap.md` — **Global Rules** + the P1 brief.
2. Read the spec `docs/superpowers/specs/2026-07-06-meli-cle-checkpoint-loop-design.md` §3.4 (gates), §4.1 (sessions), §4.2 (checkpoints/cards), §4.5 (score), §4.8 (setup gate), §5 (`setup.py` + checkpoint endpoints).
3. Read this plan top-to-bottom, plus the real files each task names — **do not guess signatures**.
4. Windows dev env: backend venv at `backend/.venv`; Docker Postgres 17 + pgvector up (`docker compose up -d`); `langassistant_test` DB created with the same creds. Backend tests run from `backend/` as `.\.venv\Scripts\python.exe -m pytest`. Frontend runs from `frontend/` via `npx`.
5. Branch: `feat/cle-p0-shell` (P1 commits land here until the phase PR).
6. **Figma:** file key `EhzLyFCTZBIGU4iNyHUqvl`, page `final` (`1372:2`), group `1372:34` ("Teacher flow group - 2. Course Setup"). Node ids pulled at plan-write time (list below); call `get_design_context` per node before building each screen.

**Figma node ids (T014–T028, group `1372:34`):**

| Screen | Node id | Screen | Node id |
|---|---|---|---|
| T014 new-course-start | `1372:36` | T022 checkpoint-generation-review | `1372:52` |
| T015 course-basics | `1372:38` | T023 previous-term-memory-import | `1372:54` |
| T016 syllabus-upload | `1372:40` | T024 score-policy-setup | `1372:56` |
| T017 core-materials-upload-progress | `1372:42` | T025 class-code-hidden-reveal-deactivate | `1372:58` |
| T018 schedule-and-venue-setup | `1372:44` | T026 setup-review-checklist | `1372:60` |
| T019 course-material-analyzer-review | `1372:46` | T027 setup-publish-success | `1372:62` |
| T020 ilo-map-builder | `1372:48` | T028 setup-missing-source-error | `1372:64` |
| T021 session-generation-review | `1372:50` | | |

---

## Decisions (reconciliation of spec vs existing schema — read first)

### Decision 1 — `setup_status` vs the existing `context_status` (spec §4.8 vs `models/course.py`)

`courses` **already has** `context_status ('draft'|'approved')` + `context_approved_at` — the Course Context Package approval gate that today releases touchpoints / note drafting. The spec §4.8 asks for a new `setup_status enum(draft, in_review, published)`.

**Decision:** Keep `context_status` as the **single authoritative course-open gate**. All gate checks (`SETUP_NOT_OPEN`) read `context_status = 'approved'` — so every existing consumer of that column keeps working unchanged, and P2 enrollment reuses the exact same authority. **Add** `setup_status ('draft'|'in_review'|'published')` as the wizard's own lifecycle/progress state (it needs the `in_review` intermediate that T026 renders and T027/T028 branch on). On `POST .../setup/publish` the service sets, in one transaction: `setup_status='published'` **and** `context_status='approved'` **and** `context_approved_at=now()`. On `POST .../setup/reopen`, `setup_status` drops back to `draft`/`in_review` but `context_status` **stays** `approved` (§4.8: reopening must not lock enrolled students out; it only re-flags artifacts whose sources changed). Net: no duplicated gate logic, no breaking change, and spec fidelity for the 3-state wizard.

### Decision 2 — `course_meetings` new columns (spec §4.1 vs `models/curriculum.py`)

Spec §4.1 wants `session_no`, `venue`, `release_state enum(locked, released, completed, archived)`, `topic_summary`. Existing `course_meetings` has `meeting_index` (unique per course), `location`, `status ('planned'|'in_progress'|'taught'|'cancelled')`, JSONB briefing/summary.

**Decision:** **Reuse** `meeting_index` for `session_no` and `location` for `venue` (no new columns — they are exact equivalents already read by the calendar feed). **Add** `topic_summary text` (no equivalent; `post_meeting_summary` is JSONB and semantically a post-hoc AI summary). **Add** `release_state` as a NEW column **distinct** from `status`: `status` tracks pedagogical lifecycle (planned→taught, Canvas-synced, used elsewhere) while `release_state` tracks **student visibility/gating** (locked vs released) — a different axis. Mapping release_state onto status would conflate "taught" (it happened) with "released" (students can see it) and 'cancelled' has no release analog. Default `release_state='locked'`.

### Decision 3 — checkpoints created DRAFT-only in P1 (spec §4.2 vs P3)

The `checkpoints.status` enum is created with the **full** spec machine (`draft…archived`) so P3 needs no migration to widen it, but every P1 endpoint writes only `draft`/`teacher_editing`. A service guard + test asserts P1 rejects `approve/schedule/publish/close` transitions (those ship in P3). No `checkpoint_responses` / `attendance` tables and therefore **no new student-owned row tables this phase** → no RLS migration in P1 (RLS lands with `checkpoint_responses` in P3, pattern `28236be3d7b3`). `concept_tags.target_kind` gains `'checkpoint_card'` now so card tagging works.

---

### Task 1: `courses` setup columns — migration + model + schema (Decision 1)

**Files:**
- Modify: `backend/app/models/course.py`
- Modify: `backend/app/schemas/course.py`
- Create: Alembic migration (autogenerate then hand-edit the CHECK constraints)
- Test: `backend/tests/test_course_setup_columns.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_course_setup_columns.py
import pytest
from sqlalchemy import select

from app.models.course import Course


@pytest.mark.asyncio
async def test_new_course_defaults_setup_columns(db_session, instructor_user):
    course = Course(
        name="LANG1511", language="zh", instructor_id=instructor_user.id,
        enroll_code="ABCD2345",
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    assert course.setup_status == "draft"
    assert course.setup_checklist == {}
    assert course.join_mode == "code"
    assert course.enroll_code_active is True
    # existing gate column untouched
    assert course.context_status == "draft"


@pytest.mark.asyncio
async def test_setup_status_check_constraint(db_session, instructor_user):
    from sqlalchemy.exc import IntegrityError
    course = Course(
        name="bad", language="zh", instructor_id=instructor_user.id,
        enroll_code="EFGH2345", setup_status="nonsense",
    )
    db_session.add(course)
    with pytest.raises(IntegrityError):
        await db_session.commit()
```

> Match the real fixture names in `backend/tests/conftest.py` (`db_session`, an instructor user fixture). Grep `conftest.py` first and adapt fixture identifiers — do not assume.

- [ ] **Step 2: Run to verify FAIL** — from `backend/`: `.\.venv\Scripts\python.exe -m pytest tests/test_course_setup_columns.py -v` → `AttributeError`/`TypeError` on the unknown columns.

- [ ] **Step 3: Extend the model** — in `backend/app/models/course.py`, add to `Course.__table_args__` (alongside the existing `ck_courses_context_status_valid`):

```python
        CheckConstraint(
            "setup_status IN ('draft','in_review','published')",
            name="ck_courses_setup_status_valid",
        ),
        CheckConstraint(
            "join_mode IN ('code','code_plus_approval')",
            name="ck_courses_join_mode_valid",
        ),
```

and add the columns (import `Boolean` and `JSONB` at the top — `from sqlalchemy import Boolean`, `from sqlalchemy.dialects.postgresql import JSONB`):

```python
    setup_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default=text("'draft'")
    )
    setup_checklist: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    join_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="code", server_default=text("'code'")
    )
    enroll_code_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
```

- [ ] **Step 4: Migration** — `.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "courses setup columns"`. Inspect: confirm the four `add_column`s + two named CHECK constraints (autogen may miss CHECKs on Postgres String columns — add `op.create_check_constraint(...)` by hand if absent, with matching `drop_check_constraint` in `downgrade`). Apply: `.\.venv\Scripts\python.exe -m alembic upgrade head`.

- [ ] **Step 5: Schema** — in `backend/app/schemas/course.py`, add the read fields to `CourseResponse` so the wizard can hydrate:

```python
    setup_status: str
    setup_checklist: dict
    join_mode: str
    enroll_code_active: bool
    context_status: str
```

- [ ] **Step 6: Run to verify PASS** — `.\.venv\Scripts\python.exe -m pytest tests/test_course_setup_columns.py tests/test_courses.py -v` (run the existing course suite to catch response-shape regressions).

- [ ] **Step 7: Commit** — `git add backend/app/models/course.py backend/app/schemas/course.py backend/alembic/versions backend/tests/test_course_setup_columns.py && git commit -m "feat(setup): courses setup_status/setup_checklist/join_mode/enroll_code_active columns"`

---

### Task 2: `course_meetings` `release_state` + `topic_summary` (Decision 2)

**Files:**
- Modify: `backend/app/models/curriculum.py`
- Modify: `backend/app/schemas/curriculum.py` (add fields to create/update/response)
- Create: Alembic migration
- Test: `backend/tests/test_meeting_release_state.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_meeting_release_state.py
import pytest
from datetime import datetime, timezone

from app.models.curriculum import CourseMeeting


@pytest.mark.asyncio
async def test_meeting_defaults_release_state_locked(db_session, seed_course):
    m = CourseMeeting(
        course_id=seed_course.id, meeting_index=1,
        scheduled_at=datetime.now(timezone.utc),
    )
    db_session.add(m)
    await db_session.commit()
    await db_session.refresh(m)
    assert m.release_state == "locked"
    assert m.topic_summary is None


@pytest.mark.asyncio
async def test_release_state_check_constraint(db_session, seed_course):
    from sqlalchemy.exc import IntegrityError
    m = CourseMeeting(
        course_id=seed_course.id, meeting_index=2,
        scheduled_at=datetime.now(timezone.utc), release_state="oops",
    )
    db_session.add(m)
    with pytest.raises(IntegrityError):
        await db_session.commit()
```

- [ ] **Step 2: FAIL run** — `.\.venv\Scripts\python.exe -m pytest tests/test_meeting_release_state.py -v`.

- [ ] **Step 3: Model** — in `CourseMeeting.__table_args__` add:

```python
        CheckConstraint(
            "release_state IN ('locked','released','completed','archived')",
            name="ck_course_meetings_release_state_valid",
        ),
```

and columns (existing imports already cover `String`/`text`; add `text` import if missing):

```python
    release_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="locked", server_default=text("'locked'")
    )
    topic_summary: Mapped[str | None] = mapped_column(String)
```

- [ ] **Step 4: Migration** — autogenerate `"course_meetings release_state + topic_summary"`, verify 2 `add_column` + the CHECK, `upgrade head`.

- [ ] **Step 5: Schema** — in `backend/app/schemas/curriculum.py`, add `topic_summary: str | None = None` to `CourseMeetingCreate`/`CourseMeetingUpdate`, and `release_state: str` + `topic_summary: str | None` to `CourseMeetingResponse`. (`release_state` is transitioned by the schedule step's dedicated endpoint in Task 7, not by free-form update — leave it off Create/Update.)

- [ ] **Step 6: PASS run** — `.\.venv\Scripts\python.exe -m pytest tests/test_meeting_release_state.py tests/test_meetings.py -v`.

- [ ] **Step 7: Commit** — `git commit -am "feat(setup): course_meetings release_state + topic_summary (visibility axis distinct from status)"`

---

### Task 3: checkpoint + score-category models + migration + concept_tags widening (Decision 3)

**Files:**
- Create: `backend/app/models/checkpoint.py`
- Modify: `backend/app/models/__init__.py` (export new models), `backend/app/models/concept.py` (widen `ck_concept_tags_target_kind_valid`)
- Create: `backend/app/models/score.py` (or fold into `checkpoint.py`; keep `score.py` separate per "many small files")
- Create: Alembic migration
- Test: `backend/tests/test_checkpoint_models.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_checkpoint_models.py
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.checkpoint import Checkpoint, CheckpointCard
from app.models.score import ScoreCategory


@pytest.mark.asyncio
async def test_checkpoint_defaults_draft(db_session, seed_course):
    cp = Checkpoint(course_id=seed_course.id, kind="session", title="Session 1 check")
    db_session.add(cp)
    await db_session.commit()
    await db_session.refresh(cp)
    assert cp.status == "draft"
    assert cp.qr_enabled is False


@pytest.mark.asyncio
async def test_only_one_final_comments_card(db_session, seed_course):
    cp = Checkpoint(course_id=seed_course.id, kind="session", title="c")
    db_session.add(cp)
    await db_session.flush()
    db_session.add(CheckpointCard(checkpoint_id=cp.id, position=0, kind="final_comments", prompt="Anything else?"))
    db_session.add(CheckpointCard(checkpoint_id=cp.id, position=1, kind="final_comments", prompt="dup"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_checkpoint_card_can_target_concept_tag(db_session, seed_course):
    # target_kind='checkpoint_card' must be accepted by the widened CHECK
    from app.models.concept import ConceptTag, Concept
    import uuid
    concept = Concept(course_id=seed_course.id, name="tone sandhi", status="approved")
    db_session.add(concept)
    await db_session.flush()
    tag = ConceptTag(
        concept_id=concept.id, target_kind="checkpoint_card",
        target_id=uuid.uuid4(), suggestion_source="inheritance",
    )
    db_session.add(tag)
    await db_session.commit()  # must not raise


@pytest.mark.asyncio
async def test_score_category(db_session, seed_course):
    sc = ScoreCategory(course_id=seed_course.id, name="Participation", sort=0)
    db_session.add(sc)
    await db_session.commit()
    await db_session.refresh(sc)
    assert sc.name == "Participation"
```

- [ ] **Step 2: FAIL run** — `.\.venv\Scripts\python.exe -m pytest tests/test_checkpoint_models.py -v` → `ModuleNotFoundError`.

- [ ] **Step 3: `models/checkpoint.py`** (full enum per §4.2; P1 only writes draft/teacher_editing — enforced in the service, Task 8):

```python
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Checkpoint(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "checkpoints"
    __table_args__ = (
        CheckConstraint("kind IN ('session','follow_up')", name="ck_checkpoints_kind_valid"),
        CheckConstraint(
            "status IN ('draft','teacher_editing','approved','scheduled',"
            "'published','live','closed','archived')",
            name="ck_checkpoints_status_valid",
        ),
        CheckConstraint(
            "close_rule IS NULL OR close_rule IN ('manual','at_close_at','end_of_session')",
            name="ck_checkpoints_close_rule_valid",
        ),
        CheckConstraint("id <> carried_from_id", name="ck_checkpoints_no_self_carry"),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_meetings.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default=text("'draft'")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    release_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_rule: Mapped[str | None] = mapped_column(String(20))
    qr_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    carried_from_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("checkpoints.id", ondelete="SET NULL")
    )
    generation_meta: Mapped[dict | None] = mapped_column(JSONB)


class CheckpointCard(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "checkpoint_cards"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('review_point','final_comments')", name="ck_checkpoint_cards_kind_valid"
        ),
        CheckConstraint(
            "removed_reason IS NULL OR removed_reason IN "
            "('not_needed','duplicate','not_covered','other')",
            name="ck_checkpoint_cards_removed_reason_valid",
        ),
        # Exactly one non-removed final_comments card per checkpoint (§4.2:
        # fixed, not removable). Partial unique index mirrors the migration.
        Index(
            "uq_checkpoint_cards_one_final",
            "checkpoint_id",
            unique=True,
            postgresql_where=text("kind = 'final_comments' AND deleted_at IS NULL"),
        ),
    )

    checkpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("checkpoints.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    prompt: Mapped[str] = mapped_column(String, nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="SET NULL")
    )
    objective_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("learning_objectives.id", ondelete="SET NULL")
    )
    removed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    removed_reason: Mapped[str | None] = mapped_column(String(20))
    removed_note: Mapped[str | None] = mapped_column(String)
```

- [ ] **Step 4: `models/score.py`**

```python
import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ScoreCategory(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "score_categories"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    points_pool: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

- [ ] **Step 5: Widen `concept_tags` CHECK** — in `backend/app/models/concept.py`, edit the `ck_concept_tags_target_kind_valid` constraint string to add `'checkpoint_card'`:

```python
            "target_kind IN ('chunk','question','flashcard_card','pronunciation_item',"
            "'pool_item','objective','meeting','assignment','checkpoint_card')",
```

- [ ] **Step 6: Register models** — add `Checkpoint`, `CheckpointCard`, `ScoreCategory` imports/exports to `backend/app/models/__init__.py` following the existing export style (so `from app.models import Checkpoint` and `Base.metadata` include them).

- [ ] **Step 7: Migration** — autogenerate `"checkpoints, checkpoint_cards, score_categories + concept_tags checkpoint_card"`. Hand-verify: `create_table` ×3, the partial unique index `uq_checkpoint_cards_one_final` (add `op.create_index(..., postgresql_where=sa.text("kind = 'final_comments' AND deleted_at IS NULL"))` if autogen drops the predicate), and the `concept_tags` CHECK swap (`op.drop_constraint('ck_concept_tags_target_kind_valid', 'concept_tags')` + `op.create_check_constraint(...)` with the widened list; mirror in `downgrade`). `upgrade head`.

- [ ] **Step 8: PASS run** — `.\.venv\Scripts\python.exe -m pytest tests/test_checkpoint_models.py -v` → 4 passed. Also `.\.venv\Scripts\python.exe -m pytest tests/test_concept_tags.py -v` (widened CHECK didn't break existing kinds).

- [ ] **Step 9: Commit** — `git commit -am "feat(checkpoint): checkpoints/checkpoint_cards/score_categories models + concept_tags checkpoint_card kind"`

---

### Task 4: setup service + course-open gate + score-category seeding

**Files:**
- Create: `backend/app/services/setup.py`
- Modify: `backend/app/api/courses.py` (`create_course` seeds score categories from pilot config)
- Test: `backend/tests/test_setup_service.py`

The service owns: the checklist step keys, the publish gate (Decision 1), reopen, and typed error codes.

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_setup_service.py
import pytest

from app.services.setup import (
    SETUP_STEP_KEYS, SetupGateError, publish_setup, reopen_setup, set_step_flag,
)


@pytest.mark.asyncio
async def test_publish_blocked_until_all_steps_complete(db_session, seed_course):
    with pytest.raises(SetupGateError) as exc:
        await publish_setup(db_session, seed_course)
    assert exc.value.code == "SETUP_INCOMPLETE"
    # context gate untouched by a failed publish
    await db_session.refresh(seed_course)
    assert seed_course.context_status == "draft"
    assert seed_course.setup_status == "draft"


@pytest.mark.asyncio
async def test_publish_flips_both_gates(db_session, seed_course):
    for key in SETUP_STEP_KEYS:
        await set_step_flag(db_session, seed_course, key, True)
    await publish_setup(db_session, seed_course)
    await db_session.refresh(seed_course)
    assert seed_course.setup_status == "published"
    assert seed_course.context_status == "approved"       # Decision 1
    assert seed_course.context_approved_at is not None


@pytest.mark.asyncio
async def test_reopen_keeps_students_in(db_session, seed_course):
    for key in SETUP_STEP_KEYS:
        await set_step_flag(db_session, seed_course, key, True)
    await publish_setup(db_session, seed_course)
    await reopen_setup(db_session, seed_course)
    await db_session.refresh(seed_course)
    assert seed_course.setup_status == "draft"
    assert seed_course.context_status == "approved"       # §4.8: stays open
```

- [ ] **Step 2: FAIL run** — `.\.venv\Scripts\python.exe -m pytest tests/test_setup_service.py -v`.

- [ ] **Step 3: Implement `services/setup.py`**

```python
"""Course-setup wizard state + the server-side course-open gate (spec §4.8).

Decision 1: ``courses.context_status`` remains the single authoritative
course-open gate; ``setup_status`` is the wizard lifecycle. Publish flips both;
reopen only rolls back ``setup_status`` so enrolled students stay in (§4.8).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import Course

# Step flags stored in ``courses.setup_checklist`` (§4.8). Ordered as the wizard
# renders them; ``analyzer_review`` gates on the analyze job, ``checkpoints`` on
# the generate job, both reviewed by the teacher.
SETUP_STEP_KEYS: tuple[str, ...] = (
    "basics", "syllabus", "materials", "schedule", "analyzer_review",
    "ilo_map", "checkpoints", "score_policy", "class_code",
)


class SetupGateError(Exception):
    """Raised when a gate refuses. ``code`` is the typed error the UI maps."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def set_step_flag(
    db: AsyncSession, course: Course, key: str, value: bool
) -> Course:
    if key not in SETUP_STEP_KEYS:
        raise SetupGateError("UNKNOWN_STEP", f"Unknown setup step '{key}'")
    # Immutable update: build a fresh dict so SQLAlchemy sees the JSONB dirty.
    checklist = {**(course.setup_checklist or {}), key: bool(value)}
    course.setup_checklist = checklist
    if course.setup_status == "draft" and any(checklist.values()):
        course.setup_status = "in_review"
    await db.commit()
    await db.refresh(course)
    return course


def missing_steps(course: Course) -> list[str]:
    checklist = course.setup_checklist or {}
    return [k for k in SETUP_STEP_KEYS if not checklist.get(k)]


async def publish_setup(db: AsyncSession, course: Course) -> Course:
    missing = missing_steps(course)
    if missing:
        raise SetupGateError(
            "SETUP_INCOMPLETE",
            f"Setup cannot publish; incomplete steps: {', '.join(missing)}",
        )
    course.setup_status = "published"
    course.context_status = "approved"          # Decision 1: single gate
    course.context_approved_at = _utcnow()
    await db.commit()
    await db.refresh(course)
    return course


async def reopen_setup(db: AsyncSession, course: Course) -> Course:
    # §4.8: reopening does NOT lock students out — context_status stays approved.
    course.setup_status = "in_review" if any((course.setup_checklist or {}).values()) else "draft"
    await db.commit()
    await db.refresh(course)
    return course


def assert_course_open(course: Course) -> None:
    """Gate used by P2 enrollment / workspace access. ``SETUP_NOT_OPEN``."""
    if course.context_status != "approved":
        raise SetupGateError("SETUP_NOT_OPEN", "This course is not open yet.")
```

- [ ] **Step 4: Seed score categories on course create** — in `backend/app/api/courses.py` `create_course`, after the `Enrollment` is added and before `await db.commit()`, seed from the pilot profile:

```python
        from app.models.score import ScoreCategory
        from app.pilot import get_pilot_profile

        for i, cat in enumerate(get_pilot_profile().score_category_defaults):
            db.add(ScoreCategory(
                course_id=course.id, name=cat.name,
                weight=cat.weight, sort=i,
            ))
```

Add a test to `test_setup_service.py` (or `test_courses.py`) asserting a freshly created course has the pilot's two default categories (`Participation`, `Quizzes`).

- [ ] **Step 5: PASS run** — `.\.venv\Scripts\python.exe -m pytest tests/test_setup_service.py tests/test_courses.py -v`.

- [ ] **Step 6: Commit** — `git commit -am "feat(setup): setup gate service (publish/reopen, SETUP_NOT_OPEN) + pilot score-category seeding"`

---

### Task 5: `analyze_course_setup` job — course map + missing-source detection

**Files:**
- Create: `backend/app/services/setup_analysis.py`
- Modify: `backend/app/services/worker.py` (`process_task` dispatch — add the branch)
- Test: `backend/tests/test_analyze_course_setup.py`

Builds a course map (documents, meetings, objectives, whether an applied syllabus exists) and flags **missing sources** (objectives with no supporting chunk, meetings with no linked materials). Result is returned as the task result dict (read back via `GET .../setup/analysis`, which queries the latest completed `analyze_course_setup` Task by `Task.payload.op("->>")("course_id")` — the documented JSON pattern).

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_analyze_course_setup.py
import pytest

from app.services.setup_analysis import run_analyze_course_setup


@pytest.mark.asyncio
async def test_analyze_flags_objectives_without_sources(db_session, seed_course, make_objective):
    await make_objective(seed_course, statement="Order food in Mandarin")
    result = await run_analyze_course_setup(db_session, {"course_id": str(seed_course.id)})
    assert result["course_id"] == str(seed_course.id)
    assert result["counts"]["objectives"] == 1
    # No chunks/materials seeded → objective is a missing source
    assert any(m["kind"] == "objective_without_source" for m in result["missing_sources"])
    assert result["has_missing_sources"] is True


@pytest.mark.asyncio
async def test_analyze_clean_when_no_gaps(db_session, seed_course):
    result = await run_analyze_course_setup(db_session, {"course_id": str(seed_course.id)})
    assert result["has_missing_sources"] is False
```

> `make_objective` may not exist — add a small local fixture/helper in the test (create a `LearningObjective` row) rather than assuming a shared factory.

- [ ] **Step 2: FAIL run** — `.\.venv\Scripts\python.exe -m pytest tests/test_analyze_course_setup.py -v`.

- [ ] **Step 3: Implement `services/setup_analysis.py`**

```python
"""``analyze_course_setup`` job: course map + missing-source detection (T019/T028).

Read-only aggregation — never mutates course state. The setup router persists
the completion flag; this handler just returns the map so ``GET .../setup/analysis``
can render the review screen and the missing-source error state.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ConceptTag, Document, LearningObjective
from app.models.curriculum import CourseMeeting


async def run_analyze_course_setup(
    db: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    course_id = uuid.UUID(payload["course_id"])

    doc_count = (
        await db.execute(
            select(func.count()).select_from(Document).where(
                Document.course_id == course_id, Document.deleted_at.is_(None)
            )
        )
    ).scalar_one()
    meetings = (
        await db.execute(
            select(CourseMeeting).where(
                CourseMeeting.course_id == course_id,
                CourseMeeting.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    objectives = (
        await db.execute(
            select(LearningObjective).where(
                LearningObjective.course_id == course_id,
                LearningObjective.deleted_at.is_(None),
            )
        )
    ).scalars().all()

    missing_sources: list[dict[str, Any]] = []

    # Objective is a "missing source" when nothing tags it as covered — i.e.
    # no concept_tags row anchors an objective the checkpoint generator could
    # ground on. (P1 heuristic; P3 tightens to chunk-level coverage.)
    for obj in objectives:
        tagged = (
            await db.execute(
                select(func.count()).select_from(ConceptTag).where(
                    ConceptTag.target_kind == "objective",
                    ConceptTag.target_id == obj.id,
                )
            )
        ).scalar_one()
        if tagged == 0 and doc_count == 0:
            missing_sources.append(
                {"kind": "objective_without_source", "id": str(obj.id),
                 "label": obj.statement[:120]}
            )

    for m in meetings:
        # A scheduled session with no materials and no topic summary can't
        # anchor checkpoint generation → flag for the analyzer review.
        if doc_count == 0 and not m.topic_summary:
            missing_sources.append(
                {"kind": "session_without_material", "id": str(m.id),
                 "label": m.title or f"Session {m.meeting_index}"}
            )

    return {
        "course_id": str(course_id),
        "counts": {
            "documents": int(doc_count),
            "meetings": len(meetings),
            "objectives": len(objectives),
        },
        "missing_sources": missing_sources,
        "has_missing_sources": bool(missing_sources),
    }
```

- [ ] **Step 4: Worker dispatch** — in `backend/app/services/worker.py` `process_task`, add before the final `else`:

```python
    elif task.task_type == "analyze_course_setup":
        from app.services.setup_analysis import run_analyze_course_setup
        return await run_analyze_course_setup(session, task.payload)
```

- [ ] **Step 5: PASS run** — `.\.venv\Scripts\python.exe -m pytest tests/test_analyze_course_setup.py tests/test_worker.py -v` (run the worker suite to confirm dispatch didn't regress).

- [ ] **Step 6: Commit** — `git commit -am "feat(setup): analyze_course_setup job (course map + missing-source detection)"`

---

### Task 6: `generate_checkpoints` job — grounded, DRAFT-only, concept-tagged

**Files:**
- Create: `backend/app/services/checkpoint_generation.py`
- Modify: `backend/app/services/worker.py` (dispatch)
- Test: `backend/tests/test_generate_checkpoints.py`

Generates one `draft` checkpoint per session (or per requested meeting), grounded via `retriever.py` (`hybrid_retrieve`) + `syllabus_grounding.load_syllabus_grounding`, with N review-point cards + exactly one fixed `final_comments` card. Each review-point card that anchors a chunk enqueues a `tag_artifact_concepts` task (`target_kind='checkpoint_card'`, `source_chunk_id=<anchor>`) so cards inherit concept tags at weight ×0.7 — reusing the existing `adaptive_jobs.run_tag_artifact_concepts` → `concept_tagger.inherit_tags_from_chunk` path unchanged. **Never** advances status past `draft`.

- [ ] **Step 1: Failing test** (stub the LLM/retriever like the existing generation-job tests — grep `tests/test_*generat*` for the monkeypatch pattern and match it)

```python
# backend/tests/test_generate_checkpoints.py
import pytest
from sqlalchemy import select

from app.models.checkpoint import Checkpoint, CheckpointCard
from app.models.task import Task
from app.services.checkpoint_generation import run_generate_checkpoints


@pytest.mark.asyncio
async def test_generate_creates_draft_checkpoint_with_final_card(
    db_session, seed_course, seed_meeting, monkeypatch
):
    async def fake_ground(db, course_id):
        return "Syllabus: greetings, numbers."
    monkeypatch.setattr(
        "app.services.checkpoint_generation.load_syllabus_grounding", fake_ground
    )
    async def fake_cards(*args, **kwargs):
        return [
            {"prompt": "How confident are you ordering food?", "chunk_id": None},
            {"prompt": "Rate your grasp of tone sandhi.", "chunk_id": None},
        ]
    monkeypatch.setattr(
        "app.services.checkpoint_generation.draft_review_cards", fake_cards
    )

    result = await run_generate_checkpoints(
        db_session, {"course_id": str(seed_course.id), "meeting_id": str(seed_meeting.id)}
    )
    cps = (await db_session.execute(
        select(Checkpoint).where(Checkpoint.course_id == seed_course.id)
    )).scalars().all()
    assert len(cps) == 1
    assert cps[0].status == "draft"          # Decision 3: never past draft
    cards = (await db_session.execute(
        select(CheckpointCard).where(CheckpointCard.checkpoint_id == cps[0].id)
    )).scalars().all()
    kinds = sorted(c.kind for c in cards)
    assert kinds.count("final_comments") == 1   # fixed final card
    assert result["created"] == 1


@pytest.mark.asyncio
async def test_generate_enqueues_tag_tasks_for_anchored_cards(
    db_session, seed_course, seed_meeting, seed_chunk, monkeypatch
):
    monkeypatch.setattr(
        "app.services.checkpoint_generation.load_syllabus_grounding",
        lambda db, cid: _async_none(),
    )
    async def fake_cards(*a, **k):
        return [{"prompt": "grounded card", "chunk_id": str(seed_chunk.id)}]
    monkeypatch.setattr("app.services.checkpoint_generation.draft_review_cards", fake_cards)

    await run_generate_checkpoints(
        db_session, {"course_id": str(seed_course.id), "meeting_id": str(seed_meeting.id)}
    )
    tasks = (await db_session.execute(
        select(Task).where(Task.task_type == "tag_artifact_concepts")
    )).scalars().all()
    assert any(t.payload.get("target_kind") == "checkpoint_card" for t in tasks)
```

- [ ] **Step 2: FAIL run** — `.\.venv\Scripts\python.exe -m pytest tests/test_generate_checkpoints.py -v`.

- [ ] **Step 3: Implement `services/checkpoint_generation.py`** (grounding + a `draft_review_cards` LLM step kept as a separate monkeypatchable function, mirroring `concept_tagger._llm_tag_call`)

```python
"""``generate_checkpoints`` job (T022): grounded, DRAFT-only checkpoint drafting.

Grounds on the existing retriever + applied syllabus, drafts review-point cards
via the LLM, always appends exactly one fixed ``final_comments`` card, and
enqueues ``tag_artifact_concepts`` for chunk-anchored cards so they inherit
concept tags (weight ×0.7) through the existing tagger. Status stays ``draft`` —
approve/schedule/publish are P3.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.checkpoint import Checkpoint, CheckpointCard
from app.models.curriculum import CourseMeeting
from app.models.task import Task
from app.services.retriever import hybrid_retrieve
from app.services.syllabus_grounding import load_syllabus_grounding

logger = logging.getLogger(__name__)

# CLE default: 3 review-point cards + 1 fixed final card (§4.2). Teacher-editable
# afterward; the count is a starting point, not a hard limit.
DEFAULT_REVIEW_CARDS = 3

_CARD_SYSTEM_PROMPT = """You draft short self-assessment "review point" prompts \
for a language-class checkpoint. Given session context, return ONLY a JSON \
object {"cards": [{"prompt": "...", "chunk_id": "<id or null>"}]} where each \
prompt asks a student to rate their confidence on one concept just covered. \
Be concise and concrete."""


class _CardV1(BaseModel):
    model_config = ConfigDict(extra="ignore")
    prompt: str = Field(..., max_length=500)
    chunk_id: str | None = None


class _CardsV1(BaseModel):
    model_config = ConfigDict(extra="ignore")
    cards: list[_CardV1] = Field(default_factory=list)


async def draft_review_cards(
    *, context: str, n: int
) -> list[dict[str, Any]]:
    """LLM step (separate fn for test monkeypatching). Non-raising: returns a
    deterministic fallback so generation never hard-fails."""
    client = AsyncOpenAI(
        api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url
    )
    try:
        resp = await client.chat.completions.create(
            model=settings.llm_primary_model,
            messages=[
                {"role": "system", "content": _CARD_SYSTEM_PROMPT},
                {"role": "user", "content": f"Draft {n} cards.\n\n{context[:6000]}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        parsed = _CardsV1.model_validate_json(resp.choices[0].message.content or "{}")
        cards = [c.model_dump() for c in parsed.cards][:n]
        if cards:
            return cards
    except Exception:  # noqa: BLE001
        logger.warning("draft_review_cards LLM step failed; using fallback", exc_info=True)
    return [{"prompt": "Rate your confidence with today's key point.", "chunk_id": None}
            for _ in range(n)]


async def _build_context(db: AsyncSession, course_id: uuid.UUID, meeting: CourseMeeting) -> str:
    parts: list[str] = []
    grounding = await load_syllabus_grounding(db, course_id)
    if grounding:
        parts.append(grounding)
    if meeting.topic_summary:
        parts.append(f"Session topic: {meeting.topic_summary}")
    query = meeting.topic_summary or meeting.title or "session review"
    try:
        chunks = await hybrid_retrieve(db, course_id=course_id, query=query, top_k=6)
        parts.extend(getattr(c, "content", "")[:800] for c in chunks)
    except Exception:  # noqa: BLE001 — grounding is best-effort
        logger.warning("hybrid_retrieve failed during checkpoint gen", exc_info=True)
    return "\n\n".join(p for p in parts if p)


async def run_generate_checkpoints(
    db: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    course_id = uuid.UUID(payload["course_id"])
    meeting_id = uuid.UUID(payload["meeting_id"]) if payload.get("meeting_id") else None
    n_cards = int(payload.get("review_card_count", DEFAULT_REVIEW_CARDS))

    meetings = []
    if meeting_id:
        m = await db.get(CourseMeeting, meeting_id)
        if m is not None:
            meetings = [m]
    created = 0
    for meeting in meetings:
        context = await _build_context(db, course_id, meeting)
        cards = await draft_review_cards(context=context, n=n_cards)

        cp = Checkpoint(
            course_id=course_id, meeting_id=meeting.id, kind="session",
            title=f"{meeting.title or 'Session ' + str(meeting.meeting_index)} checkpoint",
            status="draft",
            generation_meta={"source": "generate_checkpoints", "meeting_id": str(meeting.id)},
        )
        db.add(cp)
        await db.flush()

        for i, card in enumerate(cards):
            chunk_id = card.get("chunk_id")
            chunk_uuid = uuid.UUID(chunk_id) if chunk_id else None
            db.add(CheckpointCard(
                checkpoint_id=cp.id, position=i, kind="review_point",
                prompt=card["prompt"], chunk_id=chunk_uuid,
            ))
            await db.flush()
            if chunk_uuid is not None:
                # Reuse the existing inheritance tagger via the worker.
                db.add(Task(
                    task_type="tag_artifact_concepts",
                    payload={
                        "target_kind": "checkpoint_card",
                        "target_id": str(cp.id),  # replaced below with card id
                        "course_id": str(course_id),
                        "source_chunk_id": str(chunk_uuid),
                    },
                    status="pending",
                ))
        # Fixed, non-removable final card (§4.2).
        db.add(CheckpointCard(
            checkpoint_id=cp.id, position=len(cards), kind="final_comments",
            prompt="Any final comments or questions about today's session?",
        ))
        created += 1

    await db.commit()
    return {"course_id": str(course_id), "created": created}
```

> **Reconcile at build time:** verify `hybrid_retrieve`'s real signature (`app/services/retriever.py` line 206 — args/kwargs and return shape) and adapt the call + `.content` access. Verify `card id` propagation — the tag task's `target_id` must be the **card** id, not the checkpoint id; capture `card_row.id` after `flush()` and use it (fix the placeholder before implementing).

- [ ] **Step 4: Worker dispatch** — add to `process_task`:

```python
    elif task.task_type == "generate_checkpoints":
        from app.services.checkpoint_generation import run_generate_checkpoints
        return await run_generate_checkpoints(session, task.payload)
```

- [ ] **Step 5: PASS run** — `.\.venv\Scripts\python.exe -m pytest tests/test_generate_checkpoints.py -v`.

- [ ] **Step 6: Commit** — `git commit -am "feat(checkpoint): generate_checkpoints job (grounded, draft-only, concept-tagged cards)"`

---

### Task 7: `meetings.py` release/schedule endpoint (schedule-and-venue step)

**Files:**
- Modify: `backend/app/api/meetings.py` (add `PATCH /meetings/{id}/release-state`)
- Test: `backend/tests/test_meeting_release_endpoint.py`

The schedule step (T018) sets venue via the existing meeting update; `release_state` transitions through a dedicated guarded endpoint with a validated transition map.

- [ ] **Step 1: Failing test** — assert an instructor can move `locked→released`, a non-owner gets 404, and an invalid transition (e.g. `archived→released`) returns 409. (Copy the authed-client + owner/non-owner fixtures from `tests/test_meetings.py`.)

- [ ] **Step 2: FAIL run** — `.\.venv\Scripts\python.exe -m pytest tests/test_meeting_release_endpoint.py -v`.

- [ ] **Step 3: Implement** — add to `backend/app/api/meetings.py`:

```python
_RELEASE_TRANSITIONS = {
    "locked": {"released"},
    "released": {"completed", "locked"},
    "completed": {"archived"},
    "archived": set(),
}


@router.patch(
    "/meetings/{meeting_id}/release-state",
    response_model=APIResponse[CourseMeetingResponse],
)
async def set_release_state(
    meeting_id: uuid.UUID,
    body: dict,  # {"release_state": "released"} — use a typed schema in impl
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[CourseMeetingResponse]:
    target = body.get("release_state")
    result = await db.execute(
        select(CourseMeeting).where(
            CourseMeeting.id == meeting_id,
            CourseMeeting.course_id == course.id,
            CourseMeeting.deleted_at.is_(None),
        )
    )
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if target not in _RELEASE_TRANSITIONS.get(meeting.release_state, set()):
        raise HTTPException(
            status_code=409,
            detail=f"Illegal release_state transition {meeting.release_state}->{target}",
        )
    meeting.release_state = target
    await db.commit()
    await db.refresh(meeting)
    return APIResponse(success=True, data=CourseMeetingResponse.model_validate(meeting))
```

> Replace the `body: dict` with a `MeetingReleaseStateRequest(BaseModel)` in `schemas/curriculum.py` (`release_state: Literal["locked","released","completed","archived"]`) so validation is at the boundary.

- [ ] **Step 4: PASS run** — `.\.venv\Scripts\python.exe -m pytest tests/test_meeting_release_endpoint.py -v`.

- [ ] **Step 5: Commit** — `git commit -am "feat(setup): meeting release-state transition endpoint (schedule & venue step)"`

---

### Task 8: `setup.py` router — wizard state, analyze, publish/reopen (gate tests)

**Files:**
- Create: `backend/app/api/setup.py`, `backend/app/schemas/setup.py`
- Modify: `backend/app/api/__init__.py` (register)
- Test: `backend/tests/test_setup_api.py`

- [ ] **Step 1: Failing test** (authed instructor client per `tests/test_courses.py`)

```python
# backend/tests/test_setup_api.py
import pytest


@pytest.mark.asyncio
async def test_get_setup_state(instructor_client, owned_course):
    r = await instructor_client.get(f"/api/courses/{owned_course.id}/setup")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["setup_status"] == "draft"
    assert set(data["steps"].keys())  # step flags present


@pytest.mark.asyncio
async def test_patch_step_flag(instructor_client, owned_course):
    r = await instructor_client.patch(
        f"/api/courses/{owned_course.id}/setup", json={"step": "basics", "done": True}
    )
    assert r.status_code == 200
    assert r.json()["data"]["steps"]["basics"] is True


@pytest.mark.asyncio
async def test_publish_gate_blocks_incomplete(instructor_client, owned_course):
    r = await instructor_client.post(f"/api/courses/{owned_course.id}/setup/publish")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "SETUP_INCOMPLETE"


@pytest.mark.asyncio
async def test_analyze_enqueues_task(instructor_client, owned_course):
    r = await instructor_client.post(f"/api/courses/{owned_course.id}/setup/analyze")
    assert r.status_code == 202


@pytest.mark.asyncio
async def test_non_owner_gets_404(student_client, owned_course):
    r = await student_client.get(f"/api/courses/{owned_course.id}/setup")
    assert r.status_code in (403, 404)
```

- [ ] **Step 2: FAIL run** — `.\.venv\Scripts\python.exe -m pytest tests/test_setup_api.py -v` → 404s.

- [ ] **Step 3: Implement `schemas/setup.py`**

```python
from pydantic import BaseModel


class SetupStepUpdate(BaseModel):
    step: str
    done: bool


class SetupStateResponse(BaseModel):
    setup_status: str
    context_status: str
    steps: dict[str, bool]
    missing: list[str]


class SetupAnalysisResponse(BaseModel):
    ready: bool
    analysis: dict | None = None
```

- [ ] **Step 4: Implement `api/setup.py`** (map `SetupGateError.code` to a structured `detail`)

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_owned_course
from app.models.course import Course
from app.models.task import Task
from app.schemas.common import APIResponse
from app.schemas.setup import SetupAnalysisResponse, SetupStateResponse, SetupStepUpdate
from app.services.setup import (
    SETUP_STEP_KEYS, SetupGateError, missing_steps, publish_setup, reopen_setup,
    set_step_flag,
)

router = APIRouter(prefix="/courses/{course_id}/setup", tags=["setup"])


def _state(course: Course) -> SetupStateResponse:
    checklist = course.setup_checklist or {}
    return SetupStateResponse(
        setup_status=course.setup_status,
        context_status=course.context_status,
        steps={k: bool(checklist.get(k)) for k in SETUP_STEP_KEYS},
        missing=missing_steps(course),
    )


def _gate_http(exc: SetupGateError) -> HTTPException:
    return HTTPException(status_code=409, detail={"code": exc.code, "message": exc.message})


@router.get("", response_model=APIResponse[SetupStateResponse])
async def get_setup(course: Course = Depends(get_owned_course)):
    return APIResponse(success=True, data=_state(course))


@router.patch("", response_model=APIResponse[SetupStateResponse])
async def patch_setup(
    body: SetupStepUpdate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
):
    try:
        await set_step_flag(db, course, body.step, body.done)
    except SetupGateError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message})
    return APIResponse(success=True, data=_state(course))


@router.post("/analyze", response_model=APIResponse[None], status_code=202)
async def analyze(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
):
    db.add(Task(
        task_type="analyze_course_setup",
        payload={"course_id": str(course.id)}, status="pending",
    ))
    await db.commit()
    return APIResponse(success=True, data=None)


@router.get("/analysis", response_model=APIResponse[SetupAnalysisResponse])
async def get_analysis(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
):
    # Latest completed analyze task for this course. Task.payload is JSON — use
    # the ->> operator (CLAUDE.md convention), never .astext.
    row = (
        await db.execute(
            select(Task).where(
                Task.task_type == "analyze_course_setup",
                Task.payload.op("->>")("course_id") == str(course.id),
                Task.status == "completed",
            ).order_by(desc(Task.completed_at)).limit(1)
        )
    ).scalar_one_or_none()
    analysis = (row.payload or {}).get("result") if row else None
    return APIResponse(
        success=True,
        data=SetupAnalysisResponse(ready=analysis is not None, analysis=analysis),
    )


@router.post("/publish", response_model=APIResponse[SetupStateResponse])
async def publish(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
):
    try:
        await publish_setup(db, course)
    except SetupGateError as exc:
        raise _gate_http(exc)
    return APIResponse(success=True, data=_state(course))


@router.post("/reopen", response_model=APIResponse[SetupStateResponse])
async def reopen(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
):
    await reopen_setup(db, course)
    return APIResponse(success=True, data=_state(course))
```

Register in `backend/app/api/__init__.py`: `from app.api.setup import router as setup_router` + `api_router.include_router(setup_router)`.

- [ ] **Step 5: PASS run** — `.\.venv\Scripts\python.exe -m pytest tests/test_setup_api.py -v`.

- [ ] **Step 6: Commit** — `git commit -am "feat(setup): setup.py router (state, analyze/analysis, publish/reopen gates)"`

---

### Task 9: `checkpoints.py` router — teacher draft/generate/CRUD (DRAFT-only state tests)

**Files:**
- Create: `backend/app/api/checkpoints.py`, `backend/app/schemas/checkpoint.py`
- Modify: `backend/app/api/__init__.py`
- Test: `backend/tests/test_checkpoints_api.py`

P1 endpoints: `POST /courses/{id}/checkpoints/generate` (enqueue), `GET /courses/{id}/checkpoints`, `GET/DELETE /checkpoints/{id}` (soft delete), `PATCH /checkpoints/{id}/cards/{card_id}` (edit prompt / remove+reason — reject removing the `final_comments` card), `POST /checkpoints/{id}/cards` (add review-point card). **No** approve/schedule/publish/close (P3) — a state test confirms those routes do not exist / are rejected.

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_checkpoints_api.py
import pytest


@pytest.mark.asyncio
async def test_generate_enqueues(instructor_client, owned_course, seed_meeting):
    r = await instructor_client.post(
        f"/api/courses/{owned_course.id}/checkpoints/generate",
        json={"meeting_id": str(seed_meeting.id)},
    )
    assert r.status_code == 202


@pytest.mark.asyncio
async def test_cannot_remove_final_card(instructor_client, draft_checkpoint_with_cards):
    cp, final_card = draft_checkpoint_with_cards
    r = await instructor_client.patch(
        f"/api/checkpoints/{cp.id}/cards/{final_card.id}",
        json={"removed": True, "removed_reason": "not_needed"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "FINAL_CARD_FIXED"


@pytest.mark.asyncio
async def test_edit_review_card_prompt(instructor_client, draft_checkpoint_with_cards):
    cp, _ = draft_checkpoint_with_cards
    # fetch a review_point card via GET, then edit its prompt
    detail = (await instructor_client.get(f"/api/checkpoints/{cp.id}")).json()["data"]
    rp = next(c for c in detail["cards"] if c["kind"] == "review_point")
    r = await instructor_client.patch(
        f"/api/checkpoints/{cp.id}/cards/{rp['id']}", json={"prompt": "Edited?"}
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_p1_has_no_publish_route(instructor_client, draft_checkpoint_with_cards):
    cp, _ = draft_checkpoint_with_cards
    r = await instructor_client.post(f"/api/checkpoints/{cp.id}/publish")
    assert r.status_code == 404  # publish is P3
```

- [ ] **Step 2: FAIL run** — `.\.venv\Scripts\python.exe -m pytest tests/test_checkpoints_api.py -v`.

- [ ] **Step 3: Implement schemas** (`schemas/checkpoint.py`): `CheckpointGenerateRequest(meeting_id: uuid.UUID | None, review_card_count: int | None)`, `CheckpointCardResponse`, `CheckpointResponse(cards: list[...])`, `CheckpointCardUpdate(prompt: str | None, removed: bool | None, removed_reason: Literal[...] | None, removed_note: str | None)`, `CheckpointCardCreate(prompt, position)`.

- [ ] **Step 4: Implement `api/checkpoints.py`** — two routers or one with mixed prefixes. Ownership: resolve the checkpoint's course, reuse `get_owned_course` semantics (load checkpoint → load course → assert `course.instructor_id == user.id`, else 404). Key rules:
  - `generate`: enqueue a `generate_checkpoints` Task; 202.
  - `PATCH cards`: if the target card `kind == 'final_comments'` and the body sets `removed=True`, raise `409 {"code": "FINAL_CARD_FIXED"}`. Otherwise apply `exclude_unset` fields. Editing is only allowed while `checkpoint.status in ('draft','teacher_editing')` (Decision 3) — else `409 {"code": "REVIEW_REQUIRED"}` (matches spec §3.4 error taxonomy; full transitions land P3).
  - Do NOT add approve/schedule/publish/close routes.

  ```python
  # ownership helper (module-level)
  async def _owned_checkpoint(checkpoint_id, user, db) -> Checkpoint:
      cp = await db.get(Checkpoint, checkpoint_id)
      if cp is None or cp.deleted_at is not None:
          raise HTTPException(404, "Checkpoint not found")
      course = await db.get(Course, cp.course_id)
      if course is None or course.instructor_id != user.id:
          raise HTTPException(404, "Checkpoint not found")
      return cp
  ```

Register the router(s) in `backend/app/api/__init__.py`.

- [ ] **Step 5: PASS run** — `.\.venv\Scripts\python.exe -m pytest tests/test_checkpoints_api.py -v`.

- [ ] **Step 6: Commit** — `git commit -am "feat(checkpoint): checkpoints.py router (generate + draft card CRUD, no publish in P1)"`

---

### Task 10: `scores.py` router — score-category CRUD (score-policy step)

**Files:**
- Create: `backend/app/api/scores.py`, `backend/app/schemas/score.py`
- Modify: `backend/app/api/__init__.py`
- Test: `backend/tests/test_score_categories_api.py`

P1 subset of the spec `scores.py`: `GET/POST/PATCH/DELETE /courses/{id}/score-categories`. (Grade export + student scores are P5.)

- [ ] **Step 1: Failing test** — a freshly created course already returns the 2 seeded pilot categories (Task 4); POST adds a third; PATCH renames one; DELETE (soft) removes; non-owner 404.

- [ ] **Step 2: FAIL run** — `.\.venv\Scripts\python.exe -m pytest tests/test_score_categories_api.py -v`.

- [ ] **Step 3: Implement** — `schemas/score.py` (`ScoreCategoryCreate(name, weight?, points_pool?, sort?)`, `ScoreCategoryUpdate(all optional)`, `ScoreCategoryResponse`); `api/scores.py` CRUD guarded by `get_owned_course`, ordered by `sort`, soft-delete on DELETE. Register the router.

- [ ] **Step 4: PASS run** — `.\.venv\Scripts\python.exe -m pytest tests/test_score_categories_api.py -v`.

- [ ] **Step 5: Backend regression + review** — run the FULL suite `.\.venv\Scripts\python.exe -m pytest -q` (confirm only the KNOWN pre-existing failures from the P0 handoff remain; zero new). Run `/code-review` (or code-reviewer agent) over the Task 1–10 diff; fix CRITICAL/HIGH.

- [ ] **Step 6: Commit** — `git commit -am "feat(setup): scores.py score-category CRUD (score-policy step)"`

---

### Task 11: `StepWizard` pattern component + `use-setup` hook

**Files:**
- Create: `frontend/src/components/patterns/step-wizard.tsx`
- Modify: `frontend/src/components/patterns/index.ts` (export)
- Create: `frontend/src/hooks/use-setup.ts`
- Create: `frontend/src/components/patterns/step-wizard.test.tsx`
- Modify: `frontend/messages/en.json` (add `patterns.wizard.*` + `teacher.setup.*` skeleton keys)

Design rules (Global Rules): tokens only (`var(--color-*)`, `--space-*`, `--radius-*`); one visual treatment per step status (`upcoming | current | complete | blocked`); reuse `toneStyles` from `patterns/tones.ts`. Invoke `frontend-design:frontend-design` + `ui-ux-pro-max:ui-ux-pro-max` before styling. Pull Figma T014/T026 (`1372:36` / `1372:60`) for the stepper + review-checklist layout.

- [ ] **Step 1: Vitest first** (logic: step status derivation + guarded navigation)

```tsx
// frontend/src/components/patterns/step-wizard.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StepWizard, type WizardStep } from "./step-wizard";

const steps: WizardStep[] = [
  { id: "basics", label: "Basics", complete: true },
  { id: "syllabus", label: "Syllabus", complete: false },
  { id: "publish", label: "Publish", complete: false },
];

describe("StepWizard", () => {
  it("marks completed steps and highlights the current one", () => {
    render(<StepWizard steps={steps} currentId="syllabus">body</StepWizard>);
    expect(screen.getByRole("listitem", { name: /Basics/ })).toHaveAttribute(
      "data-status", "complete",
    );
    expect(screen.getByRole("listitem", { name: /Syllabus/ })).toHaveAttribute(
      "data-status", "current",
    );
    expect(screen.getByText("body")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: FAIL run** — from `frontend/`: `npx vitest run src/components/patterns/step-wizard.test.tsx`.

- [ ] **Step 3: Implement `step-wizard.tsx`** — props `{ steps: WizardStep[]; currentId: string; onStepSelect?: (id) => void; children: ReactNode }`; `WizardStep = { id; label; complete: boolean; blocked?: boolean }`. Derive `data-status` (`complete` if `step.complete`, `current` if `id === currentId`, `blocked` if `step.blocked`, else `upcoming`). Render an ordered `<ol>` rail (each `<li role="listitem" aria-label={label} data-status=...>`) + a `<section>` for `children`. Follow the existing pattern components' Tailwind-token idiom (see `state-banner.tsx`). Keyboard: steps are `<button>`s when `onStepSelect` given; only `complete` or `current` steps are focusable/clickable (can't jump ahead). Export from `index.ts`.

- [ ] **Step 4: `use-setup.ts`** — TanStack hooks over the Task 8/9/10 endpoints, following the `use-authed-query.ts` + `use-syllabus.ts` patterns exactly:
  - `useSetupState(courseId)` → `useAuthedQuery<SetupState>({ queryKey: ["setup", courseId], path: \`/courses/${courseId}/setup\` })`.
  - `useSetStep(courseId)` → mutation PATCH `/courses/${courseId}/setup`, invalidates `["setup", courseId]`.
  - `useAnalyzeSetup`, `useSetupAnalysis`, `usePublishSetup`, `useReopenSetup`, `useGenerateCheckpoints`, `useScoreCategories`.
  Map a `409 {code}` gate error to a typed union the UI switches on (`SETUP_INCOMPLETE`, `SETUP_NOT_OPEN`, `FINAL_CARD_FIXED`, `REVIEW_REQUIRED`).

- [ ] **Step 5: PASS run + typecheck** — `npx vitest run src/components/patterns/step-wizard.test.tsx` green; `npx tsc --noEmit` clean.

- [ ] **Step 6: Commit** — `git commit -am "feat(ui): StepWizard pattern component + use-setup hooks"`

---

### Task 12: Wizard route scaffold + T014 new-course-start + T015 course-basics

**Files:**
- Create: `frontend/src/app/(app)/teacher/courses/new/page.tsx` (T014)
- Create: `frontend/src/app/(app)/teacher/courses/[id]/setup/page.tsx` (wizard shell)
- Create: `frontend/src/app/(app)/teacher/courses/[id]/setup/setup-wizard.tsx` (client orchestrator)
- Create: `frontend/src/components/setup/step-basics.tsx`
- Modify: `frontend/messages/en.json`
- Figma: `get_design_context` for T014 (`1372:36`), T015 (`1372:38`).

- [ ] **Step 1** — T014 new-course-start (`/teacher/courses/new`): `PageHeader` + a create-course form (name, code, language, semester) using the existing `useCreateCourse` mutation (grep `use-courses.ts`); on success `router.push(\`/teacher/courses/${id}/setup\`)`. Tokens only; keys under `teacher.setup.newCourse.*`.

- [ ] **Step 2** — Wizard shell (`setup/page.tsx`): server component that renders the client `SetupWizard` with `courseId` from `params`. Read `node_modules/next/dist/docs/` for the Next.js 16 `params` handling (it differs from training data — `params` is async).

- [ ] **Step 3** — `setup-wizard.tsx`: `"use client"`; reads `useSetupState(courseId)`; builds the `WizardStep[]` from `steps` + `SETUP_STEP_KEYS` order; renders `<StepWizard>` with the active step's component; a `?step=` query param (or local state) selects the current step; each step calls `useSetStep` to flip its flag when its "mark done / continue" action fires. Waiting/blocked states use `StateBanner`.

- [ ] **Step 4** — `step-basics.tsx` (T015): edit name/code/language/semester via `useUpdateCourse`; "Save & continue" flips the `basics` flag. Reuse existing form primitives from `components/ui/`.

- [ ] **Step 5: Verify** — `npx tsc --noEmit && npm run lint` clean; `npm run dev`, create a course, land on the wizard, complete Basics → flag persists (network tab shows PATCH).

- [ ] **Step 6: Commit** — `git commit -am "feat(setup): course-setup wizard shell + new-course-start + basics steps"`

---

### Task 13: T016 syllabus-upload + T017 core-materials-upload steps

**Files:**
- Create: `frontend/src/components/setup/step-syllabus.tsx`, `frontend/src/components/setup/step-materials.tsx`
- Modify: `frontend/messages/en.json`
- Figma: T016 (`1372:40`), T017 (`1372:42`).

- [ ] **Step 1** — `step-syllabus.tsx` reuses the EXISTING syllabus upload + import flow (`components/documents/` + `use-syllabus.ts` `useTriggerSyllabusImport`; grep for the existing upload component). Show import status (pending/parsed/applied) from `GET /courses/{id}/syllabus/imports`; "continue" flips `syllabus` when an import reaches `applied` (or teacher explicitly skips — record a skipped flag).

- [ ] **Step 2** — `step-materials.tsx` reuses the EXISTING documents upload pipeline (`use-documents.ts`, `components/documents/`) with a progress list (T017 is "upload-progress"). Poll document status; "continue" flips `materials` when ≥1 document is `ready` (or explicit skip). Use `EmptyState variant="waiting"` while processing.

- [ ] **Step 3: Verify** — `npx tsc --noEmit && npm run lint`; manual: upload a syllabus + a PDF in the wizard; flags flip.

- [ ] **Step 4: Commit** — `git commit -am "feat(setup): syllabus-upload + core-materials-upload wizard steps (reuse existing pipelines)"`

---

### Task 14: T018 schedule-and-venue + T020 ILO-map-builder steps

**Files:**
- Create: `frontend/src/components/setup/step-schedule.tsx`, `frontend/src/components/setup/step-ilo.tsx`
- Create/Modify: `frontend/src/hooks/use-meetings.ts`, `frontend/src/hooks/use-objectives.ts` (add if absent, following `use-syllabus.ts`)
- Figma: T018 (`1372:44`), T020 (`1372:48`).

- [ ] **Step 1** — `step-schedule.tsx` (T018): a table/list of meetings via `GET/POST/PUT /courses/{id}/meetings` (create meeting with `meeting_index` as session no, `location` as venue, `scheduled_at`, `topic_summary`) + the `PATCH /meetings/{id}/release-state` control (Task 7). "Continue" flips `schedule` when ≥1 meeting exists.

- [ ] **Step 2** — `step-ilo.tsx` (T020): CRUD ILOs via `/courses/{id}/objectives` (existing router). Show concept links where present (read-only in P1 — `GET /concept-tags` filtered to `target_kind='objective'`). "Continue" flips `ilo_map` when ≥1 objective exists.

- [ ] **Step 3: Verify** — `npx tsc --noEmit && npm run lint`; manual: add a session + venue + ILO.

- [ ] **Step 4: Commit** — `git commit -am "feat(setup): schedule-and-venue + ILO-map-builder wizard steps"`

---

### Task 15: T019 analyzer-review + T021 session-generation-review + T022 checkpoint-generation-review

**Files:**
- Create: `frontend/src/components/setup/step-analyzer.tsx`, `frontend/src/components/setup/step-sessions.tsx`, `frontend/src/components/setup/step-checkpoints.tsx`
- Figma: T019 (`1372:46`), T021 (`1372:50`), T022 (`1372:52`).

- [ ] **Step 1** — `step-analyzer.tsx` (T019): "Run analysis" → `useAnalyzeSetup` (POST /analyze) → poll `useSetupAnalysis` (GET /analysis). Render the course map counts + a `StateBanner tone="warning"` listing `missing_sources` when `has_missing_sources`. "Continue" flips `analyzer_review` (allowed even with warnings — the hard block is at publish). While the task runs, `EmptyState variant="waiting"`.

- [ ] **Step 2** — `step-sessions.tsx` (T021): review the meetings/sessions produced (reads `/meetings`); teacher can edit `topic_summary` / release_state inline. This is a review gate over Task 14's data — "Continue" is informational (no separate flag; folds under `schedule`). If the brief later needs its own flag, add `sessions` to `SETUP_STEP_KEYS` — NOTE: keep `SETUP_STEP_KEYS` authoritative; do not invent UI-only flags.

- [ ] **Step 3** — `step-checkpoints.tsx` (T022): "Generate checkpoints" → `useGenerateCheckpoints` (POST `/courses/{id}/checkpoints/generate` per meeting) → list drafts via `GET /courses/{id}/checkpoints`; expand a checkpoint to show its cards (`GET /checkpoints/{id}`), edit a review-point prompt or remove with reason (`PATCH .../cards/{id}`), respecting the `FINAL_CARD_FIXED` 409 (disable remove on the final card). All drafts show a `ReviewStateChip`-style "Draft" badge (reuse `StateBanner`/tone `info`; the full `ReviewStateChip` pattern is P3). "Continue" flips `checkpoints` when ≥1 draft exists.

- [ ] **Step 4: Verify** — `npx tsc --noEmit && npm run lint`; manual: run analysis (see missing-source warning on an empty course), generate a checkpoint, edit a card, confirm final card can't be removed.

- [ ] **Step 5: Commit** — `git commit -am "feat(setup): analyzer-review + session-review + checkpoint-generation-review wizard steps"`

---

### Task 16: T024 score-policy + T025 class-code + T023 memory-import stub

**Files:**
- Create: `frontend/src/components/setup/step-score-policy.tsx`, `frontend/src/components/setup/step-class-code.tsx`, `frontend/src/components/setup/step-memory-import.tsx`
- Modify: `backend/app/api/courses.py` (add `POST /courses/{id}/enroll-code/rotate` + `/deactivate`)
- Test: `backend/tests/test_enroll_code_controls.py`
- Figma: T024 (`1372:56`), T025 (`1372:58`), T023 (`1372:54`).

- [ ] **Step 1: Backend failing test** — instructor can rotate the enroll code (returns a new code, old code no longer resolves) and deactivate it (`enroll_code_active=False`; `enroll-by-code` then refuses — but that refusal wiring is P2; here just assert the column flips). Non-owner 404.

- [ ] **Step 2: FAIL run** — `.\.venv\Scripts\python.exe -m pytest tests/test_enroll_code_controls.py -v`.

- [ ] **Step 3: Backend impl** — add to `api/courses.py`:
  - `POST /courses/{id}/enroll-code/rotate` (owner-guarded) → generate a fresh unique `enroll_code` (reuse `_generate_enroll_code` + the collision-retry loop), set `enroll_code_active=True`, return the new code.
  - `POST /courses/{id}/enroll-code/deactivate` → set `enroll_code_active=False`.

- [ ] **Step 4: PASS run** — `.\.venv\Scripts\python.exe -m pytest tests/test_enroll_code_controls.py -v`.

- [ ] **Step 5: Frontend** —
  - `step-score-policy.tsx` (T024): list/add/edit/remove score categories via `useScoreCategories` (Task 10); pre-populated with the seeded pilot defaults. "Continue" flips `score_policy`.
  - `step-class-code.tsx` (T025): reveal (masked by default) / rotate / deactivate the enroll code. "Continue" flips `class_code`.
  - `step-memory-import.tsx` (T023): **STUB** behind a flag — render an `EmptyState` explaining previous-term memory import arrives in P7, gated on `process.env.NEXT_PUBLIC_MEMORY_IMPORT === "enabled"` (hidden otherwise; the step is skippable and does NOT block publish). No `SETUP_STEP_KEYS` flag for it.

- [ ] **Step 6: Verify + Commit** — `npx tsc --noEmit && npm run lint`; `git commit -am "feat(setup): score-policy + class-code steps + enroll-code controls + memory-import stub"`

---

### Task 17: T026 review-checklist + T027 publish-success + T028 missing-source-error + happy-path spec + close-out

**Files:**
- Create: `frontend/src/components/setup/step-review.tsx`, `frontend/src/components/setup/setup-publish-success.tsx`, `frontend/src/components/setup/setup-missing-source-error.tsx`
- Create: `frontend/e2e/setup-wizard.spec.ts` (or a vitest orchestration test if e2e infra is unavailable — see P0 handoff limitation)
- Modify: `docs/superpowers/plans/2026-07-07-meli-cle-roadmap.md` (tracker + handoff), `docs/superpowers/RESUME.md`
- Figma: T026 (`1372:60`), T027 (`1372:62`), T028 (`1372:64`).

- [ ] **Step 1** — `step-review.tsx` (T026): render the full checklist from `useSetupState` (`steps` + `missing`); each incomplete step links back to its wizard step. "Publish course" calls `usePublishSetup`; on `409 SETUP_INCOMPLETE` show a `StateBanner tone="blocked"` listing `missing`. On `has_missing_sources` from the latest analysis, deep-link to `setup-missing-source-error`.

- [ ] **Step 2** — `setup-publish-success.tsx` (T027): success state after publish (`setup_status==='published'`, `context_status==='approved'`) with next actions (share class code, view course). `StateBanner tone="success"`.

- [ ] **Step 3** — `setup-missing-source-error.tsx` (T028): the blocked/missing-source designed state — lists each `missing_sources[]` entry with a jump-back link to the step that resolves it (materials / ILO / schedule). `StateBanner tone="warning"` + `EmptyState`.

- [ ] **Step 4: Happy-path test** — `setup-wizard.spec.ts`: sign in as instructor → create course → walk every step marking flags → publish → assert the success screen. If backend/session e2e infra is unavailable (per the P0 handoff `role-routing` limitation), instead add a vitest that drives `SetupWizard` against a mocked `use-setup` and asserts: incomplete publish shows the blocked banner; all-complete publish shows success. Document which path you took.

- [ ] **Step 5: Full regression** — backend `.\.venv\Scripts\python.exe -m pytest -q` (only known pre-existing failures remain); frontend `npx tsc --noEmit`, `npx vitest run`, `npm run build`. Run `/code-review` over the full P1 diff; fix CRITICAL/HIGH. Run `frontend-design`/`design-review` polish pass over the wizard screens.

- [ ] **Step 6: Close out** — check P1 in the roadmap Phase Tracker; append a Handoff Log entry (commits, gotchas, "next: write P2 plan — student entry & enrollment; reuse `assert_course_open` gate + `join_mode`/`enroll_code_active`"); update `RESUME.md`. `git add -f docs/superpowers/... && git commit -m "docs(roadmap): P1 complete — handoff for P2"`.

---

## Self-review checklist (confirm before marking P1 done)

**Spec §4.8 (setup gate):**
- [x] `courses.setup_status (draft/in_review/published)` + `setup_checklist` JSONB with the §4.8 step flags (basics, syllabus, materials, schedule, analyzer_review, ilo_map, checkpoints, score_policy, class_code) — Task 1 + Task 4 `SETUP_STEP_KEYS`.
- [x] `join_mode` + `enroll_code_active` columns — Task 1; enroll-code controls — Task 16.
- [x] Course-open gate is server-side, typed (`SETUP_NOT_OPEN` / `SETUP_INCOMPLETE`), and reuses `context_status` as the single authority (Decision 1) — Task 4/8; `assert_course_open` exported for P2.
- [x] Reopen does not lock students out (`context_status` stays `approved`) — Task 4 test `test_reopen_keeps_students_in`.
- [x] Missing-source detection + designed error state (T028) — Task 5 job + Task 17 UI.

**Spec §4.1 (sessions):**
- [x] `course_meetings` extended with `release_state` (distinct axis, Decision 2) + `topic_summary`; `session_no`→`meeting_index`, `venue`→`location` reused — Task 2; release transition endpoint — Task 7; schedule step — Task 14.

**Spec §4.2 (checkpoints/cards — DRAFT only in P1):**
- [x] `checkpoints` (full status enum, written `draft`-only) + `checkpoint_cards` (fixed single `final_comments` card via partial unique index) — Task 3.
- [x] `generate_checkpoints` job: grounded (`retriever` + `syllabus_grounding`), cards concept-tagged via existing inheritance tagger, `target_kind='checkpoint_card'` — Task 3 (widen CHECK) + Task 6.
- [x] Teacher draft/generate/card-edit/remove endpoints; NO publish/QR/responses (P3) — Task 9 (`test_p1_has_no_publish_route`, `FINAL_CARD_FIXED`, `REVIEW_REQUIRED`).

**Spec §4.5 (score categories):**
- [x] `score_categories` table seeded from pilot config at course creation — Task 3 model + Task 4 seeding; CRUD — Task 10; score-policy step — Task 16.

**Cross-cutting (Global Rules):**
- [x] TDD: failing test first for every backend behavior (Tasks 1–10, 16). New task types added to `worker.py` dispatch (Tasks 5, 6).
- [x] `APIResponse[T]` envelope; UUID PKs + Timestamp/SoftDelete mixins; Postgres CHECK enums validated in the service layer; `Task.payload` queried with `.op("->>")` (Task 8 analysis lookup).
- [x] No new student-owned row tables in P1 → RLS deferred to P3 (`checkpoint_responses`) — documented in Decision 3.
- [x] Frontend: `StepWizard` pattern born + exported; steps use `patterns/*` + `toneStyles` tokens + Figma nodes T014–T028; vitest where logic exists (Task 11); i18n keys under `teacher.setup.*` / `patterns.wizard.*`.
- [x] Memory-import (T023) is a flagged stub; real impl is P7 (spec §4.10 / roadmap P7).

**Open reconciliation flags for the executor:** verify `hybrid_retrieve` signature + chunk `.content` field (Task 6 Step 3 note); fix the tag-task `target_id` to the card id (Task 6 note); confirm Next.js 16 async `params` handling before the wizard route (Task 12 Step 2).
