# P3 — Checkpoint Loop Core: Detailed Implementation Plan

> **Phase:** P3 of the Meli × CLE roadmap (`docs/superpowers/plans/2026-07-07-meli-cle-roadmap.md`).
> **Spec:** `docs/superpowers/specs/2026-07-06-meli-cle-checkpoint-loop-design.md` §4.2 (checkpoints/cards/responses), §4.3 (attendance + QR), §3.4 (gates), §5 (endpoints + live monitor WS).
> **Branch:** `feat/cle-p0-shell`. **Depends on:** P1 checkpoint drafts + P2 active enrollments + P2 `readiness_responses` RLS pattern.
> **Method:** `superpowers:writing-plans` shape — TDD, one committable task at a time, failing test first. Check boxes IN THIS FILE as tasks land.

---

## Session bootstrap (every new session for this phase starts here)

1. Read the roadmap Global Rules + this file top-to-bottom.
2. Read spec §4.2, §4.3, §3.4, §5 (the live-monitor row).
3. Re-read the REAL code the tasks name before editing — never trust this plan over the code:
   - `backend/app/models/checkpoint.py` (Checkpoint FULL status enum + CheckpointCard already exist from P1 Task 3 — P3 adds NO columns to these, only 3 new tables).
   - `backend/app/api/checkpoints.py` (P1 DRAFT-only router: `_EDITABLE_STATUSES`, `_owned_checkpoint`, `_assert_editable` REVIEW_REQUIRED, `_bump_editing`, card CRUD). P3 ADDS publish-path + student endpoints here.
   - `backend/app/services/live_quiz.py` (`ConnectionManager` singleton `manager` — `connect`/`disconnect`/`broadcast`/`get_lock`) + `backend/app/api/live.py` (`websocket_live`: `?token=` → `verify_jwt` → resolve user → enrollment check → `manager.connect` loop). **Reuse this, do not build new WS infra.**
   - `backend/app/services/learning_events.py` (`record_attempt_event(..., stage=..., source_kind=..., source_id=...)` — caller commits) + `backend/app/api/quizzes.py::_enqueue_mastery` (adds `update_concept_mastery` Task rows; caller commits; wrapped best-effort).
   - `backend/app/models/readiness.py` + `backend/alembic/versions/d94257fc717c_readiness_responses_table_rls.py` (the student-owned RLS migration pattern to COPY) + `backend/tests/test_readiness_rls.py` (the RLS enforcement test pattern to COPY).
   - `backend/app/api/deps.py` (`get_current_user` sets `app.current_user_id` GUC via `set_config(..., false)`; `require_instructor`, `require_student`, `get_owned_course` → 404 not 403).
   - `backend/app/services/canvas_oauth.py` (`encode_state`/`decode_state`: **PyJWT HS256 signed token + one-shot nonce + `settings.canvas_state_secret` validated ≥32 bytes** — the QR-token mechanism to mirror).
   - `backend/app/middleware/rate_limit.py` (`_is_rate_limited_path`, `_RATE_LIMITED_REGEXES`, per-minute GET cap vs per-hour non-GET cap — the scan endpoint extends this).
   - `backend/app/services/worker.py` (`_claim_and_run_cron(name, cadence, body)` + `_run_cron_ticks` registration + `_body_decay`/`_body_overdue` cron-body shape + task dispatch at `process_task`).
   - `backend/app/pilot/base.py` + `cle.py` (`ConfidenceScale` min=-2 max=2 labels; the checkpoint confidence card renders these).
   - Frontend: `frontend/src/components/join/readiness-question.tsx` (inline `scale` branch → extract `ConfidenceScaleInput`), `frontend/src/hooks/use-checkpoints.ts` (P1 hook — extend), `frontend/src/hooks/use-live-quiz.ts` (WS client pattern), `frontend/src/components/course/course-workspace-shell.tsx` (`TABS` — flip a P3 tab `enabled`), `frontend/src/app/(app)/teacher/courses/[courseId]/` (route tree), `frontend/src/components/patterns/` (PageHeader/StateBanner/EmptyState/ReviewStateChip/tones), `frontend/src/hooks/use-authed-query.ts`, `frontend/src/hooks/use-pilot-config.ts`.
4. Before each UI task pull its Figma node via `get_design_context` (ids in the table below).
5. Session-end: update the Phase Tracker + append a Handoff Log entry in the roadmap; commit with `git add -f` (docs/ is gitignored).

---

## Decisions locked (reconciliation with P1/P2 + spec)

1. **Status machine completes the P1 enum, validated in the service layer.** P1 shipped the full CHECK enum (`draft→teacher_editing→approved→scheduled→published→live→closed→archived`) but only WROTE `draft`/`teacher_editing`. P3 adds a single source of truth — `app/services/checkpoints.py::assert_transition(from, to)` with an explicit allowed-edge map — and drives every publish-path endpoint through it. **P3 DELETES `test_p1_has_no_publish_route`** (`backend/tests/test_checkpoints_api.py` line ~331) and replaces it with real publish-path endpoint + illegal-transition tests. `_assert_editable` (card CRUD → REVIEW_REQUIRED once past draft) stays as-is.
2. **`checkpoint_responses` + `attendance_records` are student-owned RLS tables** copying the `readiness_responses` migration `d94257fc717c` verbatim (ENABLE ROW LEVEL SECURITY + `owner_isolation` policy `USING/WITH CHECK (user_id = current_setting('app.current_user_id', true)::uuid)`). Owner = `user_id`. Teacher roster/results reads go through owner-guarded course-scoped endpoints (the running app connects privileged / BYPASSRLS per migration `28236be3d7b3`); RLS is defense-in-depth that bites only under the non-superuser `meli_app` role, proven by copied RLS tests (Task 14). `checkpoint_launches` is teacher/operational (no student ownership) → **no RLS**, guarded at the endpoint layer.
3. **QR token = PyJWT HS256 signed token, mirroring `canvas_oauth.encode_state`.** New `settings.checkpoint_token_secret` (validated ≥32 bytes exactly like `canvas_state_secret`; startup-required only when checkpoints/QR are used). The signed payload embeds `{launch_id, checkpoint_id, meeting_id, jti, exp=window_end}`. **Short-lived + window-bound** via `exp` = `checkpoint_launches.window_end`; **rotating** via a rotate operation that closes the prior launch (`status='closed'`) and issues a new `launch_id`/`jti`; **single active launch per checkpoint** via a partial unique index on `(checkpoint_id) WHERE status='active'`; **single-use per student** via `attendance_records` unique `(meeting_id, user_id)` (a second scan is an idempotent no-op / 200, never a duplicate). **Scan rate-limited** by extending `middleware/rate_limit.py`: add `_ATTEND_SCAN_REGEX = re.compile(r"^/api/attend/[^/]+$")` to a new branch in `_is_rate_limited_path`, counted against its own per-minute cap (dedicated method/endpoint class, like the GET-poll cap) so QR-scan floods can't burn the RAG generation quota and vice-versa. The scanning student is authenticated, so the middleware's existing `verify_jwt`→user lookup keys the limit per user.
4. **Live monitor REUSES the live-quiz WS hub.** No new WebSocket system. Reuse `live_quiz.ConnectionManager` (`connect`/`broadcast`/`disconnect`/`get_lock`) — instantiate a second module-level `monitor_manager = ConnectionManager()` in a new `app/services/checkpoint_monitor.py` (or reuse the singleton with checkpoint-id-namespaced session keys) and copy `websocket_live`'s auth preamble (`?token=` → `verify_jwt` → resolve user → owner/enrollment check). The monitor broadcasts `{submission_count, confidence_distribution, closed}`; the student response-submission service calls `monitor_manager.broadcast(checkpoint_id, ...)` after commit.
5. **Evidence seam — one path only.** Checkpoint response submission calls `record_attempt_event(stage="during_class", source_kind="checkpoint_card", source_id=card_id, value={confidence|text})` and, for concept-tagged `review_point` cards, enqueues an `update_concept_mastery` Task (mirroring `quizzes.py::_enqueue_mastery`, best-effort try/except so attempt durability is preserved). Confidence→outcome mapping: normalized `(confidence − min) / (max − min)` = `(c+2)/4` on the −2..+2 scale. `final_comments` text + attendance NEVER emit mastery (attendance = participation only, doc rule). No parallel evidence system.
6. **Confidence scale from pilot config; `ConfidenceScaleInput` extracted for reuse.** The `scale` branch currently inlined in `components/join/readiness-question.tsx` is extracted to `components/patterns/confidence-scale-input.tsx` (−2..+2 from `usePilotConfig().confidence_scale`), consumed by BOTH readiness `scale` questions and the checkpoint confidence cards. Mobile-first (single-column stack on narrow viewports).

---

## Figma node map (file `EhzLyFCTZBIGU4iNyHUqvl`, page `final`)

Teacher group `1372:84` — "4. Sessions and Checkpoints" (T037–T051):

| Screen | Node | Screen | Node |
|---|---|---|---|
| T037 sessions-list | `1372:86` | T045 qr-launch | `1372:102` |
| T038 session-detail | `1372:88` | T046 live-checkpoint-monitor | `1372:104` |
| T039 session-edit-and-release-state | `1372:90` | T047 attendance-roster-result | `1372:106` |
| T040 checkpoint-studio-by-session | `1372:92` | T048 checkpoint-closed-results | `1372:108` |
| T041 review-point-card-editor | `1372:94` | T049 checkpoint-history | `1372:110` |
| T042 remove-review-card-reason-modal | `1372:96` | T050 completed-sessions-archive | `1372:112` |
| T043 carry-over-suggestion-modal | `1372:98` | T051 session-waiting-no-data-state | `1372:114` |
| T044 publish-checkpoint-confirmation | `1372:100` | | |

Student group `1372:270` — "6. Checkpoint and Attendance" (S033–S042, MOBILE-FIRST):

| Screen | Node | Screen | Node |
|---|---|---|---|
| S033 qr-scan-landing | `1372:272` | S038 checkpoint-missed-late | `1372:282` |
| S034 checkpoint-intro | `1372:274` | S039 checkpoint-history | `1372:284` |
| S035 checkpoint-confidence-card | `1372:276` | S040 follow-up-checkpoint-suggested | `1372:286` |
| S036 checkpoint-final-comments | `1372:278` | S041 revisit-response | `1372:288` |
| S037 checkpoint-complete | `1372:280` | S042 attendance-confirmed | `1372:290` |

---

## Tasks

Each task: failing test first → minimal impl → refactor → code review (`/code-review` or code-reviewer agent) → conventional commit. Backend tasks 1–14, frontend 15–21.

### Backend

- [x] **T1 — Status-machine transition helper (`app/services/checkpoints.py`).**
  - Test first (`tests/test_checkpoint_transitions.py`): `assert_transition(from, to)` allows exactly the spec edges — `draft→teacher_editing`, `teacher_editing→approved` (+ back to `teacher_editing`), `approved→scheduled`, `scheduled→published`, `published→live`, `live→closed`, `closed→archived`, `approved→published` (direct publish w/ immediate release); every other pair raises a typed `IllegalTransition` carrying `code="REVIEW_REQUIRED"`. Include an `is_editable(status)` reused by the router.
  - Pure function, no DB. This is the single source of truth every publish-path endpoint routes through (Decision 1).
  - Commit `feat(checkpoints): status-machine transition guard (service layer)`.

- [x] **T2 — `checkpoint_responses` model + RLS migration.**
  - Test first: `tests/test_checkpoint_response_model.py` — columns `checkpoint_id`, `card_id`, `user_id`, `confidence int` (CHECK `confidence IS NULL OR confidence BETWEEN -2 AND 2`), `text_response text nullable`, `status` (CHECK `on_time|late`), `submitted_at`, unique `(card_id, user_id)`. UUID PK + `TimestampMixin`.
  - Model in `app/models/checkpoint.py` (`CheckpointResponse`). Migration COPIES `d94257fc717c` structure: create table + `ix_checkpoint_responses_checkpoint_id` + `ENABLE ROW LEVEL SECURITY` + `checkpoint_responses_owner_isolation` policy on `user_id` (Decision 2). Chain from P2 head `d94257fc717c`.
  - Commit `feat(checkpoints): checkpoint_responses model + owner-isolation RLS`.

- [x] **T3 — `attendance_records` model + RLS migration.**
  - Test first: `tests/test_attendance_model.py` — columns `meeting_id`, `user_id`, `status` (CHECK `present|late|excused|absent`), `source` (CHECK `qr|manual_override`), `override_reason text nullable`, `override_by FK users nullable`, `checked_in_at`, unique `(meeting_id, user_id)`.
  - Model + migration (COPY RLS pattern; owner-isolation on `user_id`; participation-only, never mastery). Chain from T2.
  - Commit `feat(attendance): attendance_records model + owner-isolation RLS`.

- [x] **T4 — `checkpoint_launches` model + migration (no RLS).**
  - Test first: `tests/test_checkpoint_launch_model.py` — columns `checkpoint_id`, `meeting_id`, `token text` (the signed JWT), `jti`, `window_start`, `window_end`, `launched_by FK`, `status` (CHECK `active|closed`); **partial unique index `(checkpoint_id) WHERE status='active'`** (single active launch, Decision 3). No RLS — operational/teacher-owned.
  - Model + migration. Add `settings.checkpoint_token_secret: str | None` to `app/config.py` with the same ≥32-byte validation as `canvas_state_secret` (only enforced when a launch is attempted, not unconditionally at startup — keep dev/test bootable).
  - Commit `feat(attendance): checkpoint_launches model + token secret config`.

- [x] **T5 — Publish-path service + endpoints (REPLACES the no-publish guard).**
  - Test first: in `tests/test_checkpoints_api.py` **delete `test_p1_has_no_publish_route`** and add: `POST /checkpoints/{id}/approve` (draft/teacher_editing→approved; requires ≥1 non-removed review_point card + the fixed final card), `POST /checkpoints/{id}/schedule` (approved→scheduled; requires `release_at`+`close_rule`), `POST /checkpoints/{id}/publish` (approved/scheduled→published; **gate**: status `approved`+ session relation + release timing + close rule else `REVIEW_REQUIRED`), `POST /checkpoints/{id}/close` (published/live→closed). Illegal transitions → 409 `REVIEW_REQUIRED`. Non-owner → 404. Append a `review_actions` row on approve/publish/close.
  - Impl in `app/api/checkpoints.py` (reuse `_owned_checkpoint`) routing through `assert_transition` (T1). Extend `app/schemas/checkpoint.py`.
  - Commit `feat(checkpoints): approve/schedule/publish/close endpoints + publish gate`.

- [x] **T6 — Teacher results + history endpoints.**
  - Test first: `GET /checkpoints/{id}/results` (per-card response counts + confidence distribution + derived "missed" = closed & no response for enrolled active students), `GET /courses/{id}/checkpoints?history=1` (closed/archived list). Owner-guarded.
  - Impl in `app/api/checkpoints.py` (`course_router` for the history filter). No RLS reliance — course-scoped owner reads.
  - Commit `feat(checkpoints): teacher results + history endpoints`.

- [x] **T7 — Student intro + response submission (evidence seam).**
  - Test first: `GET /checkpoints/{id}/intro` (student, enrollment-scoped; only when `published`/`live` and within window; else `QR_NOT_AVAILABLE`/404) returns ordered live cards; `POST /checkpoints/{id}/responses` upserts one row per `(card_id, user_id)` with `confidence` (review_point) or `text_response` (final), sets `status=on_time|late` from `close_at`. Asserts: a `LearningEvent` (`stage="during_class"`, `source_kind="checkpoint_card"`) is written AND an `update_concept_mastery` Task is enqueued for concept-tagged review_point cards (outcome `(c+2)/4`), best-effort (attempt persists even if enqueue fails). Duplicate submit updates in place. Wrong-owner cannot write (RLS + endpoint guard).
  - Impl: new `app/services/checkpoint_responses.py` (submission + evidence wiring, mirrors `quizzes.py`), student endpoints in `checkpoints.py`. Broadcast to `monitor_manager` (Decision 4) after commit — stubbed until T12, wired then.
  - Commit `feat(checkpoints): student intro + response submission w/ evidence seam`.

- [x] **T8 — Student history + follow-up + revisit endpoints.**
  - Test first: `GET /users/me/courses/{id}/checkpoints` (student's own checkpoint history + derived missed/late/complete per S039), `GET /checkpoints/{id}/follow-up-suggested` (S040 — suggested follow-up derived from low-confidence responses), `POST /checkpoints/{id}/revisit-response` (S041 — a revisit re-submits against a `follow_up`-kind checkpoint carried via `carried_from_id`). Owner/enrollment-scoped.
  - Commit `feat(checkpoints): student history + follow-up-suggested + revisit`.

- [x] **T9 — QR launch service + endpoint (token signing + gate).**
  - Test first: `tests/test_checkpoint_launch.py` — `launch_checkpoint` signs a PyJWT HS256 token (mirror `canvas_oauth.encode_state`) with `{launch_id, checkpoint_id, meeting_id, jti, exp=window_end}`; **gate** `QR_NOT_AVAILABLE` unless checkpoint `published`/`live` + session-bound + `qr_enabled` + within window; single active launch (partial unique index); a rotate closes the prior launch and issues a fresh token; expired token (`exp` past) fails; tampered signature fails. Endpoint `POST /checkpoints/{id}/launch` owner-guarded.
  - Impl: new `app/services/checkpoint_qr.py` (`encode_launch_token`/`decode_launch_token` using `settings.checkpoint_token_secret`), endpoint in a new `app/api/attendance.py`.
  - Commit `feat(attendance): QR launch token (signed, window-bound, rotating)`.

- [x] **T10 — Attendance scan `/attend/{token}` + rate-limit extension.**
  - Test first: `POST /attend/{token}` validates the token (signature+exp+active launch) → upserts `attendance_records` (`source=qr`, `status=present|late` from window) → returns the checkpoint intro route so the client routes into S034; single-use per student is idempotent (second scan = 200, no dup row, unique `(meeting_id,user_id)`); invalid/expired/closed-launch token → 4xx typed. Plus `tests/test_rate_limit_attend.py`: extend `middleware/rate_limit.py` so `^/api/attend/[^/]+$` is rate-limited on its own per-minute cap; assert a scan flood 429s without touching the RAG quota.
  - Impl: scan endpoint in `app/api/attendance.py`; `_ATTEND_SCAN_REGEX` branch in `_is_rate_limited_path` + its own method/endpoint counting class.
  - Commit `feat(attendance): QR scan endpoint + scan rate-limit`.

- [x] **T11 — Attendance roster result + manual override.**
  - Test first: `GET /meetings/{id}/attendance` (teacher roster: present/late/excused/absent, absent derived from active roster − records), `PATCH /attendance/{id}` (manual override: `status`, required `override_reason`, `override_by=current user`, `source=manual_override`; append `review_actions`). Owner-guarded via the meeting's course.
  - Impl in `app/api/attendance.py`.
  - Commit `feat(attendance): roster result + manual override with reason`.

- [x] **T12 — Live monitor WS (reuse live-quiz hub).**
  - Test first: `tests/test_checkpoint_monitor.py` — WS `/api/checkpoints/{id}/monitor` copies `websocket_live`'s `?token=`→`verify_jwt`→owner check; a connected client receives `{submission_count, confidence_distribution}` on connect and a `submission`/`closed` broadcast when a response lands / the checkpoint closes. Reuse `ConnectionManager` (Decision 4) — assert no new WS framework, just `monitor_manager.connect/broadcast`.
  - Impl: `app/services/checkpoint_monitor.py` (`monitor_manager = ConnectionManager()` + a `broadcast_state` helper), WS endpoint in `checkpoints.py`; wire the T7 submission service + T5 close endpoint to broadcast.
  - Commit `feat(checkpoints): live monitor WS reusing live-quiz hub`.

- [x] **T13 — `close_due_checkpoints` cron.**
  - Test first: `tests/test_close_due_checkpoints.py` — `close_due_checkpoints(session)` transitions `published`/`live` checkpoints whose `close_at`/`close_rule` is due to `closed` (routes through `assert_transition`), closes any active launch, broadcasts `closed`. Idempotent (re-run no-ops). Registered in `_run_cron_ticks` via `_claim_and_run_cron("close_due_checkpoints", timedelta(minutes=1), _body_close_due)`.
  - Impl: service fn in `app/services/checkpoints.py` + `_body_close_due` + registration in `worker.py` (mirror `_body_decay`/`_body_overdue`).
  - Commit `feat(checkpoints): close_due_checkpoints cron`.

- [x] **T14 — RLS isolation tests for the two student-owned tables.**
  - COPY `tests/test_readiness_rls.py` into `tests/test_checkpoint_responses_rls.py` + `tests/test_attendance_rls.py`: under `SET ROLE meli_app`, user A's row is invisible/immutable to user B (SELECT hides, UPDATE/DELETE affect 0 rows, INSERT of A's `user_id` rejected by WITH CHECK), GUC switch-back restores visibility, blank GUC fails closed. Skip-guard when `meli_app` absent. Seed/teardown on `async_engine`.
  - Commit `test(checkpoints): RLS owner-isolation for responses + attendance`.

### Frontend (mobile-first for student S033–S042; pull Figma per screen)

- [x] **T15 — Extract `ConfidenceScaleInput` + extend `use-checkpoints`.**
  - Extract the `scale` branch of `components/join/readiness-question.tsx` into `components/patterns/confidence-scale-input.tsx` (props: `scale`, `value`, `onChange`, `disabled`; −2..+2 from config; mobile-first single-column). Refactor `readiness-question.tsx` to consume it (existing readiness tests stay green). Extend `hooks/use-checkpoints.ts`: publish-path mutations (approve/schedule/publish/close), results + history queries, launch mutation, student intro/response/history/revisit, and a `useCheckpointMonitor` WS client mirroring `use-live-quiz.ts`. Update the P1 `CheckpointStatus` type to include `live`. Vitest for the extracted component + a submission mutation.
  - Commit `feat(patterns): extract ConfidenceScaleInput + extend use-checkpoints`.

- [x] **T16 — Teacher sessions list/detail/edit-release (T037–T039) + workspace tab.**
  - Flip a Sessions/Checkpoints tab `enabled` in `course-workspace-shell.tsx` `TABS` + add the route under `teacher/courses/[courseId]/sessions/`. Sessions list (T037), detail (T038), edit + release-state control (T039, reuses the P1 meetings release-state endpoint). i18n under `teacher.sessions.*`. Pull `1372:86/88/90`.
  - Commit `feat(teacher): sessions list/detail/edit-release + workspace tab`.

- [x] **T17 — Teacher checkpoint studio + card editor + remove/carry-over modals (T040–T043).**
  - Studio by session (T040) listing draft cards with `ReviewStateChip`; review-point card editor (T041); remove-reason modal (T042, `removed_reason` enum); carry-over suggestion modal (T043, `carried_from_id`). Reuse P1 card CRUD mutations. Pull `1372:92/94/96/98`.
  - Commit `feat(teacher): checkpoint studio + card editor + remove/carry-over modals`.

- [x] **T18 — Teacher publish confirmation + QR launch + live monitor (T044–T046).**
  - Publish confirmation dialog surfacing the `REVIEW_REQUIRED` gate as a `StateBanner` (PublishGateDialog pattern) (T044); QR launch panel rendering the signed token as a QR + window countdown (T045); live monitor consuming `useCheckpointMonitor` WS (submission count + confidence distribution + close) (T046). Pull `1372:100/102/104`.
  - Commit `feat(teacher): publish confirm + QR launch + live monitor`.

- [x] **T19 — Teacher attendance/results/history/archive/no-data (T047–T051).**
  - Attendance roster result + manual-override modal with reason (T047); closed results view (T048); checkpoint history (T049); completed-sessions archive (T050); waiting/no-data EmptyState (T051, designed reason+next-action). Pull `1372:106/108/110/112/114`.
  - Commit `feat(teacher): attendance roster + results + history + archive + no-data`.

- [x] **T20 — Student QR landing → intro → confidence → comments → complete (S033–S037, MOBILE-FIRST).**
  - Route `student/attend/[token]/` (QR landing S033, posts to `/attend/{token}`, routes into intro); checkpoint intro (S034); confidence cards using `ConfidenceScaleInput` (S035); final-comments card (S036); complete (S037). Keyboard-completable, `prefers-reduced-motion`, single-column. i18n `student.checkpoint.*`. Pull `1372:272/274/276/278/280`.
  - Commit `feat(student): QR landing → checkpoint confidence flow (mobile-first)`.

- [x] **T21 — Student missed/late + history + follow-up + revisit + attendance confirmed (S038–S042).**
  - Missed/late state (S038); checkpoint history (S039); follow-up-suggested (S040); revisit response (S041, `revisit-response` endpoint); attendance confirmed (S042). Pull `1372:282/284/286/288/290`. Playwright happy-path spec (QR scan → confidence → complete → attendance confirmed) where infra allows; else vitest against mocked hooks (per P0/P1/P2 offline convention). P3 close-out: update roadmap Phase Tracker + Handoff Log.
  - Commit `feat(student): checkpoint missed/history/follow-up/revisit/attendance + P3 close-out`.

---

## Self-review checklist (spec §4.2/§4.3 coverage before P3 close-out)

- [x] Full status machine reachable end-to-end: `draft→…→archived`, illegal transitions refused (T1/T5), `test_p1_has_no_publish_route` deleted + replaced.
- [x] `checkpoint_responses`: unique `(card_id,user_id)`, confidence −2..+2 CHECK, on_time/late derived, "missed" derived (T2/T6/T7).
- [x] Response submission emits exactly ONE `learning_event` (`during_class`) + enqueues `update_concept_mastery` for tagged review_point cards — no parallel evidence path (T7, Decision 5).
- [x] `attendance_records`: present/late/excused/absent, qr vs manual_override, override reason+by, unique `(meeting_id,user_id)`, participation-only never mastery (T3/T11).
- [x] QR security: signed (PyJWT HS256), short-lived + window-bound (`exp`), rotating, single active launch, single-use per student, scan rate-limited (T4/T9/T10, Decision 3).
- [x] Live monitor reuses the live-quiz `ConnectionManager` — no new WS system (T12, Decision 4).
- [x] RLS enforced + proven for both new student-owned tables under `meli_app` (T14, Decision 2).
- [x] Confidence scale is config-driven; `ConfidenceScaleInput` extracted + reused by readiness AND checkpoint cards (T15, Decision 6).
- [x] Student S033–S042 flow is mobile-first, keyboard-completable, empty/waiting states designed (T20/T21).
- [x] `close_due_checkpoints` cron idempotent + registered (T13).
- [x] Gates return typed codes (`REVIEW_REQUIRED`, `QR_NOT_AVAILABLE`) the UI maps to designed states (T5/T7/T9/T18).
- [x] No hardcoded strings (next-intl), no hardcoded colors (tokens), conventional commits, code review per task cluster.
