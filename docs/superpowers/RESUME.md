# Adaptive Engine — Resume Pointer

> **Purpose:** drop-in context for a fresh Claude Code session picking up the adaptive engine work after a `/compact`. Read this first, then the spec, then the active plan.

**Last updated:** 2026-04-28 (Phase 1 shipped, ready to write Phase 2 plan)

## State

| Doc | Path | Commit | Status |
|---|---|---|---|
| Design spec | `docs/superpowers/specs/2026-04-28-adaptive-engine-design.md` | `f63c6e5` | ✅ approved by user |
| Phase 1 plan | `docs/superpowers/plans/2026-04-28-adaptive-engine-phase1-plan.md` | `5d7487b` | ✅ executed (15/15 tasks) |
| **Phase 1 implementation** | branch `feat/adaptive-engine-phase1` | `0ea8c74…2d4bd08` (18 commits) | ✅ shipped, reviewed, fixed; **NOT merged to main yet** |
| Phase 2 plan | not written | — | ⏳ **next step** — write now (post-compact) |
| Phase 3 plan | not written | — | ⏳ wait until Phase 2 mastery has produced real data |

## Phase 1 — what shipped

Branch `feat/adaptive-engine-phase1` (18 commits, base `e600172`, head `2d4bd08`):

**Backend (Tasks 1-9):**
- Alembic migration `d8c3a1e7f9b4` — 6 new tables (`course_modules`, `course_meetings`, `learning_objectives`, `assignments`, `assignment_submissions`, `syllabus_imports`) + `documents.kind` column + `meeting_id`/`module_id` FKs on documents/quizzes/flashcard_sets/pronunciation_sets
- SQLAlchemy models in `backend/app/models/curriculum.py`
- Pydantic schemas in `backend/app/schemas/curriculum.py`
- 5 routers: `modules.py`, `meetings.py`, `objectives.py`, `assignments.py`, `syllabus.py`
- `/api/courses/{id}/calendar` combined feed (meetings + published assignments) — accessible to enrolled students
- Syllabus parser: `parse_syllabus_text` (LLM via OpenRouter) + `apply_syllabus_payload` (transactional dedup applier) + `parse_syllabus` worker dispatch + UI Re-trigger on failure
- `mark_overdue_submissions` daily cron (24h cadence in worker loop)
- `get_owned_course` extracted to `app/api/deps.py` (was duplicated 5×)

**Frontend (Tasks 10-14):**
- TanStack Query hooks: `use-modules`, `use-meetings`, `use-objectives`, `use-assignments`, `use-assignment-submissions`, `use-syllabus`, rewritten `use-calendar-events`
- Shared TS types in `frontend/src/lib/curriculum-types.ts`
- Instructor editor pages under `/dashboard/courses/[courseId]/{modules,meetings,objectives,assignments,syllabus}`
- Student calendar at `/dashboard/calendar` with week navigation (prev/next/today)
- Student assignment submit flow with role-based view (`useRole()` branches instructor/student)
- Syllabus uploader + parsed-payload review (JSON textarea + structured preview)
- Curriculum components in `frontend/src/components/curriculum/` (15 components)
- Dashboard widgets retain placeholder data via new `dashboard-preview-events.ts`

**E2E smoke (Task 15):**
- `frontend/e2e/curriculum-flow.spec.ts` — 5 unauthenticated-redirect tests passing; full flow `test.fixme'd` pending Better Auth test session fixtures

**Post-review fixes applied (commits `864c274` + `d8b583b`):**
- C1/C2 IDOR — `list_submissions` and `grade_submission` now verify `Assignment.course_id == course_id`
- C3 Calendar accessible to enrolled students (was instructor-only)
- `parse_syllabus` failure → `status='failed'` with `error_message` (no more stuck spinner)
- `_own_course` extracted to `deps.get_owned_course`
- Syllabus import trigger rate-limited
- `apply_syllabus_payload` skips invalid `scheduled_at`/`due_at` instead of crashing
- `SubmissionGrade.score` capped at 9999.99 (matches DB `Numeric(6,2)`)
- Submission upsert race handled via IntegrityError catch + re-fetch
- `update_meeting` returns 409 on `meeting_index` conflict
- `parent_id` cross-course validation
- Calendar date range capped at 366 days
- LLM truncation logs warning at 40k chars
- Worker defense: document/import course mismatch fails the import
- UI: UUID → "Student #abc123" fingerprint; native `<select>` → Select primitive; raw Tailwind palette → Honey & Salt design tokens (status badges, success/error text); native checkbox enhanced; aria-labels uniqueified; consistent `["submissions", courseId, assignmentId]` query keys
- README.md updated with Phase 1 feature section + curriculum/syllabus API tables + roadmap split (3a Done, 3b/3c Planned)

**Tests:** 452 backend tests passing (10 new: cross-course IDOR, student calendar access, parent_id validation, meeting_index conflict). Pre-existing unrelated failures (`test_live_quiz_service::test_get_leaderboard_sorted`, `test_scheduler_integration`) untouched.

**Frontend build:** green, no TypeScript errors, no FormEvent deprecations.

## Phase 1 — known follow-ups (NOT blockers, address opportunistically)

- Backend: `AssignmentSubmissionResponse` doesn't expose user name/email — grading roster shows fingerprint UUIDs. Phase 2 should join through `users` table.
- Backend: `apply_syllabus_payload` has N+1 queries for dedup (per-row SELECT). Acceptable for Phase 1 scale; refactor to bulk fetch + in-memory map if syllabi exceed ~50 items per section.
- Backend: `apply_syllabus_payload` overwrites `existing.scheduled_at` on re-apply — instructor manual edits get reverted. Document or add merge logic.
- Frontend: syllabus payload review uses raw JSON textarea — works for HKUST instructors but not ideal UX. A structured editor would help.
- Frontend: student `StudentAssignmentList` has no per-assignment submission status — needs backend endpoint exposing user's own submission state per assignment.
- Frontend: `use-calendar-events` legacy shim cleanup is complete; `dashboard-preview-events.ts` still has stub data (UPCOMING_SWARMS) — remove when dashboard widgets get real per-course data.
- Stale Clerk references throughout README.md — sweep when convenient.

## Branch state

- **Current branch:** `feat/adaptive-engine-phase1`
- **NOT pushed** — user wanted to review before pushing
- All 18 commits live locally; no rebase needed
- Per memory rule "Single branch for plans": Phase 2 work continues on this same branch (do NOT create a new branch per phase)

## Locked product decisions (do not re-litigate)

| # | Decision | Reason |
|---|---|---|
| 1 | Concept curation = **medium-touch** (LLM extracts → cluster → instructor curates per cluster, ~30 min/course) | Pure LLM extraction produces unstable join keys (literature consensus 2025) |
| 2 | Outcome telemetry uses **per-cohort A/B switch** with toggle (engine on/off/random_50) | Investors want measurable lift, not just "feels better" |
| 3 | ALOSI / Open edX = **reference only**, not fork | Their schema is XBlock-coupled |
| 4 | Phase 1 ships **standalone** (no concepts in it) — ✅ done | Validates calendar UX before harder layer |
| 5 | Pronunciation feeds `concept_mastery` via `overall_score / 100` | Single uniform evidence model |
| 6 | `assignment_submissions` shipped in Phase 1 — ✅ done | Canvas integration not confirmed; planned publish flow needs real submission tracking |
| 7 | Scoped syllabus parser shipped in Phase 1 — ✅ done | Parses ONLY documents with `kind='syllabus'` |

## Locked technical decisions (research-grounded; do not re-litigate)

| # | Decision | Replaces | Evidence |
|---|---|---|---|
| 1 | Beta-Binomial posterior for `concept_mastery` | EMA in initial spec | EMA is not a published mastery method; PDT/Beta gives mean+variance+cold-start for same complexity |
| 2 | HLR-style nightly decay shipped in Phase 2.2 (with mastery) | Decay deferred to "future" in initial spec | Duolingo +9.5% retention, ~50% error reduction |
| 3 | KST "outer fringe" predicate as first-class candidate filter for `next_actions` | Hand-tuned coefficients alone | ALEKS uses KST; instructor-explainable |
| 4 | Single polymorphic `concept_tags(target_kind, target_id, concept_id, weight)` | 8 separate tagging tables | One migration, one write path, partial indexes per kind |
| 5 | `course_meetings` (not `class_sessions`) — ✅ done in Phase 1 | Avoid collision with existing `LiveSession` model | Naming clarity |
| 6 | `concept.embedding vector(3072)` | Was `vector(1536)` in initial spec | Matches `openai/text-embedding-3-large` native dim |

## How to resume — Phase 2 plan writing (post-compact)

User said they want to continue to Phase 2 after compacting. Triggers for Phase 2 are intentionally relaxed (Phase 1 has not yet had ≥2 weeks of soak), but the user has explicitly chosen to proceed. Run this flow:

1. **Read this file** (you're doing it).
2. **Read the design spec**: `docs/superpowers/specs/2026-04-28-adaptive-engine-design.md` — Phase 2 sections cover concepts, Beta-Binomial mastery, HLR decay, syllabus-as-generation-context.
3. **Skim Phase 1 codebase patterns** — Phase 2 plan should reference real file paths from Phase 1:
   - Migration style: `backend/alembic/versions/d8c3a1e7f9b4_phase1_curriculum_calendar.py`
   - Model patterns: `backend/app/models/curriculum.py` (mixins, named constraints, ondelete clauses)
   - Schema patterns: `backend/app/schemas/curriculum.py` (Pydantic v2, Literal unions, model_config)
   - Router patterns: `backend/app/api/modules.py` and siblings (use `Depends(get_owned_course)`, soft delete on DELETE)
   - Worker dispatch: `backend/app/services/worker.py:273+` (parse_syllabus branch shows the pattern)
   - Hook patterns: `frontend/src/hooks/use-modules.ts` and siblings
   - UI primitives: `frontend/src/components/curriculum/` matches Honey & Salt with semantic color tokens
4. **Invoke `superpowers:writing-plans`** with the Phase 2 scope:
   - `concepts` table (with `embedding vector(3072)`, status field for curation lifecycle)
   - `concept_prerequisites` table (DAG with cycle prevention)
   - `concept_tags` polymorphic table (`target_kind` + `target_id` + `concept_id` + `weight`)
   - `concept_mastery` table (Beta-Binomial: `alpha`, `beta`, `last_updated`, per user×course×concept)
   - HLR-style nightly decay job + `concept_mastery_history` for replay debugging
   - LLM concept extraction + clustering pipeline (medium-touch curation flow per locked decision #1)
   - Pre-fill mastery via 90-day attempt replay
   - Syllabus-as-generation-context: when generating quizzes/flashcards/summaries, pull the most recent applied `SyllabusImport.parsed_payload` for that course as a system prompt addendum
   - Frontend: concept curation UI (cluster review per course), mastery visualization, "what concepts does this content tag?" affordance for instructors
   - Output to `docs/superpowers/plans/2026-04-28-adaptive-engine-phase2-plan.md`
5. After plan is written + reviewed, switch to executing-plans (or subagent-driven-development) to implement.

**Phase 2 must NOT touch:**
- The decision layer (`next_actions`, `instructor_alerts`, `action_outcomes`, engine on/off toggle) — that's Phase 3
- Existing Phase 1 entities (modules, meetings, objectives, assignments) except to add `concept_tags` polymorphic links

## Critical context for any future session

- **Existing stack:** FastAPI + SQLAlchemy 2.0 async + Alembic + Postgres 17 + pgvector + Next.js 16 App Router (proxy.ts NOT middleware.ts) + React 19 + TanStack Query + Better Auth.
- **Existing strong layers (DO NOT REPLACE):**
  - Content: `documents` → `chunks` (HNSW + tsvector) → quiz/flashcard/summary generators (`app/services/generator.py`)
  - Evidence: `quiz_attempts`, `flashcard_progress` (FSRS-5), `revision_attempts` (with bandit-selected difficulty), `pronunciation_scores`
  - Policy: `bandit_models` (per user/course/content_type), `scheduler_models` (FSRS-5 19 params per user/course), `recalibration_*` machinery
  - **Curriculum (NEW in Phase 1):** `course_modules`, `course_meetings`, `learning_objectives`, `assignments`, `assignment_submissions`, `syllabus_imports` + `documents.kind`
- **Worker:** `app/services/worker.py:196` already uses `FOR UPDATE SKIP LOCKED`. New `task_type` values are dispatched via the if/elif chain at `worker.py:273+` (Phase 1 added `parse_syllabus`). Add new branches there. Daily crons follow the `last_overdue_run` pattern in the main loop.
- **Auth:** Better Auth (self-hosted), JWTs verified against JWKS at `BETTER_AUTH_JWKS_URL`. `get_current_user` dependency creates user rows on first login.
- **Permissions:** instructor-only mutations use `get_owned_course` dep (post-Phase-1 refactor). Read access for enrolled users uses inline `_enrolled` join in handler. Calendar feed accessible to all enrolled.
- **Test DB:** `langassistant_test`. `conftest.py` provides `db_session`, `async_client`, `logged_in_user`, `test_instructor`, `test_student` fixtures. Use `pytest_asyncio.fixture` for async fixtures (strict mode).
- **Frontend conventions:**
  - `React.FormEvent<HTMLFormElement>` (NOT bare `React.FormEvent` — deprecated in React 19)
  - Server components for pages, client components for interactivity (`"use client"` only where needed)
  - Async params: `props: { params: Promise<{ courseId: string }> }` then `await props.params`
  - Design tokens in `styles/tokens.css` (oklch); use semantic vars (`--color-warning`, `--color-success`, `--color-error`, `--color-accent`) NOT raw Tailwind palette

## Validation refs (kept here so they don't drift)

Spec was validated against:
- ALEKS / Knowledge Space Theory ([Falmagne ALEKS science](https://www.aleks.com/about_aleks/Science_Behind_ALEKS.pdf))
- ALOSI / Open edX adaptive engine ([wiki](https://openedx.atlassian.net/wiki/spaces/AC/pages/575799401/Adaptive+Learning+Tools+and+Engines))
- Duolingo HLR ([paper](https://research.duolingo.com/papers/settles.acl16.pdf))
- DAS3H ([arxiv 1905.06873](https://arxiv.org/abs/1905.06873))
- KT survey ([ACM Computing Surveys 2023](https://dl.acm.org/doi/full/10.1145/3569576))
- Lan & Baraniuk contextual bandits for learning ([EDM 2016](https://people.umass.edu/~andrewlan/papers/16edm-bandits.pdf))
- 2025 LLM-for-educational-KG papers ([Springer](https://link.springer.com/article/10.1007/s42979-024-03341-y), [MDPI 2025](https://www.mdpi.com/2504-4990/7/3/103))
