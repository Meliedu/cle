# Meli × CLE Checkpoint Loop — Master Roadmap (Cross-Session Tracker)

> **For agentic workers:** This is the CROSS-SESSION CONTRACT, not a task-level plan. Each phase gets its own detailed plan file (`2026-MM-DD-meli-cle-pN-*.md`) written with the `superpowers:writing-plans` skill, then executed with `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the checkpoint-centered course loop (spec: `docs/superpowers/specs/2026-07-06-meli-cle-checkpoint-loop-design.md`) end-to-end for teacher + student, across 8 independently-shippable phases run in separate Claude sessions.

**Architecture:** Extend-in-place on the existing FastAPI + Next.js 16 monorepo. New domain layer (checkpoints, attendance/QR, activities, score policy, work-item checklist spine, readiness, reports, course-memory API) rides the existing evidence seam (`learning_events` → notes → review → follow-ups → mastery). Role-scoped frontend IA (`/teacher`, `/student`) replaces the shared `/dashboard`. CLE specifics live in a pilot config module.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic, Postgres 17 + pgvector, DB task queue; Next.js 16 App Router, React 19, TanStack Query, Better Auth (JWT + genericOAuth-ready), next-intl, Playwright, pytest.

---

## Session bootstrap protocol (EVERY new session starts here)

1. Read this roadmap top-to-bottom (it is short; do not skip the Global Rules).
2. Read the spec: `docs/superpowers/specs/2026-07-06-meli-cle-checkpoint-loop-design.md`.
3. Find the first unchecked phase in the Phase Tracker below.
4. If that phase has no detailed plan file yet → invoke `superpowers:writing-plans` and write it from the phase brief + spec (+ read the actual code files the brief names). Commit the plan.
5. Execute the plan task-by-task (`superpowers:subagent-driven-development` or `superpowers:executing-plans`). Check off checkboxes IN THE PLAN FILE as tasks complete.
6. On phase completion (or session end): update the Phase Tracker checkbox + append a Handoff Log entry at the bottom of THIS file (date, what shipped, commits, gotchas, next action), commit both.

**Session-end rule:** never leave the session without updating the Handoff Log — the next session has zero memory.

## Global rules (apply to every phase)

- **Figma:** file key `EhzLyFCTZBIGU4iNyHUqvl`, page `final` (`1372:2`). Before building any screen, pull its design context via Figma MCP `get_design_context` (node IDs in the phase briefs; individual screen ids are children of the group frames — call `get_metadata` on the group first). Wireframes are abstract: follow flow + content structure, apply our own enterprise visual design.
- **UI quality:** invoke `frontend-design:frontend-design` and `ui-ux-pro-max:ui-ux-pro-max` skills for UI build tasks. Tokens from `frontend/src/styles/tokens.css` only — no hardcoded colors. One visual treatment per state-machine status (`ReviewStateChip` / `StateBanner` patterns). Empty/waiting states are designed components (reason + next action), never blank divs.
- **i18n:** every new string is a next-intl key (`frontend/messages/en.json`); namespaces `teacher.*`, `student.*`, `patterns.*`, `nav.*`. English only; zh-Hant later.
- **Backend conventions:** `APIResponse[T]` envelope; UUID PKs + `TimestampMixin` (+ soft delete where user-facing); Postgres enums with transitions validated in the service layer; review-affecting actions appended to `review_actions`; RLS on student-owned tables (pattern: migration `28236be3d7b3`); role/ownership guards from `app/api/deps.py`; new task types added to `worker.py` dispatch with `_task_created_at` idempotency where they mutate user state; `Task.payload` is JSON — query with `.op("->>")`.
- **Gates are server-side** (spec §3.4): typed error codes (`SETUP_NOT_OPEN`, `REVIEW_REQUIRED`, `QR_NOT_AVAILABLE`, `SCORE_POLICY_INCOMPLETE`, `REPORT_NOT_REVIEWED`, `MEMORY_UNDECIDED`) that the UI maps to designed states.
- **Evidence seam:** every student submission emits a `learning_event` (see `app/services/learning_events.py`) and enqueues `update_concept_mastery` where concept-tagged. Never build a parallel evidence path.
- **TDD:** failing test first for all backend logic; 80%+ coverage on new code; state-machine transition tests + gate-refusal tests + RLS isolation tests per phase. Playwright spec per phase critical flow.
- **Review & commits:** run code review (code-reviewer agent or `/code-review`) after each task cluster; conventional commits (`feat:`, `fix:`, `docs:`, `test:`); commit frequently; plan/spec/roadmap files need `git add -f` (docs/ is gitignored by design).
- **Security:** no secrets in code; rate-limit new abuse-prone endpoints (QR scan, readiness submit); audit exports/publishes; no time-on-page tracking (data-minimization boundary); no seed/demo data paths reachable in production builds.
- **Next.js 16 caveat:** read `frontend/AGENTS.md` + `node_modules/next/dist/docs/` before frontend work — `proxy.ts` not `middleware.ts`; APIs differ from training data.

## Phase Tracker

- [ ] **P0 — Shell & foundations** → plan: `2026-07-07-meli-cle-p0-shell-foundations.md` (WRITTEN — execute next)
- [ ] **P1 — Course setup wizard & gates** → plan: not written
- [ ] **P2 — Student entry & enrollment** → plan: not written
- [ ] **P3 — Checkpoint loop core** → plan: not written
- [ ] **P4 — Student workspace, checklist & calendar** → plan: not written
- [ ] **P5 — Practice / quiz / activities / score** → plan: not written
- [ ] **P6 — Follow-up & insights** → plan: not written
- [ ] **P7 — Reports, course memory & hardening** → plan: not written

Phases must run in order: P1 depends on P0's config/shell; P2 on P1's setup gate; P3 on P1's sessions/checkpoint drafts; P4 on P3's work-item sources; P5 on P4's work-item spine; P6 on P3+P5 evidence flowing; P7 on everything.

---

## Phase briefs

### P0 — Shell & foundations

**Screens:** T001–T013 shell (Figma group `1372:6`), S001–S002 (`1372:198` first two), S014–S022 shell (`1372:226`).
**Scope:** pilot config module (`backend/app/pilot/` + `GET /api/config`); role-scoped route trees `app/(app)/teacher/` + `app/(app)/student/` with RoleGate + `/dashboard` role redirect (legacy subroutes keep working); backend-authoritative `useRole` (from `/api/auth/me`, replacing email-domain guess); nav configs + collapsible sidebar shells per Figma; P0 pattern components (PageHeader, StateBanner, EmptyState); sign-in rebuild per T001/S001 with HKUST staff/student routing affordance + Better Auth `genericOAuth` slots behind env flags + `docs/oidc-redirect-uris.md` (verified callback paths); profile + notification-preferences pages (`users.notification_prefs` JSONB + PATCH endpoint); i18n namespace skeleton; role-routing Playwright spec.
**Deliberate deferrals:** full calendar month/week grids (T007/T008, S018–S020) → P4; insights pages → P6 (route ships with designed no-evidence EmptyState).
**Key existing files:** `frontend/src/proxy.ts`, `frontend/src/hooks/use-role.ts`, `frontend/src/lib/auth.ts`, `frontend/src/app/dashboard/*`, `frontend/src/components/{layout,dashboard,auth}/`, `backend/app/config.py`, `backend/app/api/__init__.py`, `backend/app/api/auth.py`.

### P1 — Course setup wizard & gates

**Screens:** T014–T028 (group `1372:34`).
**Scope (spec §4.8, §5 setup.py):** `courses.setup_status` + `setup_checklist` + `join_mode` + `enroll_code_active` migration; setup wizard route `/teacher/courses/[id]/setup` (StepWizard pattern component born here) orchestrating: basics → syllabus upload (existing `syllabus_imports`) → materials upload (existing documents pipeline) → schedule & venue (existing meetings + new `session_no`/`venue`/`release_state`/`topic_summary` columns) → material analyzer review (`analyze_course_setup` task: course map + missing-source detection) → ILO map builder (existing objectives + concept links) → session generation review → checkpoint generation review (`generate_checkpoints` task + `checkpoints`/`checkpoint_cards` tables in DRAFT states only — publish flow is P3) → previous-term memory import (STUB screen linking to P7; hide behind flag until P7) → score policy setup (`score_categories` table, seeded from pilot config) → class code (reveal/rotate/deactivate) → setup review checklist → publish (course-open gate) / missing-source error.
**New tables:** `checkpoints`, `checkpoint_cards`, `score_categories` (+courses/meetings columns). `concept_tags.target_kind` gains `checkpoint_card`.
**New task types:** `analyze_course_setup`, `generate_checkpoints` (grounded via `retriever.py` + `syllabus_grounding.py`, cards tagged via `concept_tagger.py`).
**Key files:** `app/services/{syllabus,pipeline,generator,retriever,concept_tagger}.py`, `app/models/curriculum.py`, `app/api/{courses,meetings,objectives,syllabus}.py`, `worker.py` dispatch.

### P2 — Student entry & enrollment

**Screens:** S003–S013 (group `1372:198`), T029–T035 (group `1372:66`; T036 memory summary deferred to P7).
**Scope (spec §4.7):** `readiness_responses` table (+RLS); readiness definitions from pilot config; join funnel `/student/join` (code → invalid/inactive → short preview → eligibility survey → ready check → optional diagnostic → recommendation result (claim-limit copy) → deep preview → readiness summary → course-not-open (setup gate) → pending approval → join success); join approval endpoints (`enrollments.status pending` → approve/deny) + teacher enrollment overview/roster/join-request/code-modal screens; teacher course overview (T029) + schedule table (T030); `enroll-by-code` respects `join_mode` + setup gate.
**Key files:** `app/api/courses.py` (enrollment), `app/models/course.py`, new `app/api/readiness.py`, `frontend/src/components/course/`.

### P3 — Checkpoint loop core

**Screens:** T037–T051 (group `1372:84`), S033–S042 (group `1372:270`).
**Scope (spec §4.2–4.3, §5):** checkpoint status machine to full `draft→teacher_editing→approved→scheduled→published→live→closed→archived`; `checkpoint_responses` (+RLS, learning_event emission, mastery enqueue); `attendance_records` + `checkpoint_launches` (signed short-lived QR tokens, window-bound, single-use per student, rate-limited scan); sessions list/detail/edit-release (T037–T039); checkpoint studio by session + review-point card editor + remove-reason modal + carry-over modal + publish confirmation (publish gate) + QR launch + live monitor (WS, reuse live-quiz hub pattern) + attendance roster result (+manual override with reason) + closed results + history + archive + waiting/no-data; student flow: QR landing `/attend/[token]` → checkpoint intro → confidence cards (ConfidenceScaleInput born here, −2..+2 from config) → final comments card → complete → missed/late → history → follow-up suggested → revisit response → attendance confirmed (mobile-first); `close_due_checkpoints` cron.
**Key files:** `app/services/{live_quiz,learning_events,mastery}.py` (patterns), new `app/api/{checkpoints,attendance}.py`, new models file `app/models/checkpoint.py`.

### P4 — Student workspace, checklist & calendar

**Screens:** S023–S032 + S072 (group `1372:246`), T052–T059 (groups `1372:116` + first of `1372:132`), full calendars T007/T008 + S018–S020 (deferred from P0).
**Scope (spec §4.6):** `work_items` + `work_item_progress` (+RLS) written transactionally by publish/response services (backfill for P3 checkpoints); student course workspace (overview, checklist, schedule table, sessions list/detail/locked, materials list + reader, activities list placeholder, no-materials/no-activities states); teacher materials library (upload, link-resource modal, auto session folders, preview, assign-to-session, remove confirmation, no-materials-published); full calendar month/week components (both roles) merging meetings + work_items (+ event detail drawer); dashboard next-action fed from work items; `mark_missed_work_items` cron.
**Key files:** `app/api/{documents,meetings}.py`, `app/services/pipeline.py`, new `app/api/checklist.py`, `frontend/src/components/{documents,dashboard}/`.

### P5 — Practice / quiz / activities / score

**Screens:** T060–T075 (group `1372:132`), S043–S059 + S073 (group `1372:292`).
**Scope (spec §4.4–4.5):** publish-settings columns on `quizzes` (+`grade_exports`, score gate on publish); practice builder/review/publish/results (existing quiz engine, `purpose='practice'`); quiz builder/review/publish/results (score-bearing disclosure before start — S050); `activities` + `activity_responses` (swipe/vote/comment_reaction) + builders + live activity monitor (WS) + results/evidence; student practice question types (MC, matching, ordering, short answer — matching/ordering are NEW question renderers), feedback, complete; student activity flows (waiting/swipe/vote/comment/submitted/record); score & participation record (S059); grade export CSV + audit (T075); work items for everything published; fold-in pass: flashcards/pronunciation/revision/live-quiz mounted under Activities areas.
**Key files:** `app/api/quizzes.py`, `app/models/quiz.py`, `app/services/{generator,live_quiz,gamification}.py`, new `app/api/{activities,scores}.py`.

### P6 — Follow-up & insights

**Screens:** S060–S065 + S070–S071 (group `1372:330`), T076–T079 (group `1372:168`).
**Scope:** wire the EXISTING evidence engine (`review.py`, `learning_notes`, `follow_up_actions`, `outcome_checks`, `instructor_alerts`, `concept_mastery`) into the new UI: follow-up items appear in student checklist (work_item source `follow_up`) + action detail + revisit response; learning profile + signal detail + ILO strength map + skill pattern map (skill taxonomy from pilot config; only render where evidence exists — no-evidence state otherwise); teacher course insights + signal detail drawer + evidence source view + effectiveness tracker; waiting-for-instructor-feedback state; new `app/api/insights.py` re-shaping existing data.
**Key files:** `app/api/{review,mastery,analytics,instructor_alerts}.py`, `app/services/{mastery,alerts,adaptive_jobs}.py`.

### P7 — Reports, course memory & hardening

**Screens:** T080–T087 (group `1372:168`), S066–S069 (group `1372:330`), completes T023 + T036.
**Scope (spec §4.9–4.10):** `reports` table + `draft_report` job (weekly cadence via cron + end-term; drafts ONLY from reviewed learning notes / `report_eligibility`); teacher report archive/detail/edit/approve/send/export + evidence appendix + export-share settings (send gate + audit); student report archive/weekly/end-term/delivery state; course memory API/UI over `course_record_items` (list/detail/decide keep-revise-reject-carry_forward) + next-term suggestions + memory summary (T036) + memory import into setup (T023, unstub P1); **hardening:** CodeQL/Semgrep SAST + pip-audit/npm audit in CI; i18n key audit (no hardcoded strings); seed-data production exclusion check; `audit_events` coverage check; full-suite E2E pass; `design-review` polish pass over all new screens.
**Key files:** `app/models/evidence.py` (`course_record_items`), `app/services/adaptive_jobs.py` (note drafting patterns), new `app/api/{reports,memory}.py`, `.github/workflows/`.

---

## Handoff Log (append-only; newest first)

### 2026-07-07 — Planning session (Fable 5)
- Spec approved + committed (`1e655bd`). This roadmap + detailed P0 plan written and committed.
- Nothing executed yet. Next action: **execute P0 plan** (`2026-07-07-meli-cle-p0-shell-foundations.md`).
- Gotchas discovered during planning: `docs/` is gitignored — use `git add -f` for spec/plan/roadmap files. `use-role.ts` currently guesses role from email domain client-side (P0 fixes). Adaptive-engine RESUME.md was stale and has been superseded by this roadmap.
