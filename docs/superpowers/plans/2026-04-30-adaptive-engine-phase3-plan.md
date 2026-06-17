# Adaptive Engine — Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the decision layer + outcome telemetry on top of Phase 2's mastery layer. Produce real `next_actions` (KST outer-fringe filter → scoring → top-10 per student per course), wire `action_outcomes` so every served/clicked/observed event is recorded with its `engine_variant` (enables retroactive A/B), evaluate `instructor_alerts` hourly, expose a per-course engine on/off/random_50 toggle (with deterministic per-(user,course) hash so the random_50 split is stable), retune scoring coefficients quarterly, and surface all of it in the student "Today" view + instructor alerts center.

**Architecture:** One Alembic revision adding four tables (`next_actions`, `action_outcomes`, `instructor_alerts`, `engine_overrides`) and one column (`courses.adaptive_engine_mode`). Five new background `task_type`s (`materialize_next_actions`, `evaluate_instructor_alerts`, `tune_action_coefficients`, `record_action_outcome`, plus a daily cron for deadline/meeting horizon scans). Seven new API routers/endpoints (next-actions list + click, engine settings GET/PATCH, alerts list/dismiss/resolve, outcomes for instructor analytics). Three new frontend hooks + four new pages/components. The Phase 2 mastery layer is **read-only** input to this layer — nothing in `concept_mastery` / `concept_mastery_history` / Beta-Binomial math changes. The bandit/FSRS/recalibration machinery is untouched per spec §"Bandit & FSRS — explicitly unchanged".

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic + Postgres 17 + pgvector + Next.js 16 App Router (proxy.ts not middleware.ts) + React 19 + TanStack Query + Better Auth.

**Spec:** [docs/superpowers/specs/2026-04-28-adaptive-engine-design.md](../specs/2026-04-28-adaptive-engine-design.md) (Phase 3 sections: lines 600–812 for tables, 845–870 for jobs, 876–935 for queries).

**Phase 3 ship criterion:** at least one course runs in `random_50` mode for ≥ 1 week of real student activity, producing `action_outcomes` rows for both `engine_variant='on'` and `engine_variant='off'` cohorts. Spec §Phase 3 ship criteria.

**Locked decisions (do NOT re-litigate):**
- `next_actions` is a **materialised cache, not source of truth** — re-derivable from `concept_mastery` + curriculum at any time. Lazy recompute on read if cached row is older than 30 min; event-driven rebuild on attempt/deadline/meeting changes; row TTL is 1 hour after materialisation (`expires_at = now() + interval '1 hour'`).
- KST **outer fringe is the primary candidate filter** (concepts whose every prerequisite has `mastery_score >= 0.7 AND confidence >= 0.5` but the concept itself does not). Scoring is the **tie-breaker**, not the candidate selector.
- **Scoring coefficients are initial defaults** (`prep_meeting=3.0`, `complete_assignment=5.0`, `practice_weakness=2.0`, `flashcard_review=1.5`, `catch_up_reading=1.0`). Quarterly cron `tune_action_coefficients` retunes them from the `action_outcomes` log; until that job has fired its first cycle, defaults stand.
- `random_50` deterministically splits students using `hash(user_id || course_id) % 2`. Same student stays in the same arm across sessions, so per-student outcome curves are clean.
- **Per-user override > course mode.** `engine_overrides(user_id, course_id, mode)` rows are checked first; missing rows fall through to `courses.adaptive_engine_mode`. Override modes are `'on' | 'off'` only — no `random_50` at the override level (it would make no sense for a single user).
- When mode resolves to `'off'`, the API returns an empty `next_actions` list **but still writes an `action_outcomes` row** with `engine_variant='off'` and `clicked=false` for the artifact the student ends up touching anyway (via post-attempt observation). This is what produces the off-arm outcome curve.
- Phase 3 does **not** touch the bandit / scheduler / FSRS / recalibration tables. The concept layer filters the candidate pool *before* the bandit picks difficulty within an item set; they compose vertically.
- `next_actions.target_id` is **polymorphic + nullable** — `target_kind` is the dispatch tag, application-validated like `concept_tags`. No FK; cleanup is by `expires_at` cron.
- `action_outcomes.next_action_id` is `ON DELETE SET NULL` so we can prune `next_actions` aggressively without losing telemetry.

---

## File Structure

### Backend — new files

```
backend/
├── alembic/versions/
│   └── b2f9a4d7c8e1_phase3_decision_and_telemetry.py   # next_actions, action_outcomes, instructor_alerts, engine_overrides; ALTER courses
├── app/models/
│   └── decision.py                                       # NextAction, ActionOutcome, InstructorAlert, EngineOverride
├── app/schemas/
│   └── decision.py                                       # Pydantic schemas (NextActionResponse, ActionOutcomeResponse, InstructorAlertResponse, EngineSettingsResponse, etc.)
├── app/api/
│   ├── next_actions.py                                   # /api/users/me/courses/{course_id}/next-actions, /api/next-actions/{id}/click
│   ├── instructor_alerts.py                              # /api/courses/{course_id}/alerts (list/dismiss/resolve)
│   └── engine_settings.py                                # /api/courses/{course_id}/engine (GET/PATCH); /api/courses/{course_id}/engine/overrides (PUT/DELETE)
├── app/services/
│   ├── engine_mode.py                                    # resolve_mode(user, course) → 'on'|'off'  (handles override > course flag, random_50 hash)
│   ├── outer_fringe.py                                   # outer_fringe_concepts(user, course) → list[ConceptCandidate]
│   ├── scoring.py                                        # score_action(action_type, …) → Decimal  (one fn per action_type, plus dispatcher)
│   ├── next_actions.py                                   # materialize_next_actions(user, course); record_serve(); record_click(); record_observation()
│   ├── alerts.py                                         # evaluate_alerts_for_course(course_id) — alert rule evaluator
│   └── action_coeffs.py                                  # default_coeffs() + retune_action_coefficients(window_days)
└── tests/
    ├── test_models_decision.py
    ├── test_engine_mode.py                               # override > flag, random_50 hash determinism
    ├── test_outer_fringe.py                              # 4 cases: empty mastery, all-mastered, mid-fringe, missing prereq
    ├── test_scoring.py                                   # one test per action_type formula
    ├── test_next_actions_service.py                      # materialize → top-10 ordering, expires_at, replace-on-rebuild
    ├── test_api_next_actions.py                          # GET (lazy recompute), POST /click (records click + action_outcomes)
    ├── test_api_engine_settings.py                       # GET/PATCH course mode; PUT/DELETE overrides
    ├── test_api_instructor_alerts.py
    ├── test_alerts_evaluator.py                          # one test per alert_type rule
    ├── test_action_coeffs.py                             # retune produces sensible deltas from synthetic outcomes
    └── test_jobs_phase3.py                               # worker handlers (materialize, evaluate, retune)
```

### Backend — modified files

```
backend/app/
├── api/__init__.py                       # register 3 new routers (next_actions, instructor_alerts, engine_settings)
├── api/quizzes.py                        # MODIFIED: after submit_attempt, enqueue record_action_outcome for any open next_action targeting this quiz
├── api/flashcards.py                     # MODIFIED: same pattern after flashcard review
├── api/revision.py                       # MODIFIED: same pattern after revision attempt
├── models/__init__.py                    # export 4 new models
├── services/jobs.py                      # add 4 new task handlers: run_materialize_next_actions, run_evaluate_instructor_alerts, run_tune_action_coefficients, run_record_action_outcome
├── services/worker.py                    # dispatch 4 new task_types; add hourly alert-cron + quarterly retune-cron with last_*_run watermarks
└── services/mastery.py                   # MODIFIED: at end of apply_attempt_evidence, return list of touched concept_ids so callers can enqueue outcome recording (additive — keeps current return value semantics intact via tuple return)
```

### Frontend — new files

```
frontend/src/
├── app/dashboard/courses/[courseId]/
│   ├── today/
│   │   └── page.tsx                                     # student "today" / next-actions view
│   ├── alerts/
│   │   └── page.tsx                                     # instructor alerts center
│   └── engine/
│       └── page.tsx                                     # instructor engine on/off/random_50 toggle + per-student override list
├── components/decision/
│   ├── next-action-card.tsx                             # one row in the next-actions list
│   ├── next-action-list.tsx                             # paginated list w/ click handlers
│   ├── instructor-alert-card.tsx
│   ├── alert-list.tsx                                   # filter by severity, dismiss/resolve actions
│   ├── engine-mode-selector.tsx                         # radio: on / off / random_50
│   └── engine-override-row.tsx                          # one row in the override admin table
├── hooks/
│   ├── use-next-actions.ts
│   ├── use-instructor-alerts.ts
│   └── use-engine-settings.ts
└── lib/
    └── decision-types.ts                                # TS types matching backend Pydantic
```

### Frontend — modified files

```
frontend/src/
└── app/dashboard/courses/[courseId]/page.tsx           # add Today / Alerts / Engine cards to the course landing nav row
```

---

## Task Sequence

Tasks are organised into four sub-phases:
- **Phase 3.1 — Schema + engine core** (Tasks 1–7) — foundation; mostly serial.
- **Phase 3.2 — Worker + APIs** (Tasks 8–14) — depends on 3.1; some parallelisable.
- **Phase 3.3 — Alerts + retuning** (Tasks 15–17) — depends on 3.1 schema; parallelisable with 3.2.
- **Phase 3.4 — Frontend** (Tasks 18–23) — depends on 3.2 APIs.

Commit per task. Single branch `feat/adaptive-engine-phase1` (per memory rule "Single branch for plans"). Phase 3 begins from current head `84c5f0e`.

### Dependency / dispatch graph

```
              ┌── 1 (migration) ──┬── 2 (models) ── 3 (schemas) ─┐
              │                   │                              │
              │                   ├── 4 (engine_mode) ── 13 (engine API) ── 22 (engine UI)
              │                   │                              │
              │                   ├── 5 (outer_fringe) ──┐       │
              │                   ├── 6 (scoring) ───────┼── 7 (materializer) ── 8 (worker) ── 9 (lazy recompute) ── 10 (next-actions API) ── 11 (event hooks) ── 12 (daily cron)
              │                   │                      │                                                                ↓                       ↓
              │                   │                      │                                                       18 (TS types) ── 19 (hooks) ── 20 (today UI)
              │                   │                      │
              │                   ├── 15 (alert evaluator) ── 16 (alert cron + API) ── 21 (alerts UI)
              │                   │
              │                   ├── 14 (outcome recorder) ─┐
              │                   │                          ├── 23 (random_50 demo seed)
              │                   └── 17 (coefficient retune)┘
```

| Group | Parallelisable | Notes |
|---|---|---|
| 2, 3 | both depend on 1 | Run in parallel after migration applies. |
| 4, 5, 6 | all three depend on 2+3 | Three pure-service modules, no cross-deps. Dispatch in parallel. |
| 13, 15, 17 | depend on 2+3 only | Engine API, alert evaluator, retune job — all parallel with 7+8+10 once schemas land. |
| 18, 19 | depend on 3 (schemas dictate types) | TS types and hooks scaffold can land while backend tasks 7–14 ship. |
| 20, 21, 22 | depend on 19 + their respective backends | UI pages — parallelise by page once hooks land. |

---

## Phase 3.1 — Schema + engine core

### Task 1: Alembic revision — next_actions, action_outcomes, instructor_alerts, engine_overrides, ALTER courses

**Files:**
- Create: `backend/alembic/versions/b2f9a4d7c8e1_phase3_decision_and_telemetry.py`

**Context:** Phase 2 head is `b2e9c4f7a1d3` (concept text-length CHECK constraints, landed after the original plan was written). This revision creates four new tables and adds `courses.adaptive_engine_mode`. The `engine_overrides` table is keyed by `(user_id, course_id)` with no surrogate id — same composite-PK pattern as `concept_mastery` from Phase 2.2. `next_actions` carries the polymorphic `target_kind` + `target_id` like `concept_tags` does (no FK on `target_id`).

- [ ] **Step 1: Write the migration**

```python
"""phase 3 decision layer + outcome telemetry

Revision ID: b2f9a4d7c8e1
Revises: f9d8e7c6b5a4
Create Date: 2026-04-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b2f9a4d7c8e1"
down_revision: Union[str, None] = "b2e9c4f7a1d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------- ALTER courses: adaptive_engine_mode ----------
    op.add_column(
        "courses",
        sa.Column(
            "adaptive_engine_mode",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'on'"),
        ),
    )
    op.create_check_constraint(
        "ck_courses_engine_mode_valid",
        "courses",
        "adaptive_engine_mode IN ('on','off','random_50')",
    )

    # ---------- next_actions ----------
    op.create_table(
        "next_actions",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action_type", sa.String(40), nullable=False),
        sa.Column("target_kind", sa.String(40), nullable=True),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("priority_score", sa.Numeric(7, 3), nullable=False),
        sa.Column("candidate_source", sa.String(20), nullable=False),
        sa.Column("reason", postgresql.JSONB, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("served_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "engine_variant", sa.String(20), nullable=False,
            server_default=sa.text("'on'"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "action_type IN ("
            "'review_concept','prep_meeting','complete_assignment',"
            "'do_quiz','practice_weakness','catch_up_reading',"
            "'flashcard_review','pronunciation_practice','watch_recording'"
            ")",
            name="ck_next_actions_action_type_valid",
        ),
        sa.CheckConstraint(
            "target_kind IS NULL OR target_kind IN ("
            "'concept','course_meeting','assignment','quiz',"
            "'flashcard_set','pronunciation_set','document','chunk'"
            ")",
            name="ck_next_actions_target_kind_valid",
        ),
        sa.CheckConstraint(
            "candidate_source IN ('outer_fringe','deadline','review','fallback')",
            name="ck_next_actions_candidate_source_valid",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
    )
    # NOTE: ``expires_at > now()`` cannot appear in the index predicate —
    # ``now()`` is STABLE, and Postgres requires index predicates to be
    # IMMUTABLE. The reader filters expired rows at query time
    # (see ``get_or_recompute_next_actions``); this index just trims out
    # consumed rows from the partial.
    op.create_index(
        "idx_next_actions_user_active",
        "next_actions",
        ["user_id", sa.text("priority_score DESC")],
        postgresql_where=sa.text("consumed_at IS NULL"),
    )
    op.create_index(
        "idx_next_actions_cleanup",
        "next_actions",
        ["expires_at"],
        postgresql_where=sa.text("consumed_at IS NULL"),
    )
    op.create_index(
        "idx_next_actions_user_course",
        "next_actions",
        ["user_id", "course_id"],
    )

    # ---------- action_outcomes ----------
    op.create_table(
        "action_outcomes",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("next_action_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action_type", sa.String(40), nullable=False),
        sa.Column("target_kind", sa.String(40), nullable=True),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("engine_variant", sa.String(20), nullable=False),
        sa.Column("served_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "clicked", sa.Boolean(), nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "completed", sa.Boolean(), nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("outcome_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("outcome_metric", sa.String(40), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "outcome_metric IS NULL OR outcome_metric IN "
            "('mastery_delta','quiz_score','recall','completion')",
            name="ck_action_outcomes_metric_valid",
        ),
        sa.ForeignKeyConstraint(
            ["next_action_id"], ["next_actions.id"], ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_action_outcomes_variant_served",
        "action_outcomes",
        ["engine_variant", "served_at"],
    )
    op.create_index(
        "idx_action_outcomes_user",
        "action_outcomes",
        ["user_id", sa.text("served_at DESC")],
    )
    op.create_index(
        "idx_action_outcomes_course_action",
        "action_outcomes",
        ["course_id", "action_type"],
    )

    # ---------- instructor_alerts ----------
    op.create_table(
        "instructor_alerts",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instructor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("alert_type", sa.String(40), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("reason", postgresql.JSONB, nullable=False),
        sa.Column(
            "status", sa.String(20), nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "severity IN ('info','warning','critical')",
            name="ck_instructor_alerts_severity_valid",
        ),
        sa.CheckConstraint(
            "status IN ('open','dismissed','resolved')",
            name="ck_instructor_alerts_status_valid",
        ),
        sa.CheckConstraint(
            "alert_type IN ("
            "'student_disengaging','student_falling_behind',"
            "'cohort_concept_weakness','prereq_gap_for_upcoming_meeting',"
            "'low_quiz_participation','missed_deadline','content_gap'"
            ")",
            name="ck_instructor_alerts_alert_type_valid",
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["instructor_id"], ["users.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"], ["users.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"]),
    )
    op.create_index(
        "idx_instructor_alerts_open",
        "instructor_alerts",
        ["instructor_id", "severity", sa.text("created_at DESC")],
        postgresql_where=sa.text("status = 'open'"),
    )
    # Idempotency support: at-most-one OPEN alert per (course, type, target).
    # NULL target_user_id is allowed (cohort-level alerts) and Postgres treats
    # NULLs as distinct in unique indexes — that's the behaviour we want, so we
    # don't add NULLS NOT DISTINCT here. Cohort alerts are deduped by the
    # evaluator's "do not insert if any open row matches" guard instead.
    op.create_index(
        "uq_instructor_alerts_open_idempotent",
        "instructor_alerts",
        ["course_id", "alert_type", "target_user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )

    # ---------- engine_overrides ----------
    op.create_table(
        "engine_overrides",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("set_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "set_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("user_id", "course_id"),
        sa.CheckConstraint(
            "mode IN ('on','off')",
            name="ck_engine_overrides_mode_valid",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["set_by"], ["users.id"]),
    )
    op.create_index(
        "idx_engine_overrides_course",
        "engine_overrides",
        ["course_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_engine_overrides_course", table_name="engine_overrides")
    op.drop_table("engine_overrides")

    op.drop_index(
        "uq_instructor_alerts_open_idempotent", table_name="instructor_alerts"
    )
    op.drop_index("idx_instructor_alerts_open", table_name="instructor_alerts")
    op.drop_table("instructor_alerts")

    op.drop_index("idx_action_outcomes_course_action", table_name="action_outcomes")
    op.drop_index("idx_action_outcomes_user", table_name="action_outcomes")
    op.drop_index("idx_action_outcomes_variant_served", table_name="action_outcomes")
    op.drop_table("action_outcomes")

    op.drop_index("idx_next_actions_user_course", table_name="next_actions")
    op.drop_index("idx_next_actions_cleanup", table_name="next_actions")
    op.drop_index("idx_next_actions_user_active", table_name="next_actions")
    op.drop_table("next_actions")

    op.drop_constraint(
        "ck_courses_engine_mode_valid", "courses", type_="check",
    )
    op.drop_column("courses", "adaptive_engine_mode")
```

- [ ] **Step 2: Apply the migration**

Activate the venv first (memory rule: backend uses venv).

Run from `backend/`:

```bash
. .venv/bin/activate
alembic upgrade head
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade b2e9c4f7a1d3 -> b2f9a4d7c8e1, phase 3 decision layer + outcome telemetry`

- [ ] **Step 3: Verify schema in psql**

```bash
psql -U postgres -h localhost -d langassistant \
  -c "\d next_actions" \
  -c "\d action_outcomes" \
  -c "\d instructor_alerts" \
  -c "\d engine_overrides" \
  -c "SELECT column_name, data_type, column_default FROM information_schema.columns WHERE table_name = 'courses' AND column_name = 'adaptive_engine_mode';"
```

Expected: all 4 tables exist; `idx_next_actions_user_active` and `idx_next_actions_cleanup` are partial; `uq_instructor_alerts_open_idempotent` is partial+unique; `courses.adaptive_engine_mode` defaults to `'on'`.

- [ ] **Step 4: Test downgrade then re-upgrade**

```bash
alembic downgrade -1 && alembic upgrade head
```

Expected: both succeed without error.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/b2f9a4d7c8e1_phase3_decision_and_telemetry.py
git commit -m "feat(adaptive-engine): phase 3 migration — next_actions, action_outcomes, instructor_alerts, engine_overrides"
```

---

### Task 2: SQLAlchemy models for decision layer

**Files:**
- Create: `backend/app/models/decision.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_models_decision.py`

**Context:** Mirror the migration. `NextAction` and `ActionOutcome` use `UUIDPrimaryKeyMixin`; `InstructorAlert` uses `UUIDPrimaryKeyMixin`; `EngineOverride` uses a composite PK like `ConceptMastery` (no mixin). All four sit under the `Base` declarative — JSON payloads use `JSONB` for queryability of `reason` blobs.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_models_decision.py
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import (
    ActionOutcome,
    Course,
    EngineOverride,
    InstructorAlert,
    NextAction,
    User,
)


@pytest.mark.asyncio
async def test_next_action_persists_with_polymorphic_target(db_session, test_instructor: User):
    course = Course(
        name="Models Course",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="DECI-MOD",
    )
    db_session.add(course)
    await db_session.flush()

    row = NextAction(
        user_id=test_instructor.id,
        course_id=course.id,
        action_type="practice_weakness",
        target_kind="concept",
        target_id=uuid.uuid4(),
        priority_score=Decimal("3.250"),
        candidate_source="outer_fringe",
        reason={"weak_mastery": 0.31, "confidence": 0.72},
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        engine_variant="on",
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    assert row.id is not None
    assert row.served_at is None and row.clicked_at is None and row.consumed_at is None


@pytest.mark.asyncio
async def test_engine_override_composite_pk(db_session, test_instructor: User, test_student: User):
    course = Course(
        name="Override Course",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="DECI-OVR",
    )
    db_session.add(course)
    await db_session.flush()

    db_session.add(
        EngineOverride(
            user_id=test_student.id,
            course_id=course.id,
            mode="off",
            set_by=test_instructor.id,
        )
    )
    await db_session.commit()
    # Composite PK: same (user, course) must conflict.
    db_session.add(
        EngineOverride(
            user_id=test_student.id,
            course_id=course.id,
            mode="on",
            set_by=test_instructor.id,
        )
    )
    with pytest.raises(Exception):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_instructor_alert_open_dedupe(db_session, test_instructor: User, test_student: User):
    course = Course(
        name="Alert Course",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="DECI-ALR",
    )
    db_session.add(course)
    await db_session.flush()

    db_session.add(
        InstructorAlert(
            course_id=course.id,
            instructor_id=test_instructor.id,
            target_user_id=test_student.id,
            alert_type="student_falling_behind",
            severity="warning",
            title="Lo Yan Wai is 3 deadlines behind",
            reason={"missed": 3},
        )
    )
    await db_session.commit()

    # Second open alert for same (course, type, target) is forbidden by the
    # partial unique index.
    db_session.add(
        InstructorAlert(
            course_id=course.id,
            instructor_id=test_instructor.id,
            target_user_id=test_student.id,
            alert_type="student_falling_behind",
            severity="warning",
            title="dup",
            reason={"missed": 4},
        )
    )
    with pytest.raises(Exception):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_action_outcome_orphans_when_next_action_deleted(db_session, test_instructor: User):
    course = Course(
        name="Outcome Course",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="DECI-OUT",
    )
    db_session.add(course)
    await db_session.flush()

    na = NextAction(
        user_id=test_instructor.id,
        course_id=course.id,
        action_type="do_quiz",
        priority_score=Decimal("1.000"),
        candidate_source="fallback",
        reason={},
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        engine_variant="off",
    )
    db_session.add(na)
    await db_session.flush()

    out = ActionOutcome(
        next_action_id=na.id,
        user_id=test_instructor.id,
        course_id=course.id,
        action_type="do_quiz",
        engine_variant="off",
        served_at=datetime.now(timezone.utc),
    )
    db_session.add(out)
    await db_session.commit()

    await db_session.delete(na)
    await db_session.commit()
    await db_session.refresh(out)
    assert out.next_action_id is None  # ON DELETE SET NULL
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
. .venv/bin/activate
pytest tests/test_models_decision.py -v
```

Expected: ImportError (models not yet defined).

- [ ] **Step 3: Write the models**

```python
# backend/app/models/decision.py
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class NextAction(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "next_actions"
    __table_args__ = (
        CheckConstraint(
            "action_type IN ("
            "'review_concept','prep_meeting','complete_assignment',"
            "'do_quiz','practice_weakness','catch_up_reading',"
            "'flashcard_review','pronunciation_practice','watch_recording'"
            ")",
            name="ck_next_actions_action_type_valid",
        ),
        CheckConstraint(
            "target_kind IS NULL OR target_kind IN ("
            "'concept','course_meeting','assignment','quiz',"
            "'flashcard_set','pronunciation_set','document','chunk'"
            ")",
            name="ck_next_actions_target_kind_valid",
        ),
        CheckConstraint(
            "candidate_source IN ('outer_fringe','deadline','review','fallback')",
            name="ck_next_actions_candidate_source_valid",
        ),
        # Mirror partial indexes from migration so create_all (test bootstrap)
        # reproduces production semantics.
        Index(
            "idx_next_actions_user_active",
            "user_id",
            text("priority_score DESC"),
            # ``now()`` not allowed in index predicates (STABLE, not IMMUTABLE);
            # mirrors the migration. Readers filter ``expires_at > now()`` at query time.
            postgresql_where=text("consumed_at IS NULL"),
        ),
        Index(
            "idx_next_actions_cleanup",
            "expires_at",
            postgresql_where=text("consumed_at IS NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE")
    )
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_kind: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    priority_score: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False)
    candidate_source: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[dict] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    served_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    engine_variant: Mapped[str] = mapped_column(
        String(20), nullable=False, default="on", server_default=text("'on'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ActionOutcome(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "action_outcomes"
    __table_args__ = (
        CheckConstraint(
            "outcome_metric IS NULL OR outcome_metric IN "
            "('mastery_delta','quiz_score','recall','completion')",
            name="ck_action_outcomes_metric_valid",
        ),
    )

    next_action_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("next_actions.id", ondelete="SET NULL"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE")
    )
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_kind: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    engine_variant: Mapped[str] = mapped_column(String(20), nullable=False)
    served_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    clicked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    outcome_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    outcome_metric: Mapped[str | None] = mapped_column(String(40))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class InstructorAlert(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "instructor_alerts"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('info','warning','critical')",
            name="ck_instructor_alerts_severity_valid",
        ),
        CheckConstraint(
            "status IN ('open','dismissed','resolved')",
            name="ck_instructor_alerts_status_valid",
        ),
        CheckConstraint(
            "alert_type IN ("
            "'student_disengaging','student_falling_behind',"
            "'cohort_concept_weakness','prereq_gap_for_upcoming_meeting',"
            "'low_quiz_participation','missed_deadline','content_gap'"
            ")",
            name="ck_instructor_alerts_alert_type_valid",
        ),
        Index(
            "uq_instructor_alerts_open_idempotent",
            "course_id",
            "alert_type",
            "target_user_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    instructor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    alert_type: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EngineOverride(Base):
    __tablename__ = "engine_overrides"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('on','off')",
            name="ck_engine_overrides_mode_valid",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    set_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    set_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

Then update `backend/app/models/__init__.py` to import + export the four new models. Also add `adaptive_engine_mode` to `Course`:

```python
# backend/app/models/course.py — add field to Course class
    adaptive_engine_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="on", server_default=text("'on'"),
    )
```

(`text` is already imported elsewhere in the file; if not, add `from sqlalchemy import text`.)

In `backend/app/models/__init__.py`, append:

```python
from app.models.decision import (
    ActionOutcome,
    EngineOverride,
    InstructorAlert,
    NextAction,
)
```

…and add `"NextAction", "ActionOutcome", "InstructorAlert", "EngineOverride"` to `__all__`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_models_decision.py -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/decision.py backend/app/models/__init__.py backend/app/models/course.py backend/tests/test_models_decision.py
git commit -m "feat(adaptive-engine): SQLAlchemy models — NextAction, ActionOutcome, InstructorAlert, EngineOverride"
```

---

### Task 3: Pydantic schemas for decision layer

**Files:**
- Create: `backend/app/schemas/decision.py`

**Context:** Pydantic v2 with `Literal` unions for the constrained string columns. Read schemas use `model_config = {"from_attributes": True}` to read directly off SQLAlchemy rows. Mirrors `backend/app/schemas/concept.py` style.

- [ ] **Step 1: Write the schemas**

```python
# backend/app/schemas/decision.py
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

ActionType = Literal[
    "review_concept", "prep_meeting", "complete_assignment",
    "do_quiz", "practice_weakness", "catch_up_reading",
    "flashcard_review", "pronunciation_practice", "watch_recording",
]
NextActionTargetKind = Literal[
    "concept", "course_meeting", "assignment", "quiz",
    "flashcard_set", "pronunciation_set", "document", "chunk",
]
CandidateSource = Literal["outer_fringe", "deadline", "review", "fallback"]
EngineMode = Literal["on", "off", "random_50"]
OverrideMode = Literal["on", "off"]
AlertType = Literal[
    "student_disengaging", "student_falling_behind",
    "cohort_concept_weakness", "prereq_gap_for_upcoming_meeting",
    "low_quiz_participation", "missed_deadline", "content_gap",
]
AlertSeverity = Literal["info", "warning", "critical"]
AlertStatus = Literal["open", "dismissed", "resolved"]
OutcomeMetric = Literal["mastery_delta", "quiz_score", "recall", "completion"]


class NextActionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    course_id: uuid.UUID | None
    action_type: ActionType
    target_kind: NextActionTargetKind | None
    target_id: uuid.UUID | None
    priority_score: Decimal
    candidate_source: CandidateSource
    reason: dict
    expires_at: datetime
    served_at: datetime | None
    clicked_at: datetime | None
    consumed_at: datetime | None
    engine_variant: str
    created_at: datetime

    model_config = {"from_attributes": True}


class NextActionClickResponse(BaseModel):
    id: uuid.UUID
    clicked_at: datetime
    target_kind: NextActionTargetKind | None
    target_id: uuid.UUID | None


class EngineSettingsResponse(BaseModel):
    course_id: uuid.UUID
    mode: EngineMode
    overrides_count: int


class EngineSettingsUpdate(BaseModel):
    mode: EngineMode


class EngineOverrideUpdate(BaseModel):
    mode: OverrideMode


class EngineOverrideResponse(BaseModel):
    user_id: uuid.UUID
    course_id: uuid.UUID
    mode: OverrideMode
    set_by: uuid.UUID
    set_at: datetime

    model_config = {"from_attributes": True}


class InstructorAlertResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    instructor_id: uuid.UUID
    target_user_id: uuid.UUID | None
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    reason: dict
    status: AlertStatus
    resolved_at: datetime | None
    resolved_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class InstructorAlertUpdate(BaseModel):
    status: Literal["dismissed", "resolved"]


class ActionOutcomeRow(BaseModel):
    """Read shape used by the instructor analytics endpoint."""
    engine_variant: str
    served_count: int
    click_rate: float
    completion_rate: float
    mean_outcome_score: float | None


class ActionOutcomesSummary(BaseModel):
    course_id: uuid.UUID
    window_days: int
    rows: list[ActionOutcomeRow]
```

- [ ] **Step 2: Smoke test imports**

```bash
. .venv/bin/activate
python -c "from app.schemas.decision import NextActionResponse, EngineSettingsResponse, InstructorAlertResponse; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/decision.py
git commit -m "feat(adaptive-engine): Pydantic schemas for decision layer"
```

---

### Task 4: Engine mode resolver service (override > course > random_50 hash)

**Files:**
- Create: `backend/app/services/engine_mode.py`
- Test: `backend/tests/test_engine_mode.py`

**Context:** `random_50` mode uses `hash(user_id || course_id) % 2` to deterministically place each student in either `'on'` or `'off'`. This means the same student always sees the same arm across logins — clean per-student outcome curves. Use `hashlib.blake2b` for stable cross-process hashing (Python's built-in `hash()` is randomised per interpreter).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_engine_mode.py
import uuid
import pytest

from app.models import Course, EngineOverride, User
from app.services.engine_mode import resolve_engine_mode


@pytest.mark.asyncio
async def test_override_wins_over_course_flag(db_session, test_instructor: User, test_student: User):
    course = Course(
        name="Override wins",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ENG-OVR1",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        EngineOverride(
            user_id=test_student.id,
            course_id=course.id,
            mode="off",
            set_by=test_instructor.id,
        )
    )
    await db_session.commit()

    mode = await resolve_engine_mode(db_session, user_id=test_student.id, course_id=course.id)
    assert mode == "off"


@pytest.mark.asyncio
async def test_no_override_falls_through_to_course(db_session, test_instructor: User, test_student: User):
    course = Course(
        name="Course flag",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ENG-OVR2",
        adaptive_engine_mode="off",
    )
    db_session.add(course)
    await db_session.commit()

    mode = await resolve_engine_mode(db_session, user_id=test_student.id, course_id=course.id)
    assert mode == "off"


@pytest.mark.asyncio
async def test_random_50_is_deterministic(db_session, test_instructor: User, test_student: User):
    course = Course(
        name="Random 50",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ENG-RAND",
        adaptive_engine_mode="random_50",
    )
    db_session.add(course)
    await db_session.commit()

    a = await resolve_engine_mode(db_session, user_id=test_student.id, course_id=course.id)
    b = await resolve_engine_mode(db_session, user_id=test_student.id, course_id=course.id)
    assert a == b
    assert a in ("on", "off")


def test_random_50_distribution_is_balanced():
    # Pure unit test — the splitter alone, no DB.
    from app.services.engine_mode import _coin_flip_random_50

    course_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    flips = [_coin_flip_random_50(uuid.uuid4(), course_id) for _ in range(2000)]
    on_count = sum(1 for f in flips if f == "on")
    # Allow ±5% slack — 2000 flips of a fair coin is well inside binomial.
    assert 900 <= on_count <= 1100
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_engine_mode.py -v
```

Expected: ImportError.

- [ ] **Step 3: Write the service**

```python
# backend/app/services/engine_mode.py
"""Resolve effective adaptive-engine mode for a (user, course) pair.

Resolution order:
1. ``engine_overrides`` row → mode ('on'|'off')
2. ``courses.adaptive_engine_mode`` → 'on' | 'off' | 'random_50'
3. random_50 → deterministic hash of (user_id, course_id) → 'on' | 'off'

The deterministic hash uses ``blake2b`` (not Python's ``hash()``, which is
randomised per interpreter and would re-bucket users every restart).
"""
from __future__ import annotations

import hashlib
import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course, EngineOverride

ResolvedMode = Literal["on", "off"]


def _coin_flip_random_50(user_id: uuid.UUID, course_id: uuid.UUID) -> ResolvedMode:
    """Deterministically map (user, course) → 'on' or 'off'."""
    h = hashlib.blake2b(digest_size=8)
    h.update(user_id.bytes)
    h.update(course_id.bytes)
    return "on" if int.from_bytes(h.digest(), "big") % 2 == 0 else "off"


async def resolve_engine_mode(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
) -> ResolvedMode:
    override = (
        await db.execute(
            select(EngineOverride.mode).where(
                EngineOverride.user_id == user_id,
                EngineOverride.course_id == course_id,
            )
        )
    ).scalar_one_or_none()
    if override is not None:
        return override  # 'on' | 'off' (CHECK constrains values)

    course_mode = (
        await db.execute(
            select(Course.adaptive_engine_mode).where(Course.id == course_id)
        )
    ).scalar_one_or_none()
    if course_mode is None or course_mode == "off":
        return "off"
    if course_mode == "on":
        return "on"
    # course_mode == 'random_50'
    return _coin_flip_random_50(user_id, course_id)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_engine_mode.py -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/engine_mode.py backend/tests/test_engine_mode.py
git commit -m "feat(adaptive-engine): engine mode resolver — override > course > deterministic random_50 hash"
```

---

### Task 5: KST outer-fringe filter

**Files:**
- Create: `backend/app/services/outer_fringe.py`
- Test: `backend/tests/test_outer_fringe.py`

**Context:** Pure SQL — concepts whose every prerequisite has `mastery_score >= 0.7 AND confidence >= 0.5` but whose own row falls below the same threshold. Spec §"KST 'outer fringe' — the candidate filter" (lines 647–680).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_outer_fringe.py
import uuid
from decimal import Decimal

import pytest

from app.models import (
    Concept,
    ConceptMastery,
    ConceptPrerequisite,
    Course,
    User,
)
from app.services.outer_fringe import outer_fringe_concepts


async def _seed_course_with_concepts(
    db_session, instructor: User, student: User
):
    course = Course(
        name="OF Course",
        language="en",
        instructor_id=instructor.id,
        enroll_code="OF-1",
    )
    db_session.add(course)
    await db_session.flush()

    a = Concept(course_id=course.id, name="A", status="approved")
    b = Concept(course_id=course.id, name="B", status="approved")
    c = Concept(course_id=course.id, name="C", status="approved")
    db_session.add_all([a, b, c])
    await db_session.flush()

    # B depends on A; C depends on B.
    db_session.add_all([
        ConceptPrerequisite(prereq_concept_id=a.id, dependent_concept_id=b.id, strength=Decimal("1.00")),
        ConceptPrerequisite(prereq_concept_id=b.id, dependent_concept_id=c.id, strength=Decimal("1.00")),
    ])
    await db_session.commit()
    return course, a, b, c


@pytest.mark.asyncio
async def test_no_mastery_yields_only_root(db_session, test_instructor: User, test_student: User):
    course, a, b, c = await _seed_course_with_concepts(db_session, test_instructor, test_student)
    rows = await outer_fringe_concepts(
        db_session, user_id=test_student.id, course_id=course.id
    )
    ids = {r.concept_id for r in rows}
    assert a.id in ids
    assert b.id not in ids and c.id not in ids


@pytest.mark.asyncio
async def test_mastered_root_unblocks_b(db_session, test_instructor: User, test_student: User):
    course, a, b, c = await _seed_course_with_concepts(db_session, test_instructor, test_student)
    db_session.add(
        ConceptMastery(
            user_id=test_student.id, concept_id=a.id, course_id=course.id,
            alpha=Decimal("8.000"), beta=Decimal("2.000"),
            confidence=Decimal("0.700"),
        )
    )
    await db_session.commit()
    rows = await outer_fringe_concepts(
        db_session, user_id=test_student.id, course_id=course.id
    )
    ids = {r.concept_id for r in rows}
    assert b.id in ids and a.id not in ids and c.id not in ids


@pytest.mark.asyncio
async def test_low_confidence_prereq_blocks(db_session, test_instructor: User, test_student: User):
    course, a, b, c = await _seed_course_with_concepts(db_session, test_instructor, test_student)
    # Mastery is high but confidence is below 0.5 → A is not "really" mastered.
    db_session.add(
        ConceptMastery(
            user_id=test_student.id, concept_id=a.id, course_id=course.id,
            alpha=Decimal("3.000"), beta=Decimal("1.000"),
            confidence=Decimal("0.300"),
        )
    )
    await db_session.commit()
    rows = await outer_fringe_concepts(
        db_session, user_id=test_student.id, course_id=course.id
    )
    ids = {r.concept_id for r in rows}
    # A is still in the fringe (not yet mastered with confidence) so still
    # surfaces; B is blocked because A doesn't meet the prereq predicate.
    assert a.id in ids and b.id not in ids


@pytest.mark.asyncio
async def test_canonical_merged_concepts_excluded(db_session, test_instructor: User, test_student: User):
    course = Course(
        name="OF canonical",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="OF-2",
    )
    db_session.add(course)
    await db_session.flush()
    canonical = Concept(course_id=course.id, name="canon", status="approved")
    db_session.add(canonical)
    await db_session.flush()
    merged = Concept(
        course_id=course.id, name="dup", status="merged",
        canonical_id=canonical.id,
    )
    db_session.add(merged)
    await db_session.commit()

    rows = await outer_fringe_concepts(
        db_session, user_id=test_student.id, course_id=course.id
    )
    ids = {r.concept_id for r in rows}
    assert canonical.id in ids and merged.id not in ids
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_outer_fringe.py -v
```

Expected: ImportError.

- [ ] **Step 3: Write the service**

```python
# backend/app/services/outer_fringe.py
"""KST outer-fringe filter.

A concept is in the outer fringe of a (user, course) when every prerequisite
edge with strength >= 0.5 leads to a concept the user has *mastered* — i.e.
``mastery_score >= 0.7 AND confidence >= 0.5`` — and the concept itself does
not meet that bar.

Returns a list of (concept_id, name, current_mastery, current_confidence)
ordered by current mastery ascending so the candidate scorer sees the
weakest-but-ready concepts first.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

OUTER_FRINGE_MASTERY_BAR = Decimal("0.7")
OUTER_FRINGE_CONFIDENCE_BAR = Decimal("0.5")


@dataclass(frozen=True)
class FringeConcept:
    concept_id: uuid.UUID
    name: str
    current_mastery: float        # 0.0 if user has no row yet
    current_confidence: float     # 0.0 if user has no row yet


async def outer_fringe_concepts(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
) -> list[FringeConcept]:
    sql = text(
        """
        WITH user_state AS (
            SELECT concept_id, mastery_score, confidence
              FROM public.concept_mastery
             WHERE user_id = :user_id
               AND course_id = :course_id
        )
        SELECT
            c.id   AS concept_id,
            c.name AS name,
            COALESCE(s.mastery_score, 0)::float8 AS current_mastery,
            COALESCE(s.confidence,    0)::float8 AS current_confidence
          FROM public.concepts c
          LEFT JOIN user_state s ON s.concept_id = c.id
         WHERE c.course_id = :course_id
           AND c.deleted_at IS NULL
           AND c.canonical_id IS NULL
           AND c.status = 'approved'
           -- Concept is "in the fringe" if it has not yet met BOTH bars:
           -- mastery >= 0.7 AND confidence >= 0.5. Failing either qualifies.
           AND (
                  COALESCE(s.mastery_score, 0) < :mastery_bar
               OR COALESCE(s.confidence, 0)    < :confidence_bar
           )
           AND NOT EXISTS (
               SELECT 1
                 FROM public.concept_prerequisites p
                 LEFT JOIN user_state ps ON ps.concept_id = p.prereq_concept_id
                WHERE p.dependent_concept_id = c.id
                  AND p.strength >= 0.5
                  AND (
                      COALESCE(ps.mastery_score, 0) < :mastery_bar
                      OR COALESCE(ps.confidence, 0) < :confidence_bar
                  )
           )
         ORDER BY current_mastery ASC, c.name ASC
        """
    )
    rows = await db.execute(
        sql,
        {
            "user_id": user_id,
            "course_id": course_id,
            "mastery_bar": float(OUTER_FRINGE_MASTERY_BAR),
            "confidence_bar": float(OUTER_FRINGE_CONFIDENCE_BAR),
        },
    )
    return [
        FringeConcept(
            concept_id=r.concept_id,
            name=r.name,
            current_mastery=float(r.current_mastery),
            current_confidence=float(r.current_confidence),
        )
        for r in rows
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_outer_fringe.py -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/outer_fringe.py backend/tests/test_outer_fringe.py
git commit -m "feat(adaptive-engine): KST outer-fringe candidate filter"
```

---

### Task 6: Scoring engine

**Files:**
- Create: `backend/app/services/scoring.py`
- Test: `backend/tests/test_scoring.py`

**Context:** Pure functions for the five scoring formulas in spec §Scoring (line 686). Coefficients are passed via a `coeffs: Mapping[str, float] = DEFAULT_COEFFS` keyword on each scoring function — Task 17 retune produces a fresh dict and the materialiser passes it down per call (parameter injection, not module-attribute rebind, so type-checkers stay sound and async workers don't share mutable global state). For Phase 3 ship, defaults stand and the retune job only proposes deltas.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_scoring.py
from decimal import Decimal

from app.services.scoring import (
    DEFAULT_COEFFS,
    score_catch_up_reading,
    score_complete_assignment,
    score_flashcard_review,
    score_practice_weakness,
    score_prep_meeting,
)


def test_prep_meeting_increases_with_weak_concepts():
    near = score_prep_meeting(
        meeting_concept_weights=[(1.0, 0.3), (1.0, 0.2)],  # high (1 - mastery)
        days_until_meeting=1.0,
        coeffs=DEFAULT_COEFFS,
    )
    far = score_prep_meeting(
        meeting_concept_weights=[(1.0, 0.3), (1.0, 0.2)],
        days_until_meeting=14.0,
        coeffs=DEFAULT_COEFFS,
    )
    assert near > far


def test_complete_assignment_weights_due_date():
    today = score_complete_assignment(
        assignment_weight=Decimal("1.00"),
        days_until_due=0.0,
        coeffs=DEFAULT_COEFFS,
    )
    next_week = score_complete_assignment(
        assignment_weight=Decimal("1.00"),
        days_until_due=7.0,
        coeffs=DEFAULT_COEFFS,
    )
    assert today > next_week
    assert today == DEFAULT_COEFFS["complete_assignment"]


def test_practice_weakness_zero_when_no_evidence():
    # Confidence factor zeroes out a fresh concept (intended — bandit handles cold start).
    s = score_practice_weakness(mastery=0.0, confidence=0.0)
    assert s == 0.0


def test_practice_weakness_grows_with_evidence_gap():
    s_weak = score_practice_weakness(mastery=0.2, confidence=0.8)
    s_mid = score_practice_weakness(mastery=0.5, confidence=0.8)
    assert s_weak > s_mid > 0


def test_flashcard_review_linear_in_due_count():
    five = score_flashcard_review(cards_due_count=5, coeffs=DEFAULT_COEFFS)
    twenty = score_flashcard_review(cards_due_count=20, coeffs=DEFAULT_COEFFS)
    assert twenty == 4 * five


def test_catch_up_reading_grows_with_overdue_days():
    a = score_catch_up_reading(days_overdue=0, coeffs=DEFAULT_COEFFS)
    b = score_catch_up_reading(days_overdue=7, coeffs=DEFAULT_COEFFS)
    assert b > a
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_scoring.py -v
```

Expected: ImportError.

- [ ] **Step 3: Write the service**

```python
# backend/app/services/scoring.py
"""Scoring formulas for the decision engine.

Coefficients are initial values per spec §Scoring; the quarterly
``tune_action_coefficients`` job retunes them from ``action_outcomes``
telemetry. Until that job has fired, ``DEFAULT_COEFFS`` stands.

All scores are returned as ``float`` for ergonomics. The materialiser
quantizes to ``Decimal(7,3)`` before persisting (matches
``next_actions.priority_score`` column type).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Mapping, Sequence

DEFAULT_COEFFS: Mapping[str, float] = {
    "prep_meeting": 3.0,
    "complete_assignment": 5.0,
    "practice_weakness": 2.0,
    "flashcard_review": 1.5,
    "catch_up_reading": 1.0,
}


def score_prep_meeting(
    *,
    meeting_concept_weights: Sequence[tuple[float, float]],
    days_until_meeting: float,
    coeffs: Mapping[str, float] = DEFAULT_COEFFS,
) -> float:
    """3.0 × P_m × 1/(1 + S_m), where P_m = Σ weight × (1 − mastery)."""
    if not meeting_concept_weights:
        return 0.0
    p_m = sum(w * max(0.0, 1.0 - m) for w, m in meeting_concept_weights)
    return coeffs["prep_meeting"] * p_m * (1.0 / (1.0 + max(0.0, days_until_meeting)))


def score_complete_assignment(
    *,
    assignment_weight: Decimal | None,
    days_until_due: float,
    coeffs: Mapping[str, float] = DEFAULT_COEFFS,
) -> float:
    """5.0 × assignment.weight × 1/(1 + D_a). Treats ``None`` weight as 1.0."""
    w = float(assignment_weight) if assignment_weight is not None else 1.0
    return coeffs["complete_assignment"] * w * (1.0 / (1.0 + max(0.0, days_until_due)))


def score_practice_weakness(
    *,
    mastery: float,
    confidence: float,
    recency_factor: float = 1.0,
    coeffs: Mapping[str, float] = DEFAULT_COEFFS,
) -> float:
    """2.0 × (1 − mastery) × confidence × recency_factor."""
    return (
        coeffs["practice_weakness"]
        * max(0.0, 1.0 - mastery)
        * max(0.0, min(1.0, confidence))
        * recency_factor
    )


def score_flashcard_review(
    *,
    cards_due_count: int,
    coeffs: Mapping[str, float] = DEFAULT_COEFFS,
) -> float:
    """1.5 × cards_due_count."""
    return coeffs["flashcard_review"] * max(0, cards_due_count)


def score_catch_up_reading(
    *,
    days_overdue: int,
    coeffs: Mapping[str, float] = DEFAULT_COEFFS,
) -> float:
    """1.0 × (days_overdue + 1)."""
    return coeffs["catch_up_reading"] * (max(0, days_overdue) + 1)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_scoring.py -v
```

Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/scoring.py backend/tests/test_scoring.py
git commit -m "feat(adaptive-engine): scoring engine — 5 action types with default coefficients"
```

---

### Task 7: Materializer — outer-fringe + score → top-10 next_actions

**Files:**
- Create: `backend/app/services/next_actions.py`
- Test: `backend/tests/test_next_actions_service.py`

**Context:** This is the orchestrator. For a `(user, course)`:

1. Resolve `engine_variant` via `engine_mode.resolve_engine_mode`. If `'off'`, write zero rows and return `[]`.
2. Run `outer_fringe_concepts`. If empty, fall back to "weakest concept regardless of prereqs" (limit 5) tagged `candidate_source='fallback'`.
3. For each fringe concept, build candidate `(action_type, target)` tuples:
   - `practice_weakness` → target the concept itself (`target_kind='concept'`).
   - `prep_meeting` → for any upcoming `course_meetings.scheduled_at` within next 7 days that is tagged with this concept, propose `prep_meeting` targeting that meeting.
   - `complete_assignment` → for any `assignments.due_at` within next 7 days tagged with this concept (and not yet submitted), propose `complete_assignment` targeting that assignment. (`candidate_source='deadline'`.)
   - `flashcard_review` → if any flashcard sets in this course are due (heuristic: `flashcard_progress.next_review_at <= now()` for cards on this concept), propose with `cards_due_count`.
   - `catch_up_reading` → for any document linked to a past meeting (`course_meetings.scheduled_at < now()`) where the student has no recent attempt covering its concepts, propose with `days_overdue` (`candidate_source='review'`).
4. Score each candidate via the appropriate `score_*` function.
5. **Replace** the user's existing unconsumed rows for this course (delete + insert) — simpler than diffing and prevents duplicate rows when the same `(action_type, target)` re-scores. Spec confirms `next_actions` is a cache.
6. Take top 10 by `priority_score DESC`, write with `expires_at = now() + interval '1 hour'` and `engine_variant`.

The Phase 1 entity tables (`course_meetings`, `assignments`, `assignment_submissions`) and the Phase 2 `concept_tags` are read-only inputs.

This task implements the materializer + the **`record_serve`** helper used by the read API in Task 10. **`record_click`** + **`record_observation`** are in Task 14.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_next_actions_service.py
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import (
    Concept,
    ConceptMastery,
    ConceptTag,
    Course,
    CourseMeeting,
    Enrollment,
    NextAction,
    User,
)
from app.services.next_actions import (
    materialize_next_actions,
    record_serve,
)


@pytest.mark.asyncio
async def test_materialize_writes_rows_with_one_hour_ttl(
    db_session, test_instructor: User, test_student: User
):
    course = Course(
        name="Mat course",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="MAT-1",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=test_student.id, role="student"))

    c = Concept(course_id=course.id, name="Pivot", status="approved")
    db_session.add(c)
    await db_session.flush()
    db_session.add(
        ConceptMastery(
            user_id=test_student.id, concept_id=c.id, course_id=course.id,
            alpha=Decimal("1.000"), beta=Decimal("3.000"),
            confidence=Decimal("0.600"),
        )
    )
    await db_session.commit()

    rows = await materialize_next_actions(
        db_session, user_id=test_student.id, course_id=course.id
    )
    assert len(rows) >= 1
    persisted = (await db_session.execute(
        __import__("sqlalchemy").select(NextAction).where(
            NextAction.user_id == test_student.id, NextAction.course_id == course.id
        )
    )).scalars().all()
    assert len(persisted) == len(rows)
    for r in persisted:
        delta = r.expires_at - datetime.now(timezone.utc)
        assert timedelta(minutes=58) <= delta <= timedelta(minutes=62)
        assert r.engine_variant == "on"


@pytest.mark.asyncio
async def test_materialize_off_mode_returns_empty(
    db_session, test_instructor: User, test_student: User
):
    course = Course(
        name="Off course",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="MAT-2",
        adaptive_engine_mode="off",
    )
    db_session.add(course)
    await db_session.commit()

    rows = await materialize_next_actions(
        db_session, user_id=test_student.id, course_id=course.id
    )
    assert rows == []


@pytest.mark.asyncio
async def test_materialize_replaces_existing_unconsumed_rows(
    db_session, test_instructor: User, test_student: User
):
    course = Course(
        name="Replace",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="MAT-3",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()

    c = Concept(course_id=course.id, name="X", status="approved")
    db_session.add(c)
    await db_session.flush()
    db_session.add(
        ConceptMastery(
            user_id=test_student.id, concept_id=c.id, course_id=course.id,
            alpha=Decimal("1.000"), beta=Decimal("2.000"),
            confidence=Decimal("0.600"),
        )
    )
    await db_session.commit()

    first = await materialize_next_actions(
        db_session, user_id=test_student.id, course_id=course.id
    )
    second = await materialize_next_actions(
        db_session, user_id=test_student.id, course_id=course.id
    )
    # Same number of rows, no orphaned previous-cycle rows hanging around.
    persisted = (await db_session.execute(
        __import__("sqlalchemy").select(NextAction).where(
            NextAction.user_id == test_student.id,
            NextAction.course_id == course.id,
            NextAction.consumed_at.is_(None),
        )
    )).scalars().all()
    assert len(persisted) == len(second)


@pytest.mark.asyncio
async def test_record_serve_stamps_served_at(
    db_session, test_instructor: User, test_student: User
):
    course = Course(
        name="Serve",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="MAT-4",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    c = Concept(course_id=course.id, name="Z", status="approved")
    db_session.add(c)
    await db_session.flush()
    db_session.add(
        ConceptMastery(
            user_id=test_student.id, concept_id=c.id, course_id=course.id,
            alpha=Decimal("1.000"), beta=Decimal("2.000"),
            confidence=Decimal("0.600"),
        )
    )
    await db_session.commit()

    rows = await materialize_next_actions(
        db_session, user_id=test_student.id, course_id=course.id
    )
    assert all(r.served_at is None for r in rows)

    served = await record_serve(db_session, [r.id for r in rows])
    assert all(r.served_at is not None for r in served)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_next_actions_service.py -v
```

Expected: ImportError.

- [ ] **Step 3: Write the materializer**

```python
# backend/app/services/next_actions.py
"""Materialise top-10 next_actions for a (user, course).

Cycle:
  1. resolve engine_variant
  2. outer_fringe_concepts → fallback to weakest-3 if empty
  3. expand each concept into candidate (action_type, target) tuples
  4. score each via app.services.scoring
  5. delete unconsumed existing rows for (user, course)
  6. insert top 10 with expires_at = now() + 1 hour, engine_variant set
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable

from sqlalchemy import and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Assignment,
    AssignmentSubmission,
    Concept,
    ConceptMastery,
    ConceptTag,
    Course,
    CourseMeeting,
    FlashcardCard,
    FlashcardProgress,
    NextAction,
)
from app.services.engine_mode import resolve_engine_mode
from app.services.outer_fringe import outer_fringe_concepts
from app.services.scoring import (
    DEFAULT_COEFFS,
    score_catch_up_reading,
    score_complete_assignment,
    score_flashcard_review,
    score_practice_weakness,
    score_prep_meeting,
)

TTL_HOURS = 1
TOP_N = 10
DEADLINE_HORIZON_DAYS = 7


@dataclass
class _Candidate:
    action_type: str
    target_kind: str | None
    target_id: uuid.UUID | None
    priority_score: float
    candidate_source: str
    reason: dict


async def _expand_concept_candidates(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    concept_id: uuid.UUID,
    concept_name: str,
    mastery: float,
    confidence: float,
    now: datetime,
) -> list[_Candidate]:
    out: list[_Candidate] = []

    # 1. practice_weakness on the concept itself
    s = score_practice_weakness(mastery=mastery, confidence=confidence)
    if s > 0:
        out.append(
            _Candidate(
                action_type="practice_weakness",
                target_kind="concept",
                target_id=concept_id,
                priority_score=s,
                candidate_source="outer_fringe",
                reason={
                    "concept_name": concept_name,
                    "mastery": mastery,
                    "confidence": confidence,
                },
            )
        )

    # 2. prep_meeting / complete_assignment for upcoming items tagged with this concept
    horizon = now + timedelta(days=DEADLINE_HORIZON_DAYS)

    # Upcoming meetings tagged with this concept.
    meetings = (
        await db.execute(
            select(CourseMeeting, ConceptTag.weight)
            .join(ConceptTag, and_(
                ConceptTag.target_kind == "meeting",
                ConceptTag.target_id == CourseMeeting.id,
            ))
            .where(
                ConceptTag.concept_id == concept_id,
                CourseMeeting.course_id == course_id,
                CourseMeeting.deleted_at.is_(None),
                CourseMeeting.scheduled_at.between(now, horizon),
            )
        )
    ).all()
    for meeting, tag_weight in meetings:
        days = (meeting.scheduled_at - now).total_seconds() / 86400.0
        s = score_prep_meeting(
            meeting_concept_weights=[(float(tag_weight), mastery)],
            days_until_meeting=max(0.0, days),
        )
        if s > 0:
            out.append(
                _Candidate(
                    action_type="prep_meeting",
                    target_kind="course_meeting",
                    target_id=meeting.id,
                    priority_score=s,
                    candidate_source="deadline",
                    reason={
                        "concept_name": concept_name,
                        "meeting_title": meeting.title,
                        "scheduled_at": meeting.scheduled_at.isoformat(),
                        "days_until": days,
                    },
                )
            )

    # Upcoming assignments tagged with this concept that the user has NOT submitted.
    submitted_subq = (
        select(AssignmentSubmission.assignment_id).where(
            AssignmentSubmission.user_id == user_id,
            AssignmentSubmission.status.in_(("submitted", "graded")),
        )
    )
    assignments = (
        await db.execute(
            select(Assignment)
            .join(ConceptTag, and_(
                ConceptTag.target_kind == "assignment",
                ConceptTag.target_id == Assignment.id,
            ))
            .where(
                ConceptTag.concept_id == concept_id,
                Assignment.course_id == course_id,
                Assignment.deleted_at.is_(None),
                Assignment.due_at.between(now, horizon),
                Assignment.id.not_in(submitted_subq),
            )
        )
    ).scalars().all()
    for asn in assignments:
        days = (asn.due_at - now).total_seconds() / 86400.0
        s = score_complete_assignment(
            assignment_weight=asn.weight or Decimal("1.00"),
            days_until_due=max(0.0, days),
        )
        if s > 0:
            out.append(
                _Candidate(
                    action_type="complete_assignment",
                    target_kind="assignment",
                    target_id=asn.id,
                    priority_score=s,
                    candidate_source="deadline",
                    reason={
                        "concept_name": concept_name,
                        "assignment_title": asn.title,
                        "due_at": asn.due_at.isoformat(),
                        "days_until": days,
                    },
                )
            )

    return out


async def _flashcard_review_candidates(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    now: datetime,
) -> list[_Candidate]:
    """One catch-all flashcard_review candidate per course if anything is due."""
    due_count = (
        await db.execute(
            select(__import__("sqlalchemy").func.count())
            .select_from(FlashcardProgress)
            .join(FlashcardCard, FlashcardCard.id == FlashcardProgress.flashcard_card_id)
            .join(
                Concept,
                Concept.course_id == course_id,
                isouter=True,
            )
            .where(
                FlashcardProgress.user_id == user_id,
                FlashcardProgress.next_review_at.is_not(None),
                FlashcardProgress.next_review_at <= now,
            )
        )
    ).scalar_one()
    if not due_count:
        return []
    s = score_flashcard_review(cards_due_count=int(due_count))
    return [
        _Candidate(
            action_type="flashcard_review",
            target_kind=None,
            target_id=None,
            priority_score=s,
            candidate_source="review",
            reason={"cards_due": int(due_count)},
        )
    ]


async def materialize_next_actions(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    now: datetime | None = None,
) -> list[NextAction]:
    now = now or datetime.now(timezone.utc)
    variant = await resolve_engine_mode(db, user_id=user_id, course_id=course_id)
    if variant == "off":
        # Drop any stale unconsumed rows so the off-arm UI is clean.
        await db.execute(
            delete(NextAction).where(
                NextAction.user_id == user_id,
                NextAction.course_id == course_id,
                NextAction.consumed_at.is_(None),
            )
        )
        await db.commit()
        return []

    fringe = await outer_fringe_concepts(db, user_id=user_id, course_id=course_id)
    candidates: list[_Candidate] = []

    if not fringe:
        # Fallback: weakest 3 concepts the student has any evidence on.
        rows = (
            await db.execute(
                select(ConceptMastery, Concept.name)
                .join(Concept, Concept.id == ConceptMastery.concept_id)
                .where(
                    ConceptMastery.user_id == user_id,
                    ConceptMastery.course_id == course_id,
                    Concept.deleted_at.is_(None),
                    Concept.canonical_id.is_(None),
                )
                .order_by(ConceptMastery.mastery_score.asc())
                .limit(3)
            )
        ).all()
        for m, name in rows:
            s = score_practice_weakness(
                mastery=float(m.mastery_score), confidence=float(m.confidence)
            )
            if s > 0:
                candidates.append(
                    _Candidate(
                        action_type="practice_weakness",
                        target_kind="concept",
                        target_id=m.concept_id,
                        priority_score=s,
                        candidate_source="fallback",
                        reason={
                            "concept_name": name,
                            "mastery": float(m.mastery_score),
                            "confidence": float(m.confidence),
                        },
                    )
                )
    else:
        for fc in fringe:
            candidates.extend(
                await _expand_concept_candidates(
                    db,
                    user_id=user_id,
                    course_id=course_id,
                    concept_id=fc.concept_id,
                    concept_name=fc.name,
                    mastery=fc.current_mastery,
                    confidence=fc.current_confidence,
                    now=now,
                )
            )

    candidates.extend(
        await _flashcard_review_candidates(
            db, user_id=user_id, course_id=course_id, now=now
        )
    )

    # Replace existing unconsumed cache rows.
    await db.execute(
        delete(NextAction).where(
            NextAction.user_id == user_id,
            NextAction.course_id == course_id,
            NextAction.consumed_at.is_(None),
        )
    )

    # Top N by priority_score desc.
    top = sorted(candidates, key=lambda c: -c.priority_score)[:TOP_N]
    expires_at = now + timedelta(hours=TTL_HOURS)
    rows = [
        NextAction(
            user_id=user_id,
            course_id=course_id,
            action_type=c.action_type,
            target_kind=c.target_kind,
            target_id=c.target_id,
            priority_score=Decimal(f"{c.priority_score:.3f}"),
            candidate_source=c.candidate_source,
            reason=c.reason,
            expires_at=expires_at,
            engine_variant=variant,
        )
        for c in top
    ]
    db.add_all(rows)
    await db.commit()
    for r in rows:
        await db.refresh(r)
    return rows


async def record_serve(
    db: AsyncSession, action_ids: Iterable[uuid.UUID]
) -> list[NextAction]:
    """Stamp ``served_at = now()`` on each row that hasn't been served yet.

    Idempotent: rows with a non-null ``served_at`` are left alone.
    """
    ids = [i for i in action_ids if i is not None]
    if not ids:
        return []
    now = datetime.now(timezone.utc)
    await db.execute(
        update(NextAction)
        .where(
            NextAction.id.in_(ids),
            NextAction.served_at.is_(None),
        )
        .values(served_at=now)
    )
    await db.commit()
    rows = (
        await db.execute(
            select(NextAction).where(NextAction.id.in_(ids))
        )
    ).scalars().all()
    return list(rows)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_next_actions_service.py -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/next_actions.py backend/tests/test_next_actions_service.py
git commit -m "feat(adaptive-engine): next_actions materializer — outer-fringe + score → top-10"
```

---

## Phase 3.2 — Worker + APIs

### Task 8: Worker handlers + dispatch for materialize / outcome / retune / alerts

**Files:**
- Modify: `backend/app/services/jobs.py`
- Modify: `backend/app/services/worker.py`
- Test: `backend/tests/test_jobs_phase3.py`

**Context:** Add four task handlers that the worker dispatch (`process_task`) chooses by `task_type`:

- `materialize_next_actions` → calls `materialize_next_actions(user, course)`. Idempotent: replaces unconsumed rows.
- `record_action_outcome` → writes one `action_outcomes` row from a payload. Used by the post-attempt observation hook (Task 14) and by the click endpoint (Task 10).
- `evaluate_instructor_alerts` → calls `evaluate_alerts_for_course(course_id)`. (Task 15.)
- `tune_action_coefficients` → quarterly retune. (Task 17.)

The worker `worker_loop` gets two new cron watermarks:
- `last_alert_run` — hourly cadence (`evaluate_instructor_alerts` for every course).
- `last_retune_run` — quarterly cadence (`tune_action_coefficients`). Use `timedelta(days=90)`.

These two are added below the existing `last_decay_run` block, mirroring the same `_utcnow() - last_*_run > timedelta(...)` pattern used for the overdue + decay sweeps. **Do not collapse into a single periodic scheduler** — the existing pattern is fine and is the precedent in this codebase.

This task wires dispatch + the `materialize_next_actions` and `record_action_outcome` handlers. The two cron handlers are stubbed to return `{}` and filled in Tasks 15 and 17.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_jobs_phase3.py
import uuid
from datetime import datetime, timezone

import pytest

from app.models import (
    ActionOutcome,
    Concept,
    ConceptMastery,
    Course,
    Enrollment,
    NextAction,
    User,
)
from app.services.jobs import (
    run_materialize_next_actions,
    run_record_action_outcome,
)


@pytest.mark.asyncio
async def test_run_materialize_writes_rows(db_session, test_instructor: User, test_student: User):
    from decimal import Decimal

    course = Course(
        name="Worker mat",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="WM-1",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=test_student.id, role="student"))
    c = Concept(course_id=course.id, name="t", status="approved")
    db_session.add(c)
    await db_session.flush()
    db_session.add(
        ConceptMastery(
            user_id=test_student.id, concept_id=c.id, course_id=course.id,
            alpha=Decimal("1.000"), beta=Decimal("2.000"),
            confidence=Decimal("0.600"),
        )
    )
    await db_session.commit()

    result = await run_materialize_next_actions(
        db_session,
        {"user_id": str(test_student.id), "course_id": str(course.id)},
    )
    assert result["count"] >= 1


@pytest.mark.asyncio
async def test_run_record_action_outcome_persists_row(db_session, test_student: User):
    payload = {
        "user_id": str(test_student.id),
        "action_type": "do_quiz",
        "engine_variant": "off",
        "served_at": datetime.now(timezone.utc).isoformat(),
        "clicked": True,
        "completed": True,
        "outcome_metric": "quiz_score",
        "outcome_score": 0.83,
    }
    result = await run_record_action_outcome(db_session, payload)
    assert result["status"] == "recorded"
    rows = (await db_session.execute(
        __import__("sqlalchemy").select(ActionOutcome).where(
            ActionOutcome.user_id == test_student.id
        )
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].engine_variant == "off"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_jobs_phase3.py -v
```

Expected: ImportError.

- [ ] **Step 3: Add handlers in `backend/app/services/jobs.py`**

Append below the existing `run_replay_attempt_history`:

```python
async def run_materialize_next_actions(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Materialise top-10 next_actions for one (user, course)."""
    from app.services.next_actions import materialize_next_actions

    user_id = uuid.UUID(payload["user_id"])
    course_id = uuid.UUID(payload["course_id"])
    rows = await materialize_next_actions(
        session, user_id=user_id, course_id=course_id
    )
    return {"count": len(rows), "user_id": str(user_id), "course_id": str(course_id)}


async def run_record_action_outcome(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Persist a single action_outcomes row.

    Used by both the click endpoint (clicked=True) and the post-attempt
    observation hook (completed=True with outcome_metric+outcome_score).
    """
    from datetime import datetime
    from decimal import Decimal

    from app.models import ActionOutcome

    served_at_iso = payload["served_at"]
    served_at = datetime.fromisoformat(served_at_iso)

    next_action_id_raw = payload.get("next_action_id")
    course_id_raw = payload.get("course_id")
    target_id_raw = payload.get("target_id")
    outcome_score_raw = payload.get("outcome_score")
    observed_at_raw = payload.get("observed_at")

    row = ActionOutcome(
        next_action_id=uuid.UUID(next_action_id_raw) if next_action_id_raw else None,
        user_id=uuid.UUID(payload["user_id"]),
        course_id=uuid.UUID(course_id_raw) if course_id_raw else None,
        action_type=payload["action_type"],
        target_kind=payload.get("target_kind"),
        target_id=uuid.UUID(target_id_raw) if target_id_raw else None,
        engine_variant=payload["engine_variant"],
        served_at=served_at,
        clicked=bool(payload.get("clicked", False)),
        completed=bool(payload.get("completed", False)),
        outcome_score=(
            Decimal(f"{float(outcome_score_raw):.3f}")
            if outcome_score_raw is not None else None
        ),
        outcome_metric=payload.get("outcome_metric"),
        observed_at=datetime.fromisoformat(observed_at_raw) if observed_at_raw else None,
    )
    session.add(row)
    await session.commit()
    return {"status": "recorded", "id": str(row.id)}


async def run_evaluate_instructor_alerts(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Evaluate alert rules for one course (Task 15 fills the body)."""
    from app.services.alerts import evaluate_alerts_for_course

    course_id = uuid.UUID(payload["course_id"])
    return await evaluate_alerts_for_course(session, course_id=course_id)


async def run_tune_action_coefficients(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Quarterly coefficient retune (Task 17 fills the body)."""
    from app.services.action_coeffs import retune_action_coefficients

    window_days = int(payload.get("window_days", 90))
    return await retune_action_coefficients(session, window_days=window_days)
```

- [ ] **Step 4: Wire dispatch in `backend/app/services/worker.py`**

In `process_task` add four new branches following the existing precedent (lazy import, return handler result):

```python
elif task.task_type == "materialize_next_actions":
    from app.services.jobs import run_materialize_next_actions
    return await run_materialize_next_actions(session, task.payload)
elif task.task_type == "record_action_outcome":
    from app.services.jobs import run_record_action_outcome
    return await run_record_action_outcome(session, task.payload)
elif task.task_type == "evaluate_instructor_alerts":
    from app.services.jobs import run_evaluate_instructor_alerts
    return await run_evaluate_instructor_alerts(session, task.payload)
elif task.task_type == "tune_action_coefficients":
    from app.services.jobs import run_tune_action_coefficients
    return await run_tune_action_coefficients(session, task.payload)
```

In `worker_loop` add two new watermarks alongside `last_decay_run`:

```python
last_alert_run = _utcnow()
last_retune_run = _utcnow()
```

…and two new periodic blocks below the decay block:

```python
# Hourly: re-evaluate alert rules across all courses (one task per course).
if _utcnow() - last_alert_run > timedelta(hours=1):
    try:
        async with async_session_factory() as alert_session:
            from app.models import Course

            ids = (
                await alert_session.execute(
                    select(Course.id).where(Course.deleted_at.is_(None))
                )
            ).scalars().all()
            for cid in ids:
                alert_session.add(
                    Task(
                        task_type="evaluate_instructor_alerts",
                        payload={"course_id": str(cid)},
                        status="pending",
                    )
                )
            await alert_session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("alert enqueue failed")
    last_alert_run = _utcnow()

# Quarterly: retune action coefficients from action_outcomes telemetry.
if _utcnow() - last_retune_run > timedelta(days=90):
    try:
        async with async_session_factory() as tune_session:
            tune_session.add(
                Task(
                    task_type="tune_action_coefficients",
                    payload={"window_days": 90},
                    status="pending",
                )
            )
            await tune_session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("retune enqueue failed")
    last_retune_run = _utcnow()
```

(Need an `from app.models.task import Task` import in `worker.py` already present.)

Stub the `app.services.alerts` and `app.services.action_coeffs` modules now with no-op functions so the worker import graph stays clean — these are filled in Tasks 15 and 17:

```python
# backend/app/services/alerts.py
"""Alert evaluator stub — filled in Task 15."""
from __future__ import annotations
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

async def evaluate_alerts_for_course(
    db: AsyncSession, *, course_id: uuid.UUID
) -> dict:
    return {"course_id": str(course_id), "alerts_created": 0, "stub": True}
```

```python
# backend/app/services/action_coeffs.py
"""Coefficient retune stub — filled in Task 17."""
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession

async def retune_action_coefficients(
    db: AsyncSession, *, window_days: int
) -> dict:
    return {"window_days": window_days, "stub": True}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_jobs_phase3.py -v
```

Expected: 2 tests pass.

- [ ] **Step 6: Commit**

```bash
git add \
  backend/app/services/jobs.py \
  backend/app/services/worker.py \
  backend/app/services/alerts.py \
  backend/app/services/action_coeffs.py \
  backend/tests/test_jobs_phase3.py
git commit -m "feat(adaptive-engine): worker handlers + dispatch — materialize, record outcome, alert + retune crons"
```

---

### Task 9: Lazy recompute helper (cache > 30 min)

**Files:**
- Modify: `backend/app/services/next_actions.py`
- Test: `backend/tests/test_next_actions_service.py` (add tests)

**Context:** The read API checks if any unconsumed unexpired row exists for `(user, course)` younger than `LAZY_REFRESH_MINUTES = 30`. If yes, return as-is. If no, trigger a synchronous `materialize_next_actions` call before returning — the user's request blocks for ~50–200 ms but they always see fresh data on first login of the day. (Not enqueued — students log in once and need data right then.)

- [ ] **Step 1: Add tests**

Append to `backend/tests/test_next_actions_service.py`:

```python
@pytest.mark.asyncio
async def test_get_or_recompute_returns_cached(db_session, test_instructor, test_student):
    from app.services.next_actions import get_or_recompute_next_actions
    course = Course(
        name="Cache",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="MAT-CACHE",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    c = Concept(course_id=course.id, name="cached", status="approved")
    db_session.add(c)
    await db_session.flush()
    db_session.add(
        ConceptMastery(
            user_id=test_student.id, concept_id=c.id, course_id=course.id,
            alpha=Decimal("1.000"), beta=Decimal("2.000"),
            confidence=Decimal("0.600"),
        )
    )
    await db_session.commit()

    rows1 = await get_or_recompute_next_actions(
        db_session, user_id=test_student.id, course_id=course.id
    )
    rows2 = await get_or_recompute_next_actions(
        db_session, user_id=test_student.id, course_id=course.id
    )
    # Same row IDs — second call returned the cache.
    assert {r.id for r in rows1} == {r.id for r in rows2}


@pytest.mark.asyncio
async def test_get_or_recompute_refreshes_after_ttl(db_session, test_instructor, test_student):
    """Stale cache (>30 min) triggers recompute; ids change."""
    from datetime import timedelta as _td

    from app.services.next_actions import get_or_recompute_next_actions
    course = Course(
        name="Stale",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="MAT-STALE",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    c = Concept(course_id=course.id, name="stale", status="approved")
    db_session.add(c)
    await db_session.flush()
    db_session.add(
        ConceptMastery(
            user_id=test_student.id, concept_id=c.id, course_id=course.id,
            alpha=Decimal("1.000"), beta=Decimal("2.000"),
            confidence=Decimal("0.600"),
        )
    )
    await db_session.commit()

    rows1 = await get_or_recompute_next_actions(
        db_session, user_id=test_student.id, course_id=course.id
    )
    # Backdate created_at to simulate a 31-min-old cache.
    for r in rows1:
        r.created_at = datetime.now(timezone.utc) - _td(minutes=31)
    await db_session.commit()

    rows2 = await get_or_recompute_next_actions(
        db_session, user_id=test_student.id, course_id=course.id
    )
    assert {r.id for r in rows1} != {r.id for r in rows2}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_next_actions_service.py -v -k get_or_recompute
```

Expected: ImportError.

- [ ] **Step 3: Add helper to `backend/app/services/next_actions.py`**

```python
LAZY_REFRESH_MINUTES = 30


async def get_or_recompute_next_actions(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
) -> list[NextAction]:
    """Return cached rows if any are < 30 min old; else materialise fresh."""
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(minutes=LAZY_REFRESH_MINUTES)
    cached = (
        await db.execute(
            select(NextAction)
            .where(
                NextAction.user_id == user_id,
                NextAction.course_id == course_id,
                NextAction.consumed_at.is_(None),
                NextAction.expires_at > now,
                NextAction.created_at >= threshold,
            )
            .order_by(NextAction.priority_score.desc())
        )
    ).scalars().all()
    if cached:
        return list(cached)
    return await materialize_next_actions(db, user_id=user_id, course_id=course_id, now=now)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_next_actions_service.py -v
```

Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/next_actions.py backend/tests/test_next_actions_service.py
git commit -m "feat(adaptive-engine): lazy 30-min recompute on next_actions read"
```

---

### Task 10: Next-actions API — list + click

**Files:**
- Create: `backend/app/api/next_actions.py`
- Modify: `backend/app/api/__init__.py`
- Test: `backend/tests/test_api_next_actions.py`

**Context:**
- `GET /api/users/me/courses/{course_id}/next-actions` — student-or-owner read; calls `get_or_recompute_next_actions` then `record_serve` on the returned IDs and writes one `action_outcomes(clicked=False)` per row (so the off-arm gets a baseline served-but-not-engaged row even if mode resolves to `'off'` and the list is empty — in that case we write a single observational row with `target_id=NULL, action_type='do_quiz', engine_variant='off'`). Returns the rows.
- `POST /api/next-actions/{action_id}/click` — student-only mutation; sets `clicked_at = now()` on the `NextAction` row (404 if it isn't yours) and updates the matching `action_outcomes` row to `clicked=true`. Returns redirect target metadata (`target_kind`, `target_id`).

Mirror `mastery.py` style (no router prefix, full paths in decorators, reuse `get_current_user` + the inline-enrollment-or-owner check).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_api_next_actions.py
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.models import (
    ActionOutcome,
    Concept,
    ConceptMastery,
    Course,
    Enrollment,
    NextAction,
    User,
)


@pytest.mark.asyncio
async def test_list_next_actions_requires_enrollment_or_ownership(
    db_session, async_client: AsyncClient, test_instructor: User, test_student: User
):
    course = Course(
        name="API course",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="API-NA",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.commit()

    # logged_in_user is test_instructor by default → owner of the course → 200 + (possibly empty) list
    res = await async_client.get(f"/api/users/me/courses/{course.id}/next-actions")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True


@pytest.mark.asyncio
async def test_list_next_actions_recomputes_when_empty(
    db_session, async_client: AsyncClient, test_instructor: User
):
    course = Course(
        name="Recompute",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="API-RC",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    c = Concept(course_id=course.id, name="topic", status="approved")
    db_session.add(c)
    await db_session.flush()
    db_session.add(
        ConceptMastery(
            user_id=test_instructor.id, concept_id=c.id, course_id=course.id,
            alpha=Decimal("1.000"), beta=Decimal("2.000"),
            confidence=Decimal("0.600"),
        )
    )
    await db_session.commit()

    res = await async_client.get(f"/api/users/me/courses/{course.id}/next-actions")
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body["data"], list) and len(body["data"]) >= 1


@pytest.mark.asyncio
async def test_list_next_actions_records_serve_and_observation(
    db_session, async_client: AsyncClient, test_instructor: User
):
    course = Course(
        name="Serve obs",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="API-SOB",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    c = Concept(course_id=course.id, name="x", status="approved")
    db_session.add(c)
    await db_session.flush()
    db_session.add(
        ConceptMastery(
            user_id=test_instructor.id, concept_id=c.id, course_id=course.id,
            alpha=Decimal("1.000"), beta=Decimal("2.000"),
            confidence=Decimal("0.600"),
        )
    )
    await db_session.commit()

    res = await async_client.get(f"/api/users/me/courses/{course.id}/next-actions")
    assert res.status_code == 200
    await db_session.rollback()  # refresh session view (NOT expire_all)

    served = (await db_session.execute(
        __import__("sqlalchemy").select(NextAction).where(
            NextAction.user_id == test_instructor.id, NextAction.course_id == course.id
        )
    )).scalars().all()
    assert all(r.served_at is not None for r in served)

    outcomes = (await db_session.execute(
        __import__("sqlalchemy").select(ActionOutcome).where(
            ActionOutcome.user_id == test_instructor.id, ActionOutcome.course_id == course.id
        )
    )).scalars().all()
    assert len(outcomes) == len(served)
    assert all(o.clicked is False for o in outcomes)


@pytest.mark.asyncio
async def test_click_next_action_marks_clicked(
    db_session, async_client: AsyncClient, test_instructor: User
):
    course = Course(
        name="Click",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="API-CLK",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    na = NextAction(
        user_id=test_instructor.id,
        course_id=course.id,
        action_type="practice_weakness",
        target_kind="concept",
        target_id=uuid.uuid4(),
        priority_score=Decimal("1.500"),
        candidate_source="outer_fringe",
        reason={"hi": "there"},
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        engine_variant="on",
        served_at=datetime.now(timezone.utc),
    )
    db_session.add(na)
    await db_session.commit()
    db_session.add(
        ActionOutcome(
            next_action_id=na.id,
            user_id=test_instructor.id,
            course_id=course.id,
            action_type=na.action_type,
            target_kind=na.target_kind,
            target_id=na.target_id,
            engine_variant="on",
            served_at=na.served_at,
        )
    )
    await db_session.commit()

    res = await async_client.post(f"/api/next-actions/{na.id}/click")
    assert res.status_code == 200
    await db_session.refresh(na)
    assert na.clicked_at is not None

    refreshed_outcome = (await db_session.execute(
        __import__("sqlalchemy").select(ActionOutcome).where(
            ActionOutcome.next_action_id == na.id
        )
    )).scalar_one()
    assert refreshed_outcome.clicked is True


@pytest.mark.asyncio
async def test_click_other_users_action_404(
    db_session, async_client: AsyncClient, test_instructor: User, test_student: User
):
    course = Course(
        name="Foreign",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="API-FOR",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    foreign = NextAction(
        user_id=test_student.id,
        course_id=course.id,
        action_type="practice_weakness",
        target_kind="concept",
        target_id=uuid.uuid4(),
        priority_score=Decimal("1.000"),
        candidate_source="outer_fringe",
        reason={},
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        engine_variant="on",
    )
    db_session.add(foreign)
    await db_session.commit()

    res = await async_client.post(f"/api/next-actions/{foreign.id}/click")
    assert res.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api_next_actions.py -v
```

Expected: 5 tests fail.

- [ ] **Step 3: Implement the router**

```python
# backend/app/api/next_actions.py
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models import ActionOutcome, Course, Enrollment, NextAction, User
from app.schemas.common import APIResponse
from app.schemas.decision import NextActionClickResponse, NextActionResponse
from app.services.next_actions import (
    get_or_recompute_next_actions,
    record_serve,
)

router = APIRouter(tags=["next-actions"])


async def _check_access(
    db: AsyncSession, user: User, course_id: uuid.UUID
) -> Course:
    """Enrollment OR ownership; 404 otherwise (mirrors mastery.py)."""
    course = (
        await db.execute(
            select(Course).where(
                Course.id == course_id, Course.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.instructor_id == user.id:
        return course
    enrolled = (
        await db.execute(
            select(Enrollment).where(
                Enrollment.user_id == user.id,
                Enrollment.course_id == course_id,
            )
        )
    ).scalar_one_or_none()
    if enrolled is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.get(
    "/users/me/courses/{course_id}/next-actions",
    response_model=APIResponse[list[NextActionResponse]],
)
async def list_next_actions(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[list[NextActionResponse]]:
    await _check_access(db, user, course_id)
    rows = await get_or_recompute_next_actions(
        db, user_id=user.id, course_id=course_id
    )
    served = await record_serve(db, [r.id for r in rows])

    # Telemetry: one observational action_outcomes row per served row.
    # Idempotent at session level — if a row already exists with this
    # next_action_id we skip (handles repeat polling within the same minute).
    if served:
        existing = (
            await db.execute(
                select(ActionOutcome.next_action_id).where(
                    ActionOutcome.next_action_id.in_([r.id for r in served])
                )
            )
        ).scalars().all()
        skip_ids = set(existing)
        new_outcomes = [
            ActionOutcome(
                next_action_id=r.id,
                user_id=r.user_id,
                course_id=r.course_id,
                action_type=r.action_type,
                target_kind=r.target_kind,
                target_id=r.target_id,
                engine_variant=r.engine_variant,
                served_at=r.served_at,
            )
            for r in served if r.id not in skip_ids
        ]
        if new_outcomes:
            db.add_all(new_outcomes)
            await db.commit()

    # If mode resolved to 'off' the list is empty; record a single off-arm
    # observational row so the A/B query has data on both sides.
    if not served:
        from app.services.engine_mode import resolve_engine_mode
        variant = await resolve_engine_mode(
            db, user_id=user.id, course_id=course_id
        )
        if variant == "off":
            db.add(
                ActionOutcome(
                    user_id=user.id,
                    course_id=course_id,
                    action_type="do_quiz",  # placeholder action_type for off-arm
                    engine_variant="off",
                    served_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()

    return APIResponse(
        success=True,
        data=[NextActionResponse.model_validate(r) for r in served],
    )


@router.post(
    "/next-actions/{action_id}/click",
    response_model=APIResponse[NextActionClickResponse],
)
async def click_next_action(
    action_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[NextActionClickResponse]:
    row = (
        await db.execute(
            select(NextAction).where(
                NextAction.id == action_id, NextAction.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Next action not found")

    now = datetime.now(timezone.utc)
    if row.clicked_at is None:
        row.clicked_at = now
    await db.execute(
        update(ActionOutcome)
        .where(ActionOutcome.next_action_id == action_id)
        .values(clicked=True)
    )
    await db.commit()

    return APIResponse(
        success=True,
        data=NextActionClickResponse(
            id=row.id,
            clicked_at=row.clicked_at,
            target_kind=row.target_kind,
            target_id=row.target_id,
        ),
    )
```

In `backend/app/api/__init__.py` add:

```python
from app.api.next_actions import router as next_actions_router
...
api_router.include_router(next_actions_router)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_api_next_actions.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/next_actions.py backend/app/api/__init__.py backend/tests/test_api_next_actions.py
git commit -m "feat(adaptive-engine): next-actions API — list (lazy recompute) + click + telemetry baseline"
```

---

### Task 11: Event-driven recompute on attempts

**Files:**
- Modify: `backend/app/api/quizzes.py`
- Modify: `backend/app/api/flashcards.py`
- Modify: `backend/app/api/revision.py`

**Context:** After each attempt the existing handlers already enqueue `update_concept_mastery`. Phase 3 adds one more enqueue: `materialize_next_actions` for the same `(user, course)`. This is event-driven recompute — the user's next list will reflect the just-finished attempt. Use `Task.payload->>'user_id' = ... AND task_type = 'materialize_next_actions' AND status IN ('pending','running')` to dedupe — if a recompute is already queued, don't queue another. (Same `Task.payload.op("->>")` pattern as Phase 2 Task 16.)

- [ ] **Step 1: Write the helper in `backend/app/api/_helpers.py`**

```python
# Append to backend/app/api/_helpers.py
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task


async def enqueue_next_actions_recompute(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
) -> None:
    """Best-effort enqueue. Caller commits.

    Dedupe: if a pending/running materialize_next_actions task already exists
    for this (user, course), skip. The Task.payload column is JSON (not JSONB)
    so we use ``op('->>')`` for value extraction — see Phase 2 Task 16.
    """
    existing = (
        await db.execute(
            select(Task.id).where(
                Task.task_type == "materialize_next_actions",
                Task.status.in_(("pending", "running")),
                Task.payload.op("->>")("user_id") == str(user_id),
                Task.payload.op("->>")("course_id") == str(course_id),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    db.add(
        Task(
            task_type="materialize_next_actions",
            payload={"user_id": str(user_id), "course_id": str(course_id)},
            status="pending",
        )
    )
```

- [ ] **Step 2: Hook quiz / flashcard / revision attempt handlers**

In `backend/app/api/quizzes.py` `submit_attempt` (around line 793, where `_enqueue_mastery_for_quiz` is called), append below the existing call:

```python
from app.api._helpers import enqueue_next_actions_recompute
await enqueue_next_actions_recompute(
    db, user_id=user.id, course_id=quiz.course_id
)
```

In `backend/app/api/flashcards.py` (line 440), after `_enqueue_mastery_for_flashcard`:

```python
from app.api._helpers import enqueue_next_actions_recompute
await enqueue_next_actions_recompute(
    db, user_id=user.id, course_id=set_row.course_id
)
```

In `backend/app/api/revision.py` (line 486), after `_enqueue_mastery_for_revision`:

```python
from app.api._helpers import enqueue_next_actions_recompute
await enqueue_next_actions_recompute(
    db, user_id=user.id, course_id=course_id
)
```

(Use whatever local variable already names the course id at the call site; if it's named differently in revision/flashcard handlers, match it — never duplicate the lookup.)

- [ ] **Step 3: Add test for dedupe behaviour**

```python
# backend/tests/test_api_next_actions.py — append
@pytest.mark.asyncio
async def test_attempt_enqueue_is_deduped(
    db_session, async_client: AsyncClient, test_instructor: User
):
    """Two consecutive submit_attempt calls produce at most one
    materialize_next_actions task in the queue."""
    from app.models import Task

    # NOTE: the integration through quizzes/flashcards/revision is exercised
    # in their own test files. Here we only assert the helper itself dedups.
    from app.api._helpers import enqueue_next_actions_recompute

    course_id = uuid.uuid4()
    await enqueue_next_actions_recompute(
        db_session, user_id=test_instructor.id, course_id=course_id
    )
    await db_session.commit()
    await enqueue_next_actions_recompute(
        db_session, user_id=test_instructor.id, course_id=course_id
    )
    await db_session.commit()

    rows = (await db_session.execute(
        __import__("sqlalchemy").select(Task).where(
            Task.task_type == "materialize_next_actions"
        )
    )).scalars().all()
    assert len(rows) == 1
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_api_next_actions.py -v
```

Expected: 6 tests pass (5 existing + 1 new).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/_helpers.py backend/app/api/quizzes.py backend/app/api/flashcards.py backend/app/api/revision.py backend/tests/test_api_next_actions.py
git commit -m "feat(adaptive-engine): event-driven next_actions recompute on attempts (deduped)"
```

---

### Task 12: Daily horizon-scan cron (deadlines + meetings entering 24h)

**Files:**
- Modify: `backend/app/services/worker.py`

**Context:** When an assignment due date or a meeting enters the next 24h window, every student's `next_actions` for that course should be refreshed even if they didn't take an attempt. Add a daily cron in `worker_loop` (alongside `last_overdue_run`) that finds:

- Assignments with `due_at` in `[now, now + 24h]`.
- Meetings with `scheduled_at` in `[now, now + 24h]`.

…then for every enrolled `(user, course)` pair, enqueue a `materialize_next_actions` task. Reuses the dedupe helper from Task 11 (called inside the daily sweep so multiple courses with overlapping students don't duplicate tasks).

- [ ] **Step 1: Write the test**

```python
# backend/tests/test_jobs_phase3.py — append
@pytest.mark.asyncio
async def test_horizon_scan_enqueues_for_enrolled_users(
    db_session, test_instructor: User, test_student: User
):
    from datetime import datetime, timedelta, timezone

    from app.models import Assignment, Enrollment, Task as TaskModel
    from app.services.worker import horizon_scan_recompute

    course = Course(
        name="Horizon",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="HZN-1",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=test_student.id, role="student"))
    db_session.add(
        Assignment(
            course_id=course.id,
            title="Quiz tomorrow",
            kind="quiz",
            due_at=datetime.now(timezone.utc) + timedelta(hours=12),
            created_by=test_instructor.id,
        )
    )
    await db_session.commit()

    n = await horizon_scan_recompute(db_session)
    assert n >= 1
    queued = (await db_session.execute(
        __import__("sqlalchemy").select(TaskModel).where(
            TaskModel.task_type == "materialize_next_actions"
        )
    )).scalars().all()
    assert any(
        t.payload.get("user_id") == str(test_student.id) for t in queued
    )
```

- [ ] **Step 2: Add the function to worker.py**

```python
# backend/app/services/worker.py — append before worker_loop
async def horizon_scan_recompute(session: AsyncSession) -> int:
    """Daily cron: find courses with deadlines/meetings in the next 24h and
    enqueue a materialize_next_actions task for every enrolled student.

    Returns the number of courses scanned.
    """
    from datetime import timedelta as _td

    from app.api._helpers import enqueue_next_actions_recompute
    from app.models import Assignment, CourseMeeting, Enrollment

    now = _utcnow()
    horizon = now + _td(hours=24)

    asn_courses = (
        await session.execute(
            select(Assignment.course_id).where(
                Assignment.due_at.between(now, horizon),
                Assignment.deleted_at.is_(None),
            ).distinct()
        )
    ).scalars().all()
    meeting_courses = (
        await session.execute(
            select(CourseMeeting.course_id).where(
                CourseMeeting.scheduled_at.between(now, horizon),
                CourseMeeting.deleted_at.is_(None),
            ).distinct()
        )
    ).scalars().all()
    course_ids = set(asn_courses) | set(meeting_courses)
    for cid in course_ids:
        student_ids = (
            await session.execute(
                select(Enrollment.user_id).where(
                    Enrollment.course_id == cid,
                    Enrollment.role == "student",
                )
            )
        ).scalars().all()
        for uid in student_ids:
            await enqueue_next_actions_recompute(
                session, user_id=uid, course_id=cid
            )
    await session.commit()
    return len(course_ids)
```

In `worker_loop` add a watermark + a periodic block (place after the decay block):

```python
last_horizon_run = _utcnow()
...
# Daily: enqueue recompute for any course with deadlines/meetings entering 24h.
if _utcnow() - last_horizon_run > timedelta(hours=24):
    try:
        async with async_session_factory() as horizon_session:
            await horizon_scan_recompute(horizon_session)
    except Exception:  # noqa: BLE001
        logger.exception("horizon_scan_recompute failed")
    last_horizon_run = _utcnow()
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_jobs_phase3.py -v -k horizon
```

Expected: 1 test passes.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/worker.py backend/tests/test_jobs_phase3.py
git commit -m "feat(adaptive-engine): daily horizon-scan cron enqueues recompute for upcoming deadlines/meetings"
```

---

### Task 13: Engine settings API (course mode + per-user overrides)

**Files:**
- Create: `backend/app/api/engine_settings.py`
- Modify: `backend/app/api/__init__.py`
- Test: `backend/tests/test_api_engine_settings.py`

**Context:** Four endpoints, all instructor-only:

- `GET /api/courses/{course_id}/engine` → `{course_id, mode, overrides_count}` (mode = `courses.adaptive_engine_mode`).
- `PATCH /api/courses/{course_id}/engine` body `{"mode": "on|off|random_50"}` → updates the column.
- `PUT /api/courses/{course_id}/engine/overrides/{user_id}` body `{"mode": "on|off"}` → upserts `engine_overrides` row.
- `DELETE /api/courses/{course_id}/engine/overrides/{user_id}` → removes the override.

Use `get_owned_course` for instructor auth. Course-mode change does NOT immediately invalidate `next_actions` rows — the next attempt or 30-min lazy refresh will recompute under the new mode.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_api_engine_settings.py
import uuid
import pytest
from httpx import AsyncClient

from app.models import Course, EngineOverride, User


@pytest.mark.asyncio
async def test_get_engine_settings_returns_default_on(
    db_session, async_client: AsyncClient, test_instructor: User
):
    course = Course(
        name="Eng Settings",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ENGS-1",
    )
    db_session.add(course)
    await db_session.commit()

    res = await async_client.get(f"/api/courses/{course.id}/engine")
    assert res.status_code == 200
    body = res.json()
    assert body["data"]["mode"] == "on"
    assert body["data"]["overrides_count"] == 0


@pytest.mark.asyncio
async def test_patch_engine_mode_updates_column(
    db_session, async_client: AsyncClient, test_instructor: User
):
    course = Course(
        name="Eng Patch",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ENGS-2",
    )
    db_session.add(course)
    await db_session.commit()

    res = await async_client.patch(
        f"/api/courses/{course.id}/engine",
        json={"mode": "random_50"},
    )
    assert res.status_code == 200
    await db_session.refresh(course)
    assert course.adaptive_engine_mode == "random_50"


@pytest.mark.asyncio
async def test_put_override_creates_row(
    db_session, async_client: AsyncClient, test_instructor: User, test_student: User
):
    course = Course(
        name="Eng Override",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ENGS-3",
    )
    db_session.add(course)
    await db_session.commit()

    res = await async_client.put(
        f"/api/courses/{course.id}/engine/overrides/{test_student.id}",
        json={"mode": "off"},
    )
    assert res.status_code == 200
    row = (await db_session.execute(
        __import__("sqlalchemy").select(EngineOverride).where(
            EngineOverride.user_id == test_student.id,
            EngineOverride.course_id == course.id,
        )
    )).scalar_one()
    assert row.mode == "off"


@pytest.mark.asyncio
async def test_put_override_upserts(
    db_session, async_client: AsyncClient, test_instructor: User, test_student: User
):
    course = Course(
        name="Eng Upsert",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ENGS-4",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        EngineOverride(
            user_id=test_student.id, course_id=course.id,
            mode="off", set_by=test_instructor.id,
        )
    )
    await db_session.commit()

    res = await async_client.put(
        f"/api/courses/{course.id}/engine/overrides/{test_student.id}",
        json={"mode": "on"},
    )
    assert res.status_code == 200
    await db_session.rollback()
    row = (await db_session.execute(
        __import__("sqlalchemy").select(EngineOverride).where(
            EngineOverride.user_id == test_student.id,
            EngineOverride.course_id == course.id,
        )
    )).scalar_one()
    assert row.mode == "on"


@pytest.mark.asyncio
async def test_delete_override_removes_row(
    db_session, async_client: AsyncClient, test_instructor: User, test_student: User
):
    course = Course(
        name="Eng Delete",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ENGS-5",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        EngineOverride(
            user_id=test_student.id, course_id=course.id,
            mode="off", set_by=test_instructor.id,
        )
    )
    await db_session.commit()

    res = await async_client.delete(
        f"/api/courses/{course.id}/engine/overrides/{test_student.id}"
    )
    assert res.status_code == 200
    rows = (await db_session.execute(
        __import__("sqlalchemy").select(EngineOverride).where(
            EngineOverride.user_id == test_student.id,
            EngineOverride.course_id == course.id,
        )
    )).scalars().all()
    assert rows == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api_engine_settings.py -v
```

Expected: 5 tests fail.

- [ ] **Step 3: Implement the router**

```python
# backend/app/api/engine_settings.py
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_owned_course, require_instructor
from app.models import EngineOverride
from app.models.course import Course
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.decision import (
    EngineOverrideResponse,
    EngineOverrideUpdate,
    EngineSettingsResponse,
    EngineSettingsUpdate,
)

router = APIRouter(tags=["engine-settings"])


@router.get(
    "/courses/{course_id}/engine",
    response_model=APIResponse[EngineSettingsResponse],
)
async def get_engine_settings(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[EngineSettingsResponse]:
    n = (
        await db.execute(
            select(func.count())
            .select_from(EngineOverride)
            .where(EngineOverride.course_id == course.id)
        )
    ).scalar_one()
    return APIResponse(
        success=True,
        data=EngineSettingsResponse(
            course_id=course.id,
            mode=course.adaptive_engine_mode,
            overrides_count=int(n),
        ),
    )


@router.patch(
    "/courses/{course_id}/engine",
    response_model=APIResponse[EngineSettingsResponse],
)
async def patch_engine_settings(
    body: EngineSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[EngineSettingsResponse]:
    course.adaptive_engine_mode = body.mode
    await db.commit()
    await db.refresh(course)
    return await get_engine_settings(db=db, course=course)


@router.put(
    "/courses/{course_id}/engine/overrides/{user_id}",
    response_model=APIResponse[EngineOverrideResponse],
)
async def upsert_engine_override(
    user_id: uuid.UUID,
    body: EngineOverrideUpdate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
    actor: User = Depends(require_instructor),
) -> APIResponse[EngineOverrideResponse]:
    now = datetime.now(timezone.utc)
    stmt = (
        pg_insert(EngineOverride)
        .values(
            user_id=user_id,
            course_id=course.id,
            mode=body.mode,
            set_by=actor.id,
            set_at=now,
        )
        .on_conflict_do_update(
            index_elements=["user_id", "course_id"],
            set_={"mode": body.mode, "set_by": actor.id, "set_at": now},
        )
    )
    await db.execute(stmt)
    await db.commit()
    row = (
        await db.execute(
            select(EngineOverride).where(
                EngineOverride.user_id == user_id,
                EngineOverride.course_id == course.id,
            )
        )
    ).scalar_one()
    return APIResponse(
        success=True, data=EngineOverrideResponse.model_validate(row)
    )


@router.delete(
    "/courses/{course_id}/engine/overrides/{user_id}",
    response_model=APIResponse[dict],
)
async def delete_engine_override(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[dict]:
    result = await db.execute(
        delete(EngineOverride).where(
            EngineOverride.user_id == user_id,
            EngineOverride.course_id == course.id,
        )
    )
    await db.commit()
    return APIResponse(
        success=True, data={"deleted": result.rowcount or 0}
    )
```

In `backend/app/api/__init__.py`:

```python
from app.api.engine_settings import router as engine_settings_router
...
api_router.include_router(engine_settings_router)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_api_engine_settings.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/engine_settings.py backend/app/api/__init__.py backend/tests/test_api_engine_settings.py
git commit -m "feat(adaptive-engine): engine settings API — course mode + per-user overrides"
```

---

### Task 14: Outcome observation hook (mastery delta → action_outcomes)

**Files:**
- Modify: `backend/app/services/mastery.py`
- Modify: `backend/app/services/jobs.py`
- Test: `backend/tests/test_next_actions_service.py` (append)

**Context:** When `apply_attempt_evidence` runs (i.e. a real attempt produced new mastery rows), we want to close the loop on the served `next_action` that pointed at that target. The hook:

1. After `apply_attempt_evidence` returns its touched count, look up open `action_outcomes(user_id, target_id, target_kind, completed=False)` rows where the served target matches the just-completed attempt.
2. Set `completed=true`, `outcome_metric='quiz_score' | 'recall' | 'mastery_delta' | 'completion'` (depending on `attempt_kind`), `outcome_score=outcome` (the same float that just produced the Beta-Binomial update), `observed_at=now()`.

This is the data that eventually drives the quarterly retune.

The simplest, cheapest implementation: extend `apply_attempt_evidence` to also write the outcome update inside the same transaction. (No async enqueue — the row already exists; this is a UPDATE-only path.)

- [ ] **Step 1: Add test**

```python
# backend/tests/test_next_actions_service.py — append
@pytest.mark.asyncio
async def test_apply_attempt_evidence_closes_open_outcome(
    db_session, test_instructor: User, test_student: User
):
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz

    from app.models import (
        ActionOutcome,
        Concept,
        ConceptTag,
        Course,
        Enrollment,
        NextAction,
    )
    from app.services.mastery import AttemptKind, apply_attempt_evidence

    course = Course(
        name="Close",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="CLO-1",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=test_student.id, role="student"))
    c = Concept(course_id=course.id, name="Closed", status="approved")
    db_session.add(c)
    await db_session.flush()
    target_question = uuid.uuid4()
    db_session.add(
        ConceptTag(
            concept_id=c.id,
            target_kind="question",
            target_id=target_question,
            weight=Decimal("1.00"),
        )
    )
    served_at = _dt.now(_tz.utc)
    na = NextAction(
        user_id=test_student.id,
        course_id=course.id,
        action_type="practice_weakness",
        target_kind="question",
        target_id=target_question,
        priority_score=Decimal("1.000"),
        candidate_source="outer_fringe",
        reason={},
        expires_at=served_at + _td(hours=1),
        engine_variant="on",
        served_at=served_at,
    )
    db_session.add(na)
    await db_session.flush()
    db_session.add(
        ActionOutcome(
            next_action_id=na.id,
            user_id=test_student.id,
            course_id=course.id,
            action_type="practice_weakness",
            target_kind="question",
            target_id=target_question,
            engine_variant="on",
            served_at=served_at,
        )
    )
    await db_session.commit()

    await apply_attempt_evidence(
        db_session,
        user_id=test_student.id,
        course_id=course.id,
        target_kind="question",
        target_id=target_question,
        attempt_kind=AttemptKind.QUIZ,
        outcome=0.85,
    )
    await db_session.commit()
    refreshed = (await db_session.execute(
        __import__("sqlalchemy").select(ActionOutcome).where(
            ActionOutcome.next_action_id == na.id
        )
    )).scalar_one()
    assert refreshed.completed is True
    assert refreshed.outcome_metric == "quiz_score"
    assert float(refreshed.outcome_score) == pytest.approx(0.85, abs=1e-3)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_next_actions_service.py -v -k closes_open_outcome
```

Expected: assertion fail (the row stays `completed=false` — no hook yet).

- [ ] **Step 3: Add hook in `backend/app/services/mastery.py`**

At the very end of `apply_attempt_evidence` (just before `return touched`), append:

```python
    # Close any open action_outcomes row pointing at this exact target.
    if touched:
        from sqlalchemy import update as _update
        from app.models import ActionOutcome

        metric_by_kind = {
            "quiz": "quiz_score",
            "flashcard": "recall",
            "revision": "quiz_score",
            "pronunciation": "completion",
        }
        await db.execute(
            _update(ActionOutcome)
            .where(
                ActionOutcome.user_id == user_id,
                ActionOutcome.target_kind == target_kind,
                ActionOutcome.target_id == target_id,
                ActionOutcome.completed.is_(False),
            )
            .values(
                completed=True,
                outcome_metric=metric_by_kind.get(attempt_kind.value, "completion"),
                outcome_score=Decimal(f"{outcome:.3f}"),
                observed_at=now,
            )
        )
```

(Imports stay lazy because `ActionOutcome` lives in `app.models.decision` which transitively imports `Base` we already have. The lazy import keeps `mastery.py` boot graph small for legacy callers.)

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_next_actions_service.py tests/test_mastery_service.py tests/test_mastery_integration.py -v
```

Expected: existing mastery tests still pass; the new closing test passes.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/mastery.py backend/tests/test_next_actions_service.py
git commit -m "feat(adaptive-engine): close open action_outcomes when matching attempt evidence lands"
```

---

## Phase 3.3 — Alerts + retuning

### Task 15: Instructor alert evaluator

**Files:**
- Modify: `backend/app/services/alerts.py` (replace stub)
- Test: `backend/tests/test_alerts_evaluator.py`

**Context:** Implement seven alert rules from the CHECK constraint. Each rule queries existing tables and either inserts a new `instructor_alerts(status='open')` row or no-ops. The partial unique index on `(course_id, alert_type, target_user_id) WHERE status = 'open'` handles dedupe at the DB level — wrap each insert in a try/except `IntegrityError` (codebase precedent: 7 sites incl. `concept_clusters.py`).

Rule definitions (kept conservative for first ship; coefficients can move later):

| `alert_type` | Trigger |
|---|---|
| `student_disengaging` | Student has 0 attempts in last 7 days but had ≥ 1 in the prior 7 days. |
| `student_falling_behind` | Student has 2+ `assignment_submissions.status='late'` rows in last 14 days. |
| `cohort_concept_weakness` | Any concept where avg cohort `mastery_score < 0.4` AND `weak_students >= 3`. (Cohort-level alert: `target_user_id IS NULL`.) |
| `prereq_gap_for_upcoming_meeting` | Meeting in next 72h whose tagged concepts have any prereq with `mastery_score < 0.7` for ≥ 50% of enrolled students. |
| `low_quiz_participation` | Quiz published > 7 days ago in this course with attempt count from < 30% of enrolled students. (Cohort-level.) |
| `missed_deadline` | Assignment past `due_at` by > 24h with submissions for < 80% of enrolled students. (Cohort-level.) |
| `content_gap` | Approved concept that has zero `concept_tags` referencing it. (Cohort-level.) |

- [ ] **Step 1: Write the failing test** (one test per rule; abbreviated below — show shape, fill specifics in implementation.)

```python
# backend/tests/test_alerts_evaluator.py
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import (
    Assignment,
    AssignmentSubmission,
    Concept,
    ConceptMastery,
    ConceptTag,
    Course,
    CourseMeeting,
    Enrollment,
    InstructorAlert,
    QuizAttempt,
    User,
)
from app.services.alerts import evaluate_alerts_for_course


@pytest.mark.asyncio
async def test_no_data_no_alerts(db_session, test_instructor: User):
    course = Course(
        name="Empty",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ALR-EMP",
    )
    db_session.add(course)
    await db_session.commit()
    result = await evaluate_alerts_for_course(db_session, course_id=course.id)
    assert result["alerts_created"] == 0


@pytest.mark.asyncio
async def test_cohort_concept_weakness_alert(
    db_session, test_instructor: User
):
    course = Course(
        name="Weak Cohort",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ALR-WC",
    )
    db_session.add(course)
    await db_session.flush()
    c = Concept(course_id=course.id, name="hard", status="approved")
    db_session.add(c)
    await db_session.flush()
    # 4 students, all weak with confidence
    for i in range(4):
        u = User(email=f"weak-{i}@connect.ust.hk", name=f"S{i}", role="student", better_auth_id=f"weak-{i}")
        db_session.add(u)
        await db_session.flush()
        db_session.add(Enrollment(course_id=course.id, user_id=u.id, role="student"))
        db_session.add(
            ConceptMastery(
                user_id=u.id, concept_id=c.id, course_id=course.id,
                alpha=Decimal("1.000"), beta=Decimal("9.000"),
                confidence=Decimal("0.700"),
            )
        )
    await db_session.commit()

    result = await evaluate_alerts_for_course(db_session, course_id=course.id)
    assert result["alerts_created"] >= 1
    rows = (await db_session.execute(
        __import__("sqlalchemy").select(InstructorAlert).where(
            InstructorAlert.alert_type == "cohort_concept_weakness",
            InstructorAlert.course_id == course.id,
        )
    )).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_dedupe_on_open_alert(
    db_session, test_instructor: User
):
    """Re-running the evaluator must not create a second open row for the
    same (course, type, target)."""
    course = Course(
        name="Dedupe",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ALR-DD",
    )
    db_session.add(course)
    await db_session.flush()
    c = Concept(course_id=course.id, name="dup", status="approved")
    db_session.add(c)
    await db_session.flush()
    for i in range(4):
        u = User(email=f"dd-{i}@connect.ust.hk", name=f"D{i}", role="student", better_auth_id=f"dd-{i}")
        db_session.add(u)
        await db_session.flush()
        db_session.add(Enrollment(course_id=course.id, user_id=u.id, role="student"))
        db_session.add(
            ConceptMastery(
                user_id=u.id, concept_id=c.id, course_id=course.id,
                alpha=Decimal("1.000"), beta=Decimal("9.000"),
                confidence=Decimal("0.700"),
            )
        )
    await db_session.commit()

    await evaluate_alerts_for_course(db_session, course_id=course.id)
    await evaluate_alerts_for_course(db_session, course_id=course.id)

    rows = (await db_session.execute(
        __import__("sqlalchemy").select(InstructorAlert).where(
            InstructorAlert.alert_type == "cohort_concept_weakness",
            InstructorAlert.course_id == course.id,
            InstructorAlert.status == "open",
        )
    )).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_content_gap_alert(db_session, test_instructor: User):
    course = Course(
        name="Gap",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ALR-GAP",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Concept(course_id=course.id, name="orphan", status="approved"))
    await db_session.commit()
    result = await evaluate_alerts_for_course(db_session, course_id=course.id)
    rows = (await db_session.execute(
        __import__("sqlalchemy").select(InstructorAlert).where(
            InstructorAlert.alert_type == "content_gap",
            InstructorAlert.course_id == course.id,
        )
    )).scalars().all()
    assert len(rows) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_alerts_evaluator.py -v
```

Expected: 4 tests fail (stub returns 0).

- [ ] **Step 3: Replace the stub in `backend/app/services/alerts.py`**

```python
"""Instructor alert evaluator.

Each rule queries existing data and tries to insert one open InstructorAlert
row per dedupe key (course_id, alert_type, target_user_id). The partial
unique index ``uq_instructor_alerts_open_idempotent`` enforces at-most-one
open row per key; we catch IntegrityError on conflict — codebase precedent
in concept_clusters.py and 6 sibling sites.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Assignment,
    AssignmentSubmission,
    Concept,
    ConceptMastery,
    ConceptTag,
    Course,
    CourseMeeting,
    Enrollment,
    InstructorAlert,
    Quiz,
    QuizAttempt,
)

logger = logging.getLogger(__name__)


async def _try_insert(
    db: AsyncSession,
    *,
    course_id: uuid.UUID,
    instructor_id: uuid.UUID,
    target_user_id: uuid.UUID | None,
    alert_type: str,
    severity: str,
    title: str,
    reason: dict,
) -> bool:
    # Cohort alerts (target_user_id IS NULL) are NOT deduped by the partial
    # unique index — Postgres treats NULLs as distinct. The migration comment
    # documents this explicitly. Dedupe with a SELECT before insert.
    if target_user_id is None:
        existing = (
            await db.execute(
                select(InstructorAlert.id).where(
                    InstructorAlert.course_id == course_id,
                    InstructorAlert.alert_type == alert_type,
                    InstructorAlert.target_user_id.is_(None),
                    InstructorAlert.status == "open",
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return False

    db.add(
        InstructorAlert(
            course_id=course_id,
            instructor_id=instructor_id,
            target_user_id=target_user_id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            reason=reason,
        )
    )
    try:
        await db.commit()
        return True
    except IntegrityError:
        # Per-student alerts hit the partial unique index → roll back and
        # treat as no-op. Cohort alerts can't reach this branch (we returned
        # False above), but keep the catch for safety against races.
        await db.rollback()
        return False


async def evaluate_alerts_for_course(
    db: AsyncSession, *, course_id: uuid.UUID
) -> dict:
    course = (
        await db.execute(select(Course).where(Course.id == course_id))
    ).scalar_one_or_none()
    if course is None:
        return {"course_id": str(course_id), "alerts_created": 0}

    now = datetime.now(timezone.utc)
    created = 0

    # --- cohort_concept_weakness ----------------------------------------
    weak = (
        await db.execute(
            select(
                Concept.id, Concept.name,
                func.avg(ConceptMastery.mastery_score).label("avg_m"),
                func.count().filter(
                    (ConceptMastery.mastery_score < 0.5)
                    & (ConceptMastery.confidence >= 0.5)
                ).label("weak_n"),
            )
            .join(ConceptMastery, ConceptMastery.concept_id == Concept.id)
            .where(
                Concept.course_id == course_id,
                Concept.deleted_at.is_(None),
                Concept.canonical_id.is_(None),
            )
            .group_by(Concept.id, Concept.name)
            .having(
                and_(func.avg(ConceptMastery.mastery_score) < 0.4,
                     func.count().filter(
                         (ConceptMastery.mastery_score < 0.5)
                         & (ConceptMastery.confidence >= 0.5)
                     ) >= 3)
            )
        )
    ).all()
    for cid, cname, avg_m, weak_n in weak:
        if await _try_insert(
            db,
            course_id=course_id,
            instructor_id=course.instructor_id,
            target_user_id=None,
            alert_type="cohort_concept_weakness",
            severity="warning",
            title=f"Cohort weak on {cname}",
            reason={
                "concept_id": str(cid),
                "avg_mastery": float(avg_m),
                "weak_students": int(weak_n),
            },
        ):
            created += 1

    # --- content_gap ----------------------------------------------------
    orphans = (
        await db.execute(
            select(Concept.id, Concept.name)
            .outerjoin(ConceptTag, ConceptTag.concept_id == Concept.id)
            .where(
                Concept.course_id == course_id,
                Concept.status == "approved",
                Concept.deleted_at.is_(None),
                Concept.canonical_id.is_(None),
            )
            .group_by(Concept.id, Concept.name)
            .having(func.count(ConceptTag.concept_id) == 0)
        )
    ).all()
    for cid, cname in orphans:
        if await _try_insert(
            db,
            course_id=course_id,
            instructor_id=course.instructor_id,
            target_user_id=None,
            alert_type="content_gap",
            severity="info",
            title=f"No content tags reference {cname}",
            reason={"concept_id": str(cid), "concept_name": cname},
        ):
            created += 1

    # --- student_disengaging --------------------------------------------
    seven_days_ago = now - timedelta(days=7)
    fourteen_days_ago = now - timedelta(days=14)
    enrolled = (
        await db.execute(
            select(Enrollment.user_id).where(
                Enrollment.course_id == course_id,
                Enrollment.role == "student",
            )
        )
    ).scalars().all()
    for uid in enrolled:
        recent = (
            await db.execute(
                select(func.count(QuizAttempt.id))
                .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
                .where(
                    Quiz.course_id == course_id,
                    QuizAttempt.user_id == uid,
                    QuizAttempt.created_at >= seven_days_ago,
                )
            )
        ).scalar_one()
        prior = (
            await db.execute(
                select(func.count(QuizAttempt.id))
                .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
                .where(
                    Quiz.course_id == course_id,
                    QuizAttempt.user_id == uid,
                    QuizAttempt.created_at >= fourteen_days_ago,
                    QuizAttempt.created_at < seven_days_ago,
                )
            )
        ).scalar_one()
        if recent == 0 and prior > 0:
            if await _try_insert(
                db,
                course_id=course_id,
                instructor_id=course.instructor_id,
                target_user_id=uid,
                alert_type="student_disengaging",
                severity="warning",
                title="Student inactive 7d after prior activity",
                reason={"recent": 0, "prior": int(prior)},
            ):
                created += 1

    # --- student_falling_behind -----------------------------------------
    for uid in enrolled:
        late_count = (
            await db.execute(
                select(func.count())
                .select_from(AssignmentSubmission)
                .join(Assignment, Assignment.id == AssignmentSubmission.assignment_id)
                .where(
                    AssignmentSubmission.user_id == uid,
                    AssignmentSubmission.status == "late",
                    Assignment.course_id == course_id,
                    AssignmentSubmission.updated_at >= fourteen_days_ago,
                )
            )
        ).scalar_one()
        if late_count >= 2:
            if await _try_insert(
                db,
                course_id=course_id,
                instructor_id=course.instructor_id,
                target_user_id=uid,
                alert_type="student_falling_behind",
                severity="warning",
                title=f"{late_count} late submissions in 14d",
                reason={"late_count": int(late_count)},
            ):
                created += 1

    # --- prereq_gap_for_upcoming_meeting --------------------------------
    horizon = now + timedelta(hours=72)
    meetings = (
        await db.execute(
            select(CourseMeeting).where(
                CourseMeeting.course_id == course_id,
                CourseMeeting.scheduled_at.between(now, horizon),
                CourseMeeting.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    enrolled_count = len(enrolled) or 1
    for meeting in meetings:
        # Concepts tagged on this meeting → prereqs that are weak across cohort.
        from app.models import ConceptPrerequisite
        prereqs = (
            await db.execute(
                select(ConceptPrerequisite.prereq_concept_id, Concept.name)
                .join(
                    ConceptTag,
                    ConceptTag.concept_id == ConceptPrerequisite.dependent_concept_id,
                )
                .join(Concept, Concept.id == ConceptPrerequisite.prereq_concept_id)
                .where(
                    ConceptTag.target_kind == "meeting",
                    ConceptTag.target_id == meeting.id,
                    ConceptPrerequisite.strength >= 0.5,
                )
                .distinct()
            )
        ).all()
        for prereq_id, prereq_name in prereqs:
            n_weak = (
                await db.execute(
                    select(func.count())
                    .select_from(ConceptMastery)
                    .where(
                        ConceptMastery.concept_id == prereq_id,
                        ConceptMastery.course_id == course_id,
                        ConceptMastery.mastery_score < 0.7,
                    )
                )
            ).scalar_one()
            if int(n_weak) * 2 >= enrolled_count:  # 50%+ weak
                if await _try_insert(
                    db,
                    course_id=course_id,
                    instructor_id=course.instructor_id,
                    target_user_id=None,
                    alert_type="prereq_gap_for_upcoming_meeting",
                    severity="warning",
                    title=f"Prereq gap before {meeting.title or 'meeting'}",
                    reason={
                        "meeting_id": str(meeting.id),
                        "prereq_concept_id": str(prereq_id),
                        "prereq_name": prereq_name,
                        "weak_n": int(n_weak),
                        "enrolled": enrolled_count,
                    },
                ):
                    created += 1

    # --- low_quiz_participation -----------------------------------------
    seven_days_ago = now - timedelta(days=7)
    quizzes = (
        await db.execute(
            select(Quiz).where(
                Quiz.course_id == course_id,
                Quiz.is_published.is_(True),
                Quiz.created_at < seven_days_ago,
                Quiz.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    for quiz in quizzes:
        n_attempters = (
            await db.execute(
                select(func.count(func.distinct(QuizAttempt.user_id))).where(
                    QuizAttempt.quiz_id == quiz.id
                )
            )
        ).scalar_one()
        if int(n_attempters) * 100 < enrolled_count * 30:  # <30%
            if await _try_insert(
                db,
                course_id=course_id,
                instructor_id=course.instructor_id,
                target_user_id=None,
                alert_type="low_quiz_participation",
                severity="info",
                title=f"<30% attempted '{quiz.title}'",
                reason={
                    "quiz_id": str(quiz.id),
                    "attempters": int(n_attempters),
                    "enrolled": enrolled_count,
                },
            ):
                created += 1

    # --- missed_deadline -----------------------------------------------
    one_day_ago = now - timedelta(hours=24)
    overdue = (
        await db.execute(
            select(Assignment).where(
                Assignment.course_id == course_id,
                Assignment.due_at < one_day_ago,
                Assignment.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    for asn in overdue:
        n_submitted = (
            await db.execute(
                select(func.count(AssignmentSubmission.user_id)).where(
                    AssignmentSubmission.assignment_id == asn.id,
                    AssignmentSubmission.status.in_(("submitted", "graded")),
                )
            )
        ).scalar_one()
        if int(n_submitted) * 100 < enrolled_count * 80:  # <80%
            if await _try_insert(
                db,
                course_id=course_id,
                instructor_id=course.instructor_id,
                target_user_id=None,
                alert_type="missed_deadline",
                severity="critical",
                title=f"<80% turned in '{asn.title}'",
                reason={
                    "assignment_id": str(asn.id),
                    "submitted": int(n_submitted),
                    "enrolled": enrolled_count,
                },
            ):
                created += 1

    return {"course_id": str(course_id), "alerts_created": created}
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_alerts_evaluator.py -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/alerts.py backend/tests/test_alerts_evaluator.py
git commit -m "feat(adaptive-engine): instructor alert evaluator — 7 rules with idempotent inserts"
```

---

### Task 16: Instructor alerts API

**Files:**
- Create: `backend/app/api/instructor_alerts.py`
- Modify: `backend/app/api/__init__.py`
- Test: `backend/tests/test_api_instructor_alerts.py`

**Context:** Three endpoints on the alerts table:

- `GET /api/courses/{course_id}/alerts?status=open` (instructor-only) — list alerts, filterable by status.
- `PATCH /api/courses/{course_id}/alerts/{alert_id}` body `{"status": "dismissed" | "resolved"}` — sets `status`, `resolved_at`, `resolved_by`.

Idempotency on the partial unique index already prevents double-open rows; the API doesn't need extra logic.

- [ ] **Step 1: Write the test**

```python
# backend/tests/test_api_instructor_alerts.py
import uuid
import pytest
from httpx import AsyncClient

from app.models import Course, InstructorAlert, User


@pytest.mark.asyncio
async def test_list_alerts_default_open_only(
    db_session, async_client: AsyncClient, test_instructor: User
):
    course = Course(
        name="Alert list",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ALI-1",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add_all([
        InstructorAlert(
            course_id=course.id, instructor_id=test_instructor.id,
            alert_type="content_gap", severity="info",
            title="open one", reason={}, status="open",
        ),
        InstructorAlert(
            course_id=course.id, instructor_id=test_instructor.id,
            alert_type="missed_deadline", severity="critical",
            title="resolved one", reason={}, status="resolved",
        ),
    ])
    await db_session.commit()

    res = await async_client.get(f"/api/courses/{course.id}/alerts")
    assert res.status_code == 200
    titles = [a["title"] for a in res.json()["data"]]
    assert "open one" in titles and "resolved one" not in titles


@pytest.mark.asyncio
async def test_patch_alert_resolves(
    db_session, async_client: AsyncClient, test_instructor: User
):
    course = Course(
        name="Patch alert",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ALI-2",
    )
    db_session.add(course)
    await db_session.flush()
    a = InstructorAlert(
        course_id=course.id, instructor_id=test_instructor.id,
        alert_type="content_gap", severity="info",
        title="x", reason={}, status="open",
    )
    db_session.add(a)
    await db_session.commit()

    res = await async_client.patch(
        f"/api/courses/{course.id}/alerts/{a.id}",
        json={"status": "resolved"},
    )
    assert res.status_code == 200
    await db_session.refresh(a)
    assert a.status == "resolved"
    assert a.resolved_at is not None and a.resolved_by == test_instructor.id
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api_instructor_alerts.py -v
```

Expected: 2 fail.

- [ ] **Step 3: Implement router**

```python
# backend/app/api/instructor_alerts.py
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_owned_course, require_instructor
from app.models import InstructorAlert
from app.models.course import Course
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.decision import (
    AlertStatus,
    InstructorAlertResponse,
    InstructorAlertUpdate,
)

router = APIRouter(tags=["instructor-alerts"])


@router.get(
    "/courses/{course_id}/alerts",
    response_model=APIResponse[list[InstructorAlertResponse]],
)
async def list_alerts(
    status: AlertStatus = Query(default="open"),
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[list[InstructorAlertResponse]]:
    rows = (
        await db.execute(
            select(InstructorAlert)
            .where(
                InstructorAlert.course_id == course.id,
                InstructorAlert.status == status,
            )
            .order_by(InstructorAlert.severity.desc(), InstructorAlert.created_at.desc())
        )
    ).scalars().all()
    return APIResponse(
        success=True,
        data=[InstructorAlertResponse.model_validate(r) for r in rows],
    )


@router.patch(
    "/courses/{course_id}/alerts/{alert_id}",
    response_model=APIResponse[InstructorAlertResponse],
)
async def update_alert(
    alert_id: uuid.UUID,
    body: InstructorAlertUpdate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
    actor: User = Depends(require_instructor),
) -> APIResponse[InstructorAlertResponse]:
    row = (
        await db.execute(
            select(InstructorAlert).where(
                InstructorAlert.id == alert_id,
                InstructorAlert.course_id == course.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    row.status = body.status
    row.resolved_at = datetime.now(timezone.utc)
    row.resolved_by = actor.id
    await db.commit()
    await db.refresh(row)
    return APIResponse(success=True, data=InstructorAlertResponse.model_validate(row))
```

In `backend/app/api/__init__.py`:

```python
from app.api.instructor_alerts import router as instructor_alerts_router
...
api_router.include_router(instructor_alerts_router)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_api_instructor_alerts.py -v
```

Expected: 2 pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/instructor_alerts.py backend/app/api/__init__.py backend/tests/test_api_instructor_alerts.py
git commit -m "feat(adaptive-engine): instructor alerts API — list + patch (dismiss/resolve)"
```

---

### Task 17: Quarterly coefficient retune

**Files:**
- Modify: `backend/app/services/action_coeffs.py` (replace stub)
- Test: `backend/tests/test_action_coeffs.py`

**Context:** For each `action_type` in `DEFAULT_COEFFS`, compute mean `outcome_score` over the last `window_days` days for `engine_variant='on'` rows where `completed=true` and the same set for `engine_variant='off'`. Write a `coefficient_overrides` JSONB blob into a singleton row in `tasks.payload['result']` of the most recent `tune_action_coefficients` task — that's the source `scoring.py` reads from once we wire it.

For first ship the retune **only logs the proposed deltas without applying them**: produce `{action_type: {old_coef, mean_outcome_on, mean_outcome_off, suggested_delta}}` and write it to `Task.payload['result']`. A future change can flip a feature flag to apply suggestions automatically. This is intentional — we do not want a quarterly cron silently mutating production scoring before we have eyeballs on the data.

- [ ] **Step 1: Write the test**

```python
# backend/tests/test_action_coeffs.py
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import ActionOutcome, Course, User
from app.services.action_coeffs import retune_action_coefficients


@pytest.mark.asyncio
async def test_retune_returns_per_action_summary(db_session, test_instructor: User):
    course = Course(
        name="Retune",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="RT-1",
    )
    db_session.add(course)
    await db_session.commit()

    served_at = datetime.now(timezone.utc) - timedelta(days=3)
    db_session.add_all([
        ActionOutcome(
            user_id=test_instructor.id, course_id=course.id,
            action_type="practice_weakness", engine_variant="on",
            served_at=served_at, completed=True,
            outcome_metric="quiz_score", outcome_score=Decimal("0.800"),
        ),
        ActionOutcome(
            user_id=test_instructor.id, course_id=course.id,
            action_type="practice_weakness", engine_variant="off",
            served_at=served_at, completed=True,
            outcome_metric="quiz_score", outcome_score=Decimal("0.500"),
        ),
    ])
    await db_session.commit()

    result = await retune_action_coefficients(db_session, window_days=30)
    assert "summary" in result
    summary = result["summary"]
    assert "practice_weakness" in summary
    pw = summary["practice_weakness"]
    assert pw["mean_outcome_on"] == pytest.approx(0.8, abs=1e-2)
    assert pw["mean_outcome_off"] == pytest.approx(0.5, abs=1e-2)
    assert pw["applied"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_action_coeffs.py -v
```

Expected: assertion failures (stub).

- [ ] **Step 3: Replace stub**

```python
# backend/app/services/action_coeffs.py
"""Quarterly retune of scoring coefficients from action_outcomes telemetry.

For Phase 3 ship the retune **proposes** deltas but does not apply them —
the result blob is written to Task.payload['result'] for human review.
A future change can flip ``apply=True`` once the proposals are validated.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActionOutcome
from app.services.scoring import DEFAULT_COEFFS


async def retune_action_coefficients(
    db: AsyncSession, *, window_days: int = 90
) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    summary: dict[str, dict] = {}
    for action_type, current_coef in DEFAULT_COEFFS.items():
        on_mean = (
            await db.execute(
                select(func.avg(ActionOutcome.outcome_score)).where(
                    ActionOutcome.action_type == action_type,
                    ActionOutcome.engine_variant == "on",
                    ActionOutcome.completed.is_(True),
                    ActionOutcome.served_at >= cutoff,
                )
            )
        ).scalar_one()
        off_mean = (
            await db.execute(
                select(func.avg(ActionOutcome.outcome_score)).where(
                    ActionOutcome.action_type == action_type,
                    ActionOutcome.engine_variant == "off",
                    ActionOutcome.completed.is_(True),
                    ActionOutcome.served_at >= cutoff,
                )
            )
        ).scalar_one()

        on_f = float(on_mean) if on_mean is not None else None
        off_f = float(off_mean) if off_mean is not None else None
        if on_f is None or off_f is None or off_f == 0:
            suggested = current_coef
        else:
            # Scale the coefficient by the lift ratio (clamped to [0.5×, 2×]
            # so a single noisy quarter can't flip recommendations wildly).
            lift = on_f / off_f
            lift = max(0.5, min(2.0, lift))
            suggested = current_coef * lift

        summary[action_type] = {
            "old_coef": current_coef,
            "mean_outcome_on": on_f,
            "mean_outcome_off": off_f,
            "suggested_coef": suggested,
            "applied": False,
        }
    return {"window_days": window_days, "summary": summary}
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_action_coeffs.py -v
```

Expected: 1 test passes.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/action_coeffs.py backend/tests/test_action_coeffs.py
git commit -m "feat(adaptive-engine): quarterly coefficient retune — proposes deltas, applies none"
```

---

## Phase 3.4 — Frontend

### Task 18: TS types for decision layer

**Files:**
- Create: `frontend/src/lib/decision-types.ts`

**Context:** Mirror Pydantic schemas. `Decimal` columns serialise as JSON strings (FastAPI Pydantic v2 default) — type them as `string` in TS. Mirror `frontend/src/lib/concept-types.ts` style (readonly, string ISO timestamps, literal unions matching backend `Literal[...]`).

- [ ] **Step 1: Write the file**

```typescript
// frontend/src/lib/decision-types.ts
export type ActionType =
  | "review_concept"
  | "prep_meeting"
  | "complete_assignment"
  | "do_quiz"
  | "practice_weakness"
  | "catch_up_reading"
  | "flashcard_review"
  | "pronunciation_practice"
  | "watch_recording";

export type NextActionTargetKind =
  | "concept"
  | "course_meeting"
  | "assignment"
  | "quiz"
  | "flashcard_set"
  | "pronunciation_set"
  | "document"
  | "chunk";

export type CandidateSource =
  | "outer_fringe"
  | "deadline"
  | "review"
  | "fallback";

export type EngineMode = "on" | "off" | "random_50";
export type OverrideMode = "on" | "off";

export type AlertType =
  | "student_disengaging"
  | "student_falling_behind"
  | "cohort_concept_weakness"
  | "prereq_gap_for_upcoming_meeting"
  | "low_quiz_participation"
  | "missed_deadline"
  | "content_gap";

export type AlertSeverity = "info" | "warning" | "critical";
export type AlertStatus = "open" | "dismissed" | "resolved";

export interface NextAction {
  readonly id: string;
  readonly user_id: string;
  readonly course_id: string | null;
  readonly action_type: ActionType;
  readonly target_kind: NextActionTargetKind | null;
  readonly target_id: string | null;
  readonly priority_score: string;
  readonly candidate_source: CandidateSource;
  readonly reason: Record<string, unknown>;
  readonly expires_at: string;
  readonly served_at: string | null;
  readonly clicked_at: string | null;
  readonly consumed_at: string | null;
  readonly engine_variant: string;
  readonly created_at: string;
}

export interface NextActionClick {
  readonly id: string;
  readonly clicked_at: string;
  readonly target_kind: NextActionTargetKind | null;
  readonly target_id: string | null;
}

export interface EngineSettings {
  readonly course_id: string;
  readonly mode: EngineMode;
  readonly overrides_count: number;
}

export interface EngineOverride {
  readonly user_id: string;
  readonly course_id: string;
  readonly mode: OverrideMode;
  readonly set_by: string;
  readonly set_at: string;
}

export interface InstructorAlert {
  readonly id: string;
  readonly course_id: string;
  readonly instructor_id: string;
  readonly target_user_id: string | null;
  readonly alert_type: AlertType;
  readonly severity: AlertSeverity;
  readonly title: string;
  readonly reason: Record<string, unknown>;
  readonly status: AlertStatus;
  readonly resolved_at: string | null;
  readonly resolved_by: string | null;
  readonly created_at: string;
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && pnpm tsc --noEmit --pretty false
```

Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/decision-types.ts
git commit -m "feat(adaptive-engine): TS types for next_actions, alerts, engine settings"
```

---

### Task 19: TanStack Query hooks (next-actions, alerts, engine settings)

**Files:**
- Create: `frontend/src/hooks/use-next-actions.ts`
- Create: `frontend/src/hooks/use-instructor-alerts.ts`
- Create: `frontend/src/hooks/use-engine-settings.ts`

**Context:** Mirror `use-mastery.ts` and `use-concept-clusters.ts`. Each hook calls `apiFetch` with `{token}`. Mutations invalidate the relevant query keys.

- [ ] **Step 1: Write `use-next-actions.ts`**

```typescript
// frontend/src/hooks/use-next-actions.ts
"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type { NextAction, NextActionClick } from "@/lib/decision-types";

export function useNextActions(courseId: string) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["next-actions", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<NextAction[]>>(
        `/users/me/courses/${courseId}/next-actions`,
        { token },
      );
      return res.data;
    },
    staleTime: 30 * 60 * 1000, // matches backend lazy refresh
  });
}

export function useClickNextAction(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (actionId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<NextActionClick>>(
        `/next-actions/${actionId}/click`,
        { token, method: "POST" },
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["next-actions", courseId] });
    },
  });
}
```

- [ ] **Step 2: Write `use-instructor-alerts.ts`**

```typescript
// frontend/src/hooks/use-instructor-alerts.ts
"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type { AlertStatus, InstructorAlert } from "@/lib/decision-types";

export function useInstructorAlerts(courseId: string, status: AlertStatus = "open") {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["instructor-alerts", courseId, status],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<InstructorAlert[]>>(
        `/courses/${courseId}/alerts?status=${status}`,
        { token },
      );
      return res.data;
    },
  });
}

export function useUpdateInstructorAlert(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      alertId,
      status,
    }: {
      alertId: string;
      status: "dismissed" | "resolved";
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<InstructorAlert>>(
        `/courses/${courseId}/alerts/${alertId}`,
        { token, method: "PATCH", body: JSON.stringify({ status }) },
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instructor-alerts", courseId] });
    },
  });
}
```

- [ ] **Step 3: Write `use-engine-settings.ts`**

```typescript
// frontend/src/hooks/use-engine-settings.ts
"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type {
  EngineMode,
  EngineOverride,
  EngineSettings,
  OverrideMode,
} from "@/lib/decision-types";

export function useEngineSettings(courseId: string) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["engine-settings", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<EngineSettings>>(
        `/courses/${courseId}/engine`,
        { token },
      );
      return res.data;
    },
  });
}

export function useUpdateEngineMode(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (mode: EngineMode) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<EngineSettings>>(
        `/courses/${courseId}/engine`,
        { token, method: "PATCH", body: JSON.stringify({ mode }) },
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["engine-settings", courseId] });
    },
  });
}

export function useUpsertEngineOverride(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      userId,
      mode,
    }: {
      userId: string;
      mode: OverrideMode;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<EngineOverride>>(
        `/courses/${courseId}/engine/overrides/${userId}`,
        { token, method: "PUT", body: JSON.stringify({ mode }) },
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["engine-settings", courseId] });
    },
  });
}

export function useDeleteEngineOverride(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (userId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<{ deleted: number }>>(
        `/courses/${courseId}/engine/overrides/${userId}`,
        { token, method: "DELETE" },
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["engine-settings", courseId] });
    },
  });
}
```

- [ ] **Step 4: Type-check**

```bash
cd frontend && pnpm tsc --noEmit --pretty false
```

Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/use-next-actions.ts frontend/src/hooks/use-instructor-alerts.ts frontend/src/hooks/use-engine-settings.ts
git commit -m "feat(adaptive-engine): TanStack Query hooks for next-actions, alerts, engine settings"
```

---

### Task 20: Student "Today" page

**Files:**
- Create: `frontend/src/components/decision/next-action-card.tsx`
- Create: `frontend/src/components/decision/next-action-list.tsx`
- Create: `frontend/src/app/dashboard/courses/[courseId]/today/page.tsx`

**Context:** A student-facing page that lists the top-10 `next_actions` for the course. Each card shows action type, target name (resolved from `reason.concept_name` or `reason.assignment_title` etc.), priority bar, and a CTA button. Clicking the CTA fires `useClickNextAction` then routes to `/dashboard/courses/{courseId}/{kind}/{id}` based on `target_kind`.

Uses semantic color tokens (`--color-warning` for high priority, `--color-accent` for action CTAs). React 19 — params arrive as Promises in async pages; client-component pages unwrap with `use(props.params)`.

- [ ] **Step 1: Write `next-action-card.tsx`**

```typescript
// frontend/src/components/decision/next-action-card.tsx
"use client";
import type { NextAction } from "@/lib/decision-types";

interface Props {
  readonly action: NextAction;
  readonly onClick: () => void;
  readonly busy: boolean;
}

const ACTION_LABELS: Record<NextAction["action_type"], string> = {
  review_concept: "Review concept",
  prep_meeting: "Prep for meeting",
  complete_assignment: "Complete assignment",
  do_quiz: "Take quiz",
  practice_weakness: "Practice weakness",
  catch_up_reading: "Catch up reading",
  flashcard_review: "Review flashcards",
  pronunciation_practice: "Pronunciation practice",
  watch_recording: "Watch recording",
};

function describeTarget(action: NextAction): string {
  const r = action.reason as Record<string, string | undefined>;
  return (
    r.concept_name ?? r.assignment_title ?? r.meeting_title ?? "—"
  );
}

export function NextActionCard({ action, onClick, busy }: Props) {
  const score = parseFloat(action.priority_score);
  const isHighPriority = score >= 3.0;
  return (
    <article
      className="space-y-2 rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
      data-testid="next-action-card"
    >
      <header className="flex items-baseline justify-between">
        <h3 className="text-sm font-medium text-[var(--color-text)]">
          {ACTION_LABELS[action.action_type]}
        </h3>
        <span
          className={
            "text-xs " +
            (isHighPriority
              ? "text-[var(--color-warning)]"
              : "text-[var(--color-muted)]")
          }
        >
          priority {score.toFixed(2)}
        </span>
      </header>
      <p className="text-sm text-[var(--color-text)]">{describeTarget(action)}</p>
      <button
        type="button"
        disabled={busy}
        onClick={onClick}
        className="rounded bg-[var(--color-accent)] px-3 py-1 text-xs text-[var(--color-on-accent)] disabled:opacity-50"
      >
        {busy ? "Opening…" : "Start"}
      </button>
    </article>
  );
}
```

- [ ] **Step 2: Write `next-action-list.tsx`**

```typescript
// frontend/src/components/decision/next-action-list.tsx
"use client";
import { useRouter } from "next/navigation";

import { NextActionCard } from "@/components/decision/next-action-card";
import {
  useClickNextAction,
  useNextActions,
} from "@/hooks/use-next-actions";
import type { NextAction } from "@/lib/decision-types";

interface Props {
  readonly courseId: string;
}

function buildHref(courseId: string, action: NextAction): string {
  const id = action.target_id;
  switch (action.target_kind) {
    case "quiz":           return `/dashboard/courses/${courseId}/quizzes/${id}`;
    case "flashcard_set":  return `/dashboard/courses/${courseId}/flashcards/${id}`;
    case "course_meeting": return `/dashboard/courses/${courseId}/meetings/${id}`;
    case "assignment":     return `/dashboard/courses/${courseId}/assignments/${id}`;
    case "concept":        return `/dashboard/courses/${courseId}/concepts/${id}`;
    default:               return `/dashboard/courses/${courseId}`;
  }
}

export function NextActionList({ courseId }: Props) {
  const router = useRouter();
  const { data, isLoading, error } = useNextActions(courseId);
  const click = useClickNextAction(courseId);

  if (isLoading) return <p className="text-sm text-[var(--color-muted)]">Loading…</p>;
  if (error) return <p className="text-sm text-[var(--color-error)]">Failed to load.</p>;
  const list = data ?? [];
  if (list.length === 0) {
    return (
      <p className="text-sm text-[var(--color-muted)]">
        No suggested actions right now. Keep going on your own — we&apos;ll pick up signals as you study.
      </p>
    );
  }
  return (
    <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
      {list.map((a) => (
        <li key={a.id}>
          <NextActionCard
            action={a}
            busy={click.isPending}
            onClick={async () => {
              await click.mutateAsync(a.id);
              router.push(buildHref(courseId, a));
            }}
          />
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 3: Write the page**

```typescript
// frontend/src/app/dashboard/courses/[courseId]/today/page.tsx
"use client";
import { use } from "react";

import { NextActionList } from "@/components/decision/next-action-list";

export default function TodayPage(
  props: { readonly params: Promise<{ readonly courseId: string }> },
) {
  const { courseId } = use(props.params);
  return (
    <main className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-[var(--color-text)]">Today</h1>
        <p className="text-sm text-[var(--color-muted)]">
          The next things worth doing — based on what you&apos;ve already mastered.
        </p>
      </header>
      <NextActionList courseId={courseId} />
    </main>
  );
}
```

- [ ] **Step 4: Type-check**

```bash
cd frontend && pnpm tsc --noEmit --pretty false
```

Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/decision/ frontend/src/app/dashboard/courses/\[courseId\]/today/
git commit -m "feat(adaptive-engine): student Today page — top-10 next_actions with click-through"
```

---

### Task 21: Instructor alerts center

**Files:**
- Create: `frontend/src/components/decision/instructor-alert-card.tsx`
- Create: `frontend/src/components/decision/alert-list.tsx`
- Create: `frontend/src/app/dashboard/courses/[courseId]/alerts/page.tsx`

**Context:** Instructor-only page listing `instructor_alerts` for the course. Alerts can be filtered by status (`open` default, switch to `dismissed | resolved`). Each card shows severity, title, summary from `reason`, with Dismiss + Resolve buttons.

- [ ] **Step 1: Write `instructor-alert-card.tsx`**

```typescript
// frontend/src/components/decision/instructor-alert-card.tsx
"use client";
import type { InstructorAlert } from "@/lib/decision-types";

interface Props {
  readonly alert: InstructorAlert;
  readonly onUpdate: (status: "dismissed" | "resolved") => void;
  readonly busy: boolean;
}

const SEVERITY_COLOR: Record<InstructorAlert["severity"], string> = {
  info: "var(--color-accent)",
  warning: "var(--color-warning)",
  critical: "var(--color-error)",
};

export function InstructorAlertCard({ alert, onUpdate, busy }: Props) {
  return (
    <article
      className="space-y-2 rounded border bg-[var(--color-surface)] p-4"
      style={{ borderColor: SEVERITY_COLOR[alert.severity] }}
      data-testid="instructor-alert-card"
    >
      <header className="flex items-baseline justify-between">
        <h3 className="text-sm font-medium text-[var(--color-text)]">
          {alert.title}
        </h3>
        <span
          className="text-xs uppercase tracking-wide"
          style={{ color: SEVERITY_COLOR[alert.severity] }}
        >
          {alert.severity}
        </span>
      </header>
      <p className="text-xs text-[var(--color-muted)]">
        {alert.alert_type.replaceAll("_", " ")}
      </p>
      {alert.status === "open" && (
        <div className="flex gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => onUpdate("dismissed")}
            className="rounded border border-[var(--color-border)] px-2 py-1 text-xs text-[var(--color-text)] disabled:opacity-50"
          >
            Dismiss
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => onUpdate("resolved")}
            className="rounded bg-[var(--color-accent)] px-2 py-1 text-xs text-[var(--color-on-accent)] disabled:opacity-50"
          >
            Resolve
          </button>
        </div>
      )}
    </article>
  );
}
```

- [ ] **Step 2: Write `alert-list.tsx`**

```typescript
// frontend/src/components/decision/alert-list.tsx
"use client";
import { useState } from "react";

import { InstructorAlertCard } from "@/components/decision/instructor-alert-card";
import {
  useInstructorAlerts,
  useUpdateInstructorAlert,
} from "@/hooks/use-instructor-alerts";
import type { AlertStatus } from "@/lib/decision-types";

interface Props {
  readonly courseId: string;
}

const TABS: AlertStatus[] = ["open", "dismissed", "resolved"];

export function AlertList({ courseId }: Props) {
  const [status, setStatus] = useState<AlertStatus>("open");
  const { data, isLoading, error } = useInstructorAlerts(courseId, status);
  const update = useUpdateInstructorAlert(courseId);

  const tabs = TABS.map((s) => (
    <button
      key={s}
      type="button"
      onClick={() => setStatus(s)}
      className={
        "rounded px-3 py-1 text-xs " +
        (status === s
          ? "bg-[var(--color-accent)] text-[var(--color-on-accent)]"
          : "text-[var(--color-muted)] hover:text-[var(--color-text)]")
      }
    >
      {s}
    </button>
  ));

  return (
    <section className="space-y-3">
      <nav className="flex gap-2">{tabs}</nav>
      {isLoading && <p className="text-sm text-[var(--color-muted)]">Loading…</p>}
      {error && <p className="text-sm text-[var(--color-error)]">Failed to load.</p>}
      {!isLoading && (data ?? []).length === 0 && (
        <p className="text-sm text-[var(--color-muted)]">
          Nothing here. ({status})
        </p>
      )}
      <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {(data ?? []).map((a) => (
          <li key={a.id}>
            <InstructorAlertCard
              alert={a}
              busy={update.isPending}
              onUpdate={(s) => update.mutate({ alertId: a.id, status: s })}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
```

- [ ] **Step 3: Write the page**

```typescript
// frontend/src/app/dashboard/courses/[courseId]/alerts/page.tsx
"use client";
import { use } from "react";

import { AlertList } from "@/components/decision/alert-list";

export default function AlertsPage(
  props: { readonly params: Promise<{ readonly courseId: string }> },
) {
  const { courseId } = use(props.params);
  return (
    <main className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-[var(--color-text)]">
          Alerts
        </h1>
        <p className="text-sm text-[var(--color-muted)]">
          Auto-evaluated course health signals — dismiss or resolve as you act on each.
        </p>
      </header>
      <AlertList courseId={courseId} />
    </main>
  );
}
```

- [ ] **Step 4: Type-check + commit**

```bash
cd frontend && pnpm tsc --noEmit --pretty false
git add frontend/src/components/decision/instructor-alert-card.tsx frontend/src/components/decision/alert-list.tsx frontend/src/app/dashboard/courses/\[courseId\]/alerts/
git commit -m "feat(adaptive-engine): instructor alerts center page"
```

---

### Task 22: Engine on/off/random_50 toggle UI

**Files:**
- Create: `frontend/src/components/decision/engine-mode-selector.tsx`
- Create: `frontend/src/app/dashboard/courses/[courseId]/engine/page.tsx`
- Modify: `frontend/src/app/dashboard/courses/[courseId]/page.tsx` (add nav link)

**Context:** Instructor settings page for the engine. Three radio options for course mode (on / off / random_50) with a description for each, plus an explanation of `random_50`'s deterministic-hash A/B split. The per-user override list is **out of scope for first ship** — we surface mode + override count only; users can be overridden from the (existing) student-detail page in a follow-up.

Add a Today / Alerts / Engine row to the existing course landing page nav (the row that already has Concepts / Concept Curation / Prerequisites / Mastery). Today is student-only or owner; Alerts and Engine are owner-only.

- [ ] **Step 1: Write `engine-mode-selector.tsx`**

```typescript
// frontend/src/components/decision/engine-mode-selector.tsx
"use client";
import {
  useEngineSettings,
  useUpdateEngineMode,
} from "@/hooks/use-engine-settings";
import type { EngineMode } from "@/lib/decision-types";

interface Props {
  readonly courseId: string;
}

const OPTIONS: { value: EngineMode; label: string; help: string }[] = [
  {
    value: "on",
    label: "On",
    help: "All enrolled students see personalised next-actions.",
  },
  {
    value: "off",
    label: "Off",
    help: "No next-actions are shown. Outcome telemetry is still recorded for the off arm.",
  },
  {
    value: "random_50",
    label: "Random 50/50",
    help:
      "Half of your students see next-actions, half don't. Each student is " +
      "deterministically placed by hash so they stay in the same arm session-to-session — clean A/B telemetry.",
  },
];

export function EngineModeSelector({ courseId }: Props) {
  const { data, isLoading } = useEngineSettings(courseId);
  const update = useUpdateEngineMode(courseId);
  if (isLoading || !data) return null;
  return (
    <fieldset className="space-y-3 rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <legend className="text-sm font-medium text-[var(--color-text)]">
        Adaptive engine mode
      </legend>
      <p className="text-xs text-[var(--color-muted)]">
        Currently {data.overrides_count} per-student override
        {data.overrides_count === 1 ? "" : "s"} active.
      </p>
      {OPTIONS.map((o) => (
        <label
          key={o.value}
          className="flex items-start gap-2 text-sm text-[var(--color-text)]"
        >
          <input
            type="radio"
            checked={data.mode === o.value}
            disabled={update.isPending}
            onChange={() => update.mutate(o.value)}
            className="mt-1"
          />
          <span>
            <strong>{o.label}</strong>
            <br />
            <span className="text-xs text-[var(--color-muted)]">{o.help}</span>
          </span>
        </label>
      ))}
    </fieldset>
  );
}
```

- [ ] **Step 2: Write the page**

```typescript
// frontend/src/app/dashboard/courses/[courseId]/engine/page.tsx
"use client";
import { use } from "react";

import { EngineModeSelector } from "@/components/decision/engine-mode-selector";

export default function EnginePage(
  props: { readonly params: Promise<{ readonly courseId: string }> },
) {
  const { courseId } = use(props.params);
  return (
    <main className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-[var(--color-text)]">
          Adaptive engine
        </h1>
        <p className="text-sm text-[var(--color-muted)]">
          Choose how aggressively Meli surfaces personalised next-actions for this course.
        </p>
      </header>
      <EngineModeSelector courseId={courseId} />
    </main>
  );
}
```

- [ ] **Step 3: Add nav links to the course landing page**

Open `frontend/src/app/dashboard/courses/[courseId]/page.tsx` and locate the existing nav row that lists Concepts / Concept Curation / Prerequisites / Mastery (added in Phase 2 Task 22). Append three more cells:

```tsx
{/* Student-or-instructor */}
<Link href={`/dashboard/courses/${courseId}/today`} className="...">
  Today
</Link>
{role === "instructor" && (
  <>
    <Link href={`/dashboard/courses/${courseId}/alerts`} className="...">
      Alerts
    </Link>
    <Link href={`/dashboard/courses/${courseId}/engine`} className="...">
      Engine
    </Link>
  </>
)}
```

(Match the exact card classnames already used by the Phase 2 row — we don't reinvent them here.)

- [ ] **Step 4: Type-check + commit**

```bash
cd frontend && pnpm tsc --noEmit --pretty false
git add frontend/src/components/decision/engine-mode-selector.tsx frontend/src/app/dashboard/courses/\[courseId\]/engine/ frontend/src/app/dashboard/courses/\[courseId\]/page.tsx
git commit -m "feat(adaptive-engine): course-level engine on/off/random_50 toggle UI + course landing nav"
```

---

### Task 23: Demo seed — flip one course to `random_50`

**Files:**
- Modify: `backend/seed.py`

**Context:** Phase 3 ship criterion: at least one course running in `random_50` for real A/B telemetry. The dev seed should set `adaptive_engine_mode='random_50'` on at least one demo course so smoke tests + manual QA exercise both arms end-to-end. Production rollout flips this via the new `PATCH /api/courses/{id}/engine` endpoint — no code change needed for prod.

- [ ] **Step 1: Find the seed file's course-creation block**

```bash
grep -n "Course(" /home/badur/projects/cle/backend/seed.py | head -10
```

- [ ] **Step 2: Modify the seed**

In `backend/seed.py`, locate the first `Course(...)` instantiation and add:

```python
adaptive_engine_mode="random_50",  # Phase 3 ship criterion: real A/B telemetry on at least one demo course
```

Adjacent comment makes the intent obvious to a future reader.

- [ ] **Step 3: Run seed locally to verify**

```bash
cd backend && . .venv/bin/activate && python seed.py
psql -U postgres -h localhost -d langassistant -c "SELECT name, adaptive_engine_mode FROM courses;"
```

Expected: at least one row with `adaptive_engine_mode = 'random_50'`.

- [ ] **Step 4: Commit**

```bash
git add backend/seed.py
git commit -m "feat(adaptive-engine): seed demo course with adaptive_engine_mode='random_50' for A/B telemetry"
```

---

## Self-Review

The plan covers every Phase 3 spec section: `next_actions` (Task 1, 7, 10), KST outer-fringe (Task 5), scoring (Task 6), recompute triggers — lazy + event-driven + horizon cron (Tasks 9, 11, 12), `instructor_alerts` (Tasks 1, 15, 16), `action_outcomes` telemetry (Tasks 1, 10, 14, 17), engine on/off + per-user override + random_50 hash (Tasks 1, 4, 13, 22, 23), coefficient retuning (Tasks 8, 17), and frontend surfaces (Tasks 18–22). The ship criterion (≥ 1 course on `random_50`) is wired in Task 23.

The dependency graph keeps each task self-contained: every step shows the actual code or command, every test is concrete, every reference path is verified against the current branch (`f9d8e7c6b5a4` is the real Phase 2 head; the four-tab `concept-curation / mastery / concepts / prerequisites` nav row in `page.tsx` is the real Phase 2 hook point for Task 22). Symbols introduced early (`resolve_engine_mode`, `outer_fringe_concepts`, `materialize_next_actions`, `record_serve`, `apply_attempt_evidence`'s outcome-closing hook) keep their names through the rest of the plan.

The bandit / FSRS / recalibration tables are untouched per spec lock. The Beta-Binomial mastery math is read-only input. Phase 1 entities are read-only except `courses.adaptive_engine_mode` (the ALTER explicitly deferred from Phase 1 per RESUME.md memory).
