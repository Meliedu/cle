# P4 — Student Workspace, Checklist & Calendar: Detailed Implementation Plan

> **Phase:** P4 of the Meli × CLE roadmap (`docs/superpowers/plans/2026-07-07-meli-cle-roadmap.md`).
> **Spec:** `docs/superpowers/specs/2026-07-06-meli-cle-checkpoint-loop-design.md` §4.6 (work-item checklist spine), §4.1 (sessions=meetings), §4.2 (checkpoints — the first work-item source), §5 (API surface, `checklist.py` row).
> **Branch:** `feat/cle-p0-shell`. **Depends on:** P3's checkpoint publish + response services (the work-item spine hooks into them), P1's `courses.setup_status`/`course_meetings.release_state`, P0's `calendar-view.tsx` (deferred full month/week grids), P2's `readiness_responses` RLS pattern.
> **Method:** `superpowers:writing-plans` shape — TDD, one committable task at a time, failing test first. Check boxes IN THIS FILE as tasks land.

---

## Session bootstrap (every new session for this phase starts here)

1. Read the roadmap Global Rules + the P4 phase brief + this file top-to-bottom.
2. Read spec §4.6 (work_items / work_item_progress), §4.1–4.3 (how sessions & checkpoints relate to the spine), §5 (`checklist.py`).
3. **Confirm the migration head before writing any migration:** `python -m alembic heads`. At plan-writing time the P3 head is **`c3a9f0e1d2b4`** (`checkpoint_launches`, chained `d94257fc717c` → `a1f3c7e29b04` → `b2e4d8f1a067` → `c3a9f0e1d2b4`). Chain the first P4 migration from the ACTUAL current head, not this literal.
4. Re-read the REAL code each task names before editing — never trust this plan over the code:
   - `backend/app/models/checkpoint.py` (`CheckpointResponse` is the student-owned RLS shape to mirror for `work_item_progress`), `backend/app/models/attendance.py` (`CheckpointLaunch` is the operational/no-RLS shape to mirror for `work_items`), `backend/app/models/readiness.py`.
   - `backend/alembic/versions/d94257fc717c_readiness_responses_table_rls.py` (the owner-isolation RLS migration to COPY) + `a1f3c7e29b04_checkpoint_responses_table_rls.py` + `b2e4d8f1a067_attendance_records_table_rls.py` (already-copied precedents).
   - `backend/app/api/checkpoints.py::publish_checkpoint` (lines ~599–640 — the transactional publish seam where the `checkpoint` work_item write hooks in, BEFORE `await db.commit()`) + `close_checkpoint`.
   - `backend/app/services/checkpoint_responses.py::submit_checkpoint_response` (the answer upsert commits at ~line 181; the `work_item_progress` write must ride the SAME commit as the answer, NOT the best-effort evidence block below it).
   - `backend/app/services/worker.py` (`_claim_and_run_cron`, `_run_cron_ticks` registration list ~lines 567–574, `_body_close_due`/`_body_overdue`/`_body_decay` shape — the `mark_missed_work_items` cron mirrors these; `CronRun` watermark).
   - `backend/app/api/meetings.py::calendar_feed` (`GET /courses/{course_id}/calendar` — ALREADY merges meetings + assignments into a flat `{id,kind,title,at,...}` event list; P4 adds `work_item` as a third source), `_accessible_course` (student-or-owner guard), `MAX_CALENDAR_DAYS`.
   - `backend/app/api/documents.py` (upload/list/delete; `_require_course_instructor`; `verify_enrollment` for reads) + `backend/app/models/document.py` (**already has `meeting_id` + `module_id` FK columns** — assign-to-session is a PATCH, not new machinery) + `backend/app/services/storage.py` (`build_r2_key`, `delete_file_safe`; a signed-URL/preview helper if present).
   - `backend/app/api/__init__.py` (router registration — add `checklist_router`; note the existing `attendance` triple-router registration pattern).
   - `backend/app/api/_helpers.py::verify_enrollment` (P3 fix: requires `status='active'` — the student-surface guard) + `backend/app/api/deps.py` (`get_current_user` sets `app.current_user_id` GUC, `require_instructor`, `require_student`, `get_owned_course`).
   - Frontend: `frontend/src/components/course/course-workspace-shell.tsx` (`CourseTab` union already includes `materials`/`activities`/`sessions`; `sessions` is `enabled:true` post-T16; P4 flips `materials`+`activities` to `enabled:true` and adds routes), `frontend/src/app/(app)/student/` (has calendar/courses/dashboard/join/notifications/profile — NO student course workspace yet; P4 adds `student/courses/[courseId]/…`), `frontend/src/app/(app)/teacher/courses/[courseId]/` (add `materials/`), `frontend/src/components/documents/` (`upload-zone.tsx`, `document-selector.tsx`), `frontend/src/components/dashboard/` (`calendar-view.tsx` deferred banner, `mini-calendar.tsx`, `upcoming-swarms.tsx`, `dashboard-home.tsx`, `dashboard-preview-events.ts`), `frontend/src/hooks/` (`use-documents.ts`, `use-meetings.ts`, `use-checkpoints.ts`, `use-authed-query.ts`), `frontend/messages/en.json` (namespaces `student.*` = only `join` today; `teacher.*` = `setup/course/sessions/enrollment`; `patterns.*`).
5. Before each UI task pull its Figma node via `get_metadata` on the GROUP frame first (individual screen ids are children — they are NOT in this plan), then `get_design_context` per screen. Group ids in the table below.
6. Session-end: update the roadmap Phase Tracker + append a Handoff Log entry; commit with `git add -f` (docs/ is gitignored). **The controller owns roadmap/RESUME edits — do not touch them from a task.**

---

## Decisions locked (reconciliation with spec §4.6 + real P3 code)

1. **`work_items.source_kind` ships the FULL spec §4.6 enum now; P4 only WRITES the sources that exist by P4.** CHECK enum = `checkpoint | practice | quiz | activity | material | follow_up | report` (verbatim from §4.6). P4 writes `checkpoint` (publish path, B4), `material` (assign-to-session, B8), and `follow_up` (a `follow_up`-kind checkpoint publish, B4). `practice`/`quiz`/`activity` are valid enum values first WRITTEN in P5, `report` in P7 — shipping the full CHECK now mirrors how P1 shipped the full `checkpoints.status` enum but only wrote `draft`/`teacher_editing`, so no later widening. **`meeting` is deliberately NOT a `source_kind`** — spec §4.6 does not list it; sessions live in `course_meetings` and feed the calendar directly. The calendar merges TWO independent sources (meetings + work_items), it does not fold meetings into the spine.
2. **`work_item_progress` is the student-owned RLS table (owner = `user_id`); `work_items` is course-scoped, teacher-authored, NO RLS, endpoint-guarded.** `work_item_progress` COPIES the `readiness_responses` migration `d94257fc717c` verbatim (ENABLE ROW LEVEL SECURITY + `work_item_progress_owner_isolation` policy `USING/WITH CHECK (user_id = current_setting('app.current_user_id', true)::uuid)`) — same shape as `checkpoint_responses`/`attendance_records`. `work_items` mirrors `CheckpointLaunch` (operational, no RLS): every read is enrollment- or owner-guarded at the endpoint. `status` CHECK on progress = `pending | in_progress | submitted | late | missed | completed | follow_up_assigned` (§4.6).
3. **Transactional-write seam.** The `work_item` row for a checkpoint is created in the SAME transaction as its publish, inside `api/checkpoints.py::publish_checkpoint` BEFORE `await db.commit()` (alongside `_append_review_action`) — so a published checkpoint always has its checklist row atomically. Creation is idempotent via a **unique index on `(course_id, source_kind, source_id)`** + `pg_insert(...).on_conflict_do_nothing(...)`, so a re-publish or the backfill can never double-insert. `work_item_progress` is upserted in `services/checkpoint_responses.py::submit_checkpoint_response` **as part of the answer's own commit** (before line ~181 `await db.commit()`), NOT the best-effort evidence block below it — progress durability must equal answer durability (a lost progress row would desync the checklist). The upsert keys on `(work_item_id, user_id)` and sets `status` from the response (`submitted`/`late`, `completed` when all live cards answered on time). A missing `work_item` row (pre-backfill edge) is a best-effort no-op, never a 500.
4. **Backfill for P3 checkpoints already published.** A data step (Alembic data migration, or an idempotent `backfill_work_items(session)` service invoked once) inserts a `checkpoint` work_item for every existing checkpoint in `published|live|closed|archived` that lacks one — idempotent on the `(course_id, source_kind, source_id)` unique index. It does NOT synthesize historical `work_item_progress` (progress is derived forward from new submissions; the checklist read (B6) derives per-student status from `checkpoint_responses` for pre-backfill items as a fallback so history isn't blank).
5. **Calendar merges by EXTENDING the existing feed, not building new.** `meetings.py::calendar_feed` already returns a flat event list `{id, kind, title, at, …}` with `kind ∈ meeting|assignment`. P4 adds a third source: `work_items` whose `due_at`/`close_at` fall in `[from_date, to_date)`, `kind="work_item"`, carrying `source_kind` and — for a student — that student's `work_item_progress.status` (owner-scoped), or a teacher aggregate. The full month/week grids + event-detail drawer consume this ONE endpoint. `_accessible_course` (student-or-owner) already gates it; the 366-day cap stays.
6. **Materials-to-session uses the EXISTING `documents.meeting_id` column** (already on the model — no new join table, contra the "auto session folders" phrasing in the brief). Assign-to-session = `PATCH` `document.meeting_id`. "Auto session folders" = the materials API/UI GROUPS documents by `meeting_id` (+ an "Unassigned" bucket). Assigning a material to a `released` session optionally creates a `material` work_item (`required=false`, `score_bearing=false`) so it surfaces on the student checklist/calendar; unassigning removes it. Preview/reader uses a signed R2 URL (reuse `storage.py`; if no signed-URL helper exists, add one there — do NOT stream bytes through the API).
7. **Dashboard "next action" reads the spine, not the local todo widget.** `frontend/src/hooks/use-todos.ts` is a localStorage scratch list — leave it. The dashboard next-action is a NEW read over `work_item_progress` (the next `pending`/`in_progress` item by `due_at`), exposed by a checklist endpoint (B6) and consumed in `dashboard-home.tsx`.

---

## Figma node map (file `EhzLyFCTZBIGU4iNyHUqvl`, page `final`)

Individual screen node ids are CHILDREN of these group frames and are intentionally not listed — call `get_metadata` on the group first, then `get_design_context` per screen.

| Group frame | Node | Screens (from brief) |
|---|---|---|
| Student "5. Course Workspace" | `1372:246` | S023–S032 + S072 (overview, checklist, schedule table, sessions list/detail/locked, materials list + reader, activities placeholder, no-materials / no-activities states) |
| Teacher "materials library" (part A) | `1372:116` | T052–T059 (materials upload, link-resource modal, session folders, preview, assign-to-session, remove confirmation, no-materials-published) |
| Teacher group (part B, materials tail) | `1372:132` (first frames only) | remainder of T052–T059 (the rest of `1372:132` is P5 practice/quiz — do NOT build it here) |
| Teacher shell (P0-deferred calendars) | `1372:6` | T007 calendar-month, T008 calendar-week |
| Student shell (P0-deferred calendars) | `1372:226` | S018 calendar-month, S019 calendar-week, S020 calendar-event-detail |

---

## Tasks

Each task: failing test first → minimal impl → refactor → code review (`/code-review` or code-reviewer agent) → conventional commit. Backend B1–B10, frontend F1–F9.

### Backend

- [x] **B1 — `work_items` model + migration (course-scoped, no RLS).**
  - Test first (`tests/test_work_item_model.py`): columns `course_id FK`, `source_kind` (CHECK full §4.6 enum, Decision 1), `source_id UUID`, `title`, `required bool default true`, `score_bearing bool default false`, `due_at/close_at` (nullable, tz), `visible_from` (nullable, tz), `created_by FK users`; UUID PK + `TimestampMixin` + `SoftDeleteMixin`; **unique index `uq_work_items_course_source` on `(course_id, source_kind, source_id)`** (Decision 3 idempotency). No RLS (mirrors `CheckpointLaunch`).
  - Model `WorkItem` in a NEW `app/models/work_item.py`; migration chains from the confirmed P3 head. Register in `app/models/__init__.py`.
  - Commit `feat(checklist): work_items model + course-source unique index`.

- [x] **B2 — `work_item_progress` model + owner-isolation RLS migration.**
  - Test first (`tests/test_work_item_progress_model.py`): columns `work_item_id FK`, `user_id FK`, `status` (CHECK `pending|in_progress|submitted|late|missed|completed|follow_up_assigned`), `updated_at`; unique `(work_item_id, user_id)`; UUID PK + `TimestampMixin`.
  - Model `WorkItemProgress` in `app/models/work_item.py`. Migration COPIES `d94257fc717c` structure verbatim: create table + `ix_work_item_progress_user_id` + `ENABLE ROW LEVEL SECURITY` + `work_item_progress_owner_isolation` policy on `user_id` (Decision 2). Chain from B1.
  - Commit `feat(checklist): work_item_progress model + owner-isolation RLS`.

- [x] **B3 — Work-item write service (`app/services/work_items.py`).**
  - Test first (`tests/test_work_items_service.py`): `upsert_work_item(db, *, course_id, source_kind, source_id, title, required, score_bearing, due_at, close_at, created_by)` uses `pg_insert(...).on_conflict_do_nothing(index_elements=[...]).returning(...)` then re-fetches on conflict (mirrors `mastery.py::_get_or_create_mastery`) — a second call with the same `(course_id, source_kind, source_id)` returns the SAME row, no `IntegrityError`; caller commits. `upsert_progress(db, *, work_item_id, user_id, status)` upserts on `(work_item_id, user_id)`; caller commits. `remove_work_item(db, work_item)` soft-deletes. Pure helpers — no HTTP, no commit inside (the transactional callers own the commit, Decision 3).
  - Commit `feat(checklist): work-item upsert + progress service`.

- [x] **B4 — Transactional `checkpoint` work_item on publish + backfill.**
  - Test first (`tests/test_checkpoints_api.py` additions): after `POST /checkpoints/{id}/publish` succeeds, a `work_items` row exists with `source_kind='checkpoint'`, `source_id=checkpoint.id`, `due_at=close_at`, `required=true`; re-publishing (or a `follow_up`-kind publish) does NOT duplicate (unique index); the write is rolled back if the publish transaction fails (assert atomicity). Plus `tests/test_backfill_work_items.py`: `backfill_work_items(session)` inserts one row per existing `published|live|closed|archived` checkpoint lacking one and is idempotent on re-run.
  - Impl: call `upsert_work_item(...)` inside `api/checkpoints.py::publish_checkpoint` BEFORE `await db.commit()` (alongside `_append_review_action`); title from `cp.title`, `source_kind` = `"checkpoint"` (both `session` and `follow_up` checkpoint kinds map to the `checkpoint` source_kind — the `follow_up` SPINE source_kind is reserved for P6 follow-up actions, not checkpoints). Backfill as a data migration OR `services/work_items.py::backfill_work_items` run once + guarded idempotent.
  - Commit `feat(checklist): publish writes checkpoint work_item (transactional) + backfill`.

- [x] **B5 — Transactional `work_item_progress` on response submission.**
  - Test first (`tests/test_checkpoint_responses.py` additions): after `POST /checkpoints/{id}/responses`, the student's `work_item_progress` for the checkpoint's work_item exists with `status='submitted'` (or `late` when past `close_at`); once ALL live cards are answered on time it flips to `completed`; the progress row shares the answer's commit (a forced failure of the evidence block below does NOT lose progress); a missing work_item (pre-backfill) is a no-op, not a 500. Wrong-owner cannot write another student's progress (RLS + `user_id` from the authenticated caller).
  - Impl: in `services/checkpoint_responses.py::submit_checkpoint_response`, resolve the checkpoint's work_item and call `upsert_progress(...)` BEFORE the answer's `await db.commit()` (Decision 3) — same transaction. Derive `completed` by counting the student's non-late responses vs live card count (reuse the `_derive_history_status` logic shape from `api/checkpoints.py`; extract a shared helper if it de-duplicates cleanly).
  - Commit `feat(checklist): response submission writes work_item_progress (transactional)`.

- [x] **B6 — Checklist router (`app/api/checklist.py`): student read + teacher manager + next-action.**
  - Test first (`tests/test_checklist_api.py`): `GET /courses/{id}/checklist` (student, enrollment-scoped via `verify_enrollment`) returns the course's non-deleted work_items merged with the caller's own `work_item_progress` (derived status for pre-backfill items from `checkpoint_responses` fallback, Decision 4), ordered by `due_at` then `visible_from`; `GET /courses/{id}/next-action` returns the single next `pending`/`in_progress` item by `due_at` (Decision 7) or `null`; teacher manager `GET /courses/{id}/work-items` (owner-guarded, no progress), `POST` (manual add), `PATCH /work-items/{id}` (reorder/required/title), `DELETE /work-items/{id}` (soft-remove). A non-enrolled user → 403; non-owner teacher on manager routes → 404.
  - Impl: `app/api/checklist.py` (course-scoped + item-scoped routers), schemas in `app/schemas/work_item.py`. Register all routers in `app/api/__init__.py`.
  - Commit `feat(checklist): student checklist + next-action + teacher work-item manager`.

- [x] **B7 — Calendar feed merges work_items.**
  - Test first (`tests/test_calendar_feed.py` additions): `GET /courses/{id}/calendar?from&to` now also emits `kind="work_item"` events for work_items with `due_at`/`close_at` in-window, each carrying `source_kind` and (for a student) that student's `work_item_progress.status`; a teacher sees the same items without per-student status; the 366-day cap + `from<to` validation are unchanged; a student sees only their own progress overlay (owner-scoped).
  - Impl: extend `meetings.py::calendar_feed` (append the third source; keep the flat envelope + sort). Reuse `_accessible_course` for role. No new endpoint.
  - Commit `feat(calendar): merge work_items into the course calendar feed`.

- [x] **B8 — Materials library API: assign-to-session, session folders, preview.**
  - Test first (`tests/test_documents_materials.py`): `PATCH /courses/{id}/documents/{doc_id}` (owner-guarded) sets `meeting_id` (assign) or `null` (unassign) — a foreign meeting_id → 404/422; assigning to a `released` session creates a `material` work_item (idempotent), unassigning soft-removes it; `GET /courses/{id}/materials` returns documents GROUPED by `meeting_id` (+ "unassigned" bucket) with each session's `release_state` (Decision 6); `GET /courses/{id}/documents/{doc_id}/preview` returns a short-lived signed R2 URL (owner or enrolled student on a released session), never raw bytes.
  - Impl: extend `app/api/documents.py` (new PATCH + materials + preview handlers, reuse `_require_course_instructor` / `verify_enrollment`); signed-URL helper in `app/services/storage.py` if absent. `material` work_item via `upsert_work_item` (B3).
  - Commit `feat(materials): assign-to-session, session folders, signed preview`.

- [x] **B9 — `mark_missed_work_items` cron.**
  - Test first (`tests/test_mark_missed_work_items.py`): `mark_missed_work_items(session)` flips a student's `work_item_progress` to `missed` for `required` work_items whose `close_at`/`due_at` is past AND the student is actively enrolled AND has no `completed`/`submitted` progress; idempotent (re-run no-ops); never touches non-required items or already-terminal statuses. Runs privileged (worker connection is BYPASSRLS per `28236be3d7b3`) so it can write every student's row.
  - Impl: `mark_missed_work_items` in `app/services/work_items.py` + `_body_mark_missed` + registration `_claim_and_run_cron("mark_missed_work_items", timedelta(hours=1), _body_mark_missed)` in `worker.py::_run_cron_ticks` (mirror `_body_close_due`).
  - Commit `feat(checklist): mark_missed_work_items cron`.

- [x] **B10 — RLS isolation test for `work_item_progress`.**
  - Test first: COPY `tests/test_checkpoint_responses_rls.py` (or `test_readiness_rls.py`) into `tests/test_work_item_progress_rls.py`: under `SET ROLE meli_app`, user A's progress row is invisible/immutable to user B (SELECT hides, UPDATE/DELETE affect 0 rows, INSERT of A's `user_id` rejected by WITH CHECK), GUC switch-back restores visibility, blank GUC fails closed. Skip-guard when `meli_app` absent. Seed/teardown on `async_engine`.
  - Commit `test(checklist): RLS owner-isolation for work_item_progress`.

### Frontend (pull Figma per screen via `get_metadata` on the group first)

- [x] **F1 — Hooks + `CourseTab` wiring (`use-work-items`, `use-checklist`, calendar, materials).**
  - New `hooks/use-work-items.ts` (`useChecklist(courseId)`, `useNextAction(courseId)`, teacher `useWorkItems`/`useAddWorkItem`/`useUpdateWorkItem`/`useRemoveWorkItem` mirroring `use-checkpoints.ts` shape + `authedWrite`); new `hooks/use-calendar.ts` (`useCalendar(courseId, from, to)` over `/courses/{id}/calendar`); extend `use-documents.ts` with `useMaterials`/`useAssignMaterial`/`useMaterialPreview`. Flip `materials`+`activities` to `enabled:true` in `course-workspace-shell.tsx` `TABS` and add the student `CourseTab` shape if a student shell diverges. Vitest for one query + one mutation (mocked, per offline convention).
  - Commit `feat(hooks): work-items, checklist, calendar, materials hooks + enable tabs`.

- [x] **F2 — Student course workspace shell + overview + no-content states (S023, S072).**
  - New route tree `student/courses/[courseId]/` (Next.js 16: `page` props `params` is a **Promise — `await params`**; see `frontend/AGENTS.md`). A student workspace shell (mirror `course-workspace-shell.tsx` but student tabs: overview / checklist / schedule / sessions / materials / activities); overview (S023) summarizing next-action + progress; designed no-materials / no-activities EmptyStates (S072). i18n `student.workspace.*`. Tokens only. Pull group `1372:246`.
  - Commit `feat(student): course workspace shell + overview + empty states`.

- [x] **F3 — Student checklist + schedule table (S024–S026).**
  - Checklist view (S024/S025) over `useChecklist` — grouped by status with one visual treatment per `work_item_progress.status` (reuse `ReviewStateChip`/`StateBanner` tones); schedule table (S026) over `useMeetings` (reuse P2 teacher schedule-table shape, student-read). i18n `student.checklist.*` / `student.schedule.*`. Pull the relevant `1372:246` children.
  - Commit `feat(student): checklist + schedule table`.

- [x] **F4 — Student sessions list / detail / locked (S027–S029).**
  - Sessions list (S027) from `useMeetings` filtered to `release_state ∈ released|completed`; session detail (S028) showing topic summary + that session's materials + any session checkpoint; locked state (S029, a designed EmptyState for a `locked` session — reason + "opens when your instructor releases it"). i18n `student.sessions.*`. Pull `1372:246` children.
  - Commit `feat(student): sessions list/detail/locked`.

- [x] **F5 — Student materials list + reader + activities placeholder (S030–S032).**
  - Materials list (S030) grouped by session folder from `useMaterials`; material reader (S031) opening the signed preview URL (`useMaterialPreview`) in an embedded viewer with a download fallback; activities list placeholder (S032, designed "activities arrive soon" EmptyState — P5 fills it). i18n `student.materials.*` / `student.activities.*`. Pull `1372:246` children.
  - Commit `feat(student): materials list + reader + activities placeholder`.

- [x] **F6 — Teacher materials library: upload + link-resource + session folders (T052–T054).**
  - `teacher/courses/[courseId]/materials/` route (await `params`). Upload (T052, reuse `components/documents/upload-zone.tsx` + `use-documents` upload); link-resource modal (T053 — external URL/resource entry); session-folders view (T054 — documents grouped by `meeting_id` via `useMaterials`, "Unassigned" bucket). i18n `teacher.materials.*`. Pull `1372:116` (+ first `1372:132` frames only).
  - Commit `feat(teacher): materials upload + link-resource + session folders`.

- [x] **F7 — Teacher materials: preview + assign-to-session + remove + no-materials (T055–T059).**
  - Material preview (T055, signed URL); assign-to-session control (T056, `useAssignMaterial` PATCH `meeting_id`); remove confirmation modal (T057/T058); no-materials-published EmptyState (T059, designed reason + "upload your first material"). Surface any typed error (foreign meeting_id) as a `StateBanner`. i18n `teacher.materials.*`. Pull `1372:116` children.
  - Commit `feat(teacher): material preview + assign-to-session + remove + empty state`.

- [x] **F8 — Full calendar month/week + event-detail drawer, both roles (T007/T008 + S018–S020).**
  - Replace the `calendar-view.tsx` "coming soon" `StateBanner` with real month + week grid components (`components/calendar/`), consuming `useCalendar` (meetings + assignments + work_items, Decision 5). Month grid (T007/S018), week grid (T008/S019), event-detail drawer routing by `kind` (`meeting`/`assignment`/`work_item`) (S020). `prefers-reduced-motion` respected; keyboard-navigable grid. Shared by both role lanes (the page composition already is). i18n `patterns.calendar.*`. Pull `1372:6` (T007/T008) + `1372:226` (S018–S020). Vitest for the month-grid date math.
  - Commit `feat(calendar): full month/week grids + event-detail drawer`.

- [x] **F9 — Dashboard next-action from work items + P4 close-out.**
  - Feed `dashboard-home.tsx`'s next-action slot from `useNextAction` (Decision 7 — NOT the localStorage `use-todos` widget, which stays). Designed no-next-action state. Playwright happy-path (publish checkpoint → student checklist shows it → answer → progress flips → appears on calendar) where infra allows; else vitest against mocked hooks (per P0–P3 offline convention). i18n `student.dashboard.*`. **P4 close-out is a SEPARATE controller step** — this task ships the code only; do not edit the roadmap here.
  - Commit `feat(dashboard): next-action fed from work items + P4 verification`.

---

## Self-review checklist (spec §4.6 coverage before P4 close-out)

- [x] `work_items` ships the full §4.6 `source_kind` CHECK; P4 writes `checkpoint`/`material` only; `(course_id, source_kind, source_id)` unique enforced (B1, Decision 1).
- [x] `work_item_progress` is the student-owned RLS table (owner-isolation proven under `meli_app`); `work_items` is no-RLS, endpoint-guarded (B2/B10, Decision 2).
- [x] The `checkpoint` work_item is written TRANSACTIONALLY inside `publish_checkpoint` (atomic with publish, idempotent) + existing P3 checkpoints backfilled idempotently (B4, Decisions 3–4).
- [x] `work_item_progress` rides the answer's OWN commit in `submit_checkpoint_response` (not the best-effort evidence block); missing work_item is a no-op, never a 500 (B5, Decision 3).
- [x] Student checklist + calendar overlay + dashboard next-action all read the SINGLE spine (`work_item_progress`), not a parallel list (B6/B7/F9, Decision 7).
- [x] Calendar EXTENDS the existing `calendar_feed` with `kind="work_item"`; meetings stay a separate source (no `meeting` source_kind); 366-day cap + role scoping intact (B7, Decision 5).
- [x] Materials assign-to-session uses the existing `documents.meeting_id` column; session folders = group-by-meeting; signed-URL preview, never raw bytes; foreign meeting_id refused (B8, Decision 6).
- [x] `mark_missed_work_items` cron idempotent + registered in `_run_cron_ticks` (B9).
- [x] Student S023–S032 + teacher T052–T059 shipped with designed no-materials / no-activities / locked-session states (never blank divs) (F2–F7).
- [x] Full month/week calendars + event-detail drawer replace the P0 "coming soon" banner for BOTH roles (F8; T007/T008 + S018–S020).
- [x] Next.js 16: every new `page` awaits `params` (Promise); `proxy.ts` not `middleware.ts`; read `frontend/AGENTS.md` before FE work.
- [x] No hardcoded strings (next-intl `student.*`/`teacher.*`/`patterns.*`), no hardcoded colors (tokens.css), conventional commits, code review per task cluster.
