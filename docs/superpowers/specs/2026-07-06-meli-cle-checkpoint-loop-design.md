# Meli × CLE — Checkpoint-Centered Course Loop: Design Spec

**Date:** 2026-07-06
**Status:** Approved by user (brainstorming session, Fable 5)
**Implements:** the Figma "final" page flow (file `EhzLyFCTZBIGU4iNyHUqvl`, page `1372:2`) — 87 teacher screens (T001–T087) + 73 student screens (S001–S073) — grounded in `docs/meli_docs/` (Core Service Report, CLE Pilot Service Report, Service Architecture Reference, IT Policy Compliance register, Session Handoff).

---

## 1. Summary

Meli turns course materials into active learning habits for students and low-friction teaching support for teachers. This build converts the existing Meli codebase (RAG study-tools app) into the checkpoint-centered course operating loop defined in the service reports: **Course Context → Checkpoint Planning → Student Action → Evidence Review → Follow-up → Course Memory**, with teacher review gates enforced server-side at every publication boundary.

First client: HKUST Centre for Language Education (CLE), courses LANG1511–1515, ~200 students, Fall term. The architecture keeps CLE specifics in a config layer so other institutions later mean a new config pack, not a fork.

## 2. Decisions made (with user)

| Decision | Choice |
|---|---|
| Existing features not in Figma flow (flashcards, pronunciation, revision, live quiz, gamification, RAG chat) | **Fold in, don't delete.** Rebuild IA per Figma; quizzes → Practice/Quiz builders, live quiz → activities/live monitor infra, revision + follow-ups → Follow-up loop. Flashcards/pronunciation/gamification stay reachable inside Activities/course workspace, de-emphasized. |
| Placement/streaming test | **Figma readiness flow only** (S006–S011: eligibility survey → ready check → optional diagnostic → recommendation → readiness summary). Full multi-section placement test is a separate later project; data model must not block it. |
| Auth | **OIDC-ready, wire later.** Keep email/password + Microsoft. Sign-in rebuilt per Figma with staff/student routing pattern. Better Auth `genericOAuth` slots (`hkust-staff`, `hkust-student`) behind env flags. Verify + document real callback paths for ITSO in `docs/oidc-redirect-uris.md`. |
| Grade export | **CSV/Excel download only**, with export audit. No Canvas grade sync in pilot. |
| i18n | **English-first, i18n-structured.** All new screens use next-intl keys (no hardcoded strings); only `en` messages written now; zh-Hant is a fast follow. |
| Build approach | **A: Extend in place.** Reuse existing backend substrate + tests; add checkpoint-loop domain layer; rebuild frontend IA; pilot config module. No greenfield, no premature multi-tenant replatform. |

## 3. Architecture

### 3.1 Stack (unchanged)

Monorepo: `backend/` FastAPI (Railway) + PostgreSQL 17 + pgvector + R2; `frontend/` Next.js 16 App Router (Vercel); Better Auth (JWT plugin, JWKS consumed by FastAPI); DB-backed task queue (`FOR UPDATE SKIP LOCKED`) with cron watermarks. Domains: `cle-meli.hkust.edu.hk` (prod), `cle-meli-dev.hkust.edu.hk` (dev), `cle-meli-api.hkust.edu.hk` (API).

### 3.2 Pilot config boundary (scalability requirement)

- `backend/app/pilot/` package: `base.py` (typed `PilotProfile` schema) + `cle.py` (CLE values). Selected via `PILOT_PROFILE=cle` env; validated at startup.
- Owns: terminology map (e.g. "Checkpoint", "ILO", "Session"), skill taxonomy (reading, speaking, listening, writing, vocabulary, grammar, pronunciation, task-comprehension), readiness survey + ready-check definitions, default score categories, confidence scale (−2..+2, labels), report cadence (weekly + end-term), email-domain→role rules, locales, claim-limit copy for readiness/recommendation/reports.
- Exposed read-only at `GET /api/config`; frontend fetches once at app-shell level and provides via context. **No CLE-specific string or policy hardcoded in components or services.**
- Explicitly NOT in scope: multi-tenant infrastructure, entitlement gating, per-tenant DB partitioning. One deployment = one institution = one profile (per the architecture reference's "pilot is a configuration of the core").

### 3.3 Role-scoped frontend IA

Two route trees replace the shared `/dashboard`:

- **`app/(app)/teacher/`** — `dashboard`, `courses`, `calendar`, `insights`, `profile`, `notifications`; `courses/[courseId]/` workspace tabs: `overview`, `sessions` (+checkpoints), `materials`, `activities` (practice/quiz/activity builders + score), `enrollment`, `insights` (reports), `memory`, `setup` (wizard).
- **`app/(app)/student/`** — `dashboard`, `courses`, `calendar`, `profile`, `notifications`; `courses/[courseId]/`: `overview`, `checklist`, `schedule`, `sessions`, `materials`, `activities`, `profile` (learning profile), `reports`; plus `join` funnel (code → preview → survey → ready check → diagnostic → recommendation → summary → pending/success) and `attend/[token]` QR flow (mobile-first).
- `/dashboard` and legacy routes redirect by role. `proxy.ts` gains role-aware guards (role claim already in session/JWT); students hitting `/teacher/*` are redirected and vice versa. Backend remains the authority (all endpoints role-guarded regardless of routing).
- Fold-ins: flashcards, pronunciation, revision mode, live quiz, gamification mount inside the student/teacher Activities and course workspace areas — same components, new placement, nav de-emphasized.

### 3.4 Server-enforced operating gates

Each gate is a service-layer check returning a typed error code the UI maps to its designed waiting/blocked state (never a blank page):

| Gate | Pass condition | Error → UI state |
|---|---|---|
| Course can open | `courses.setup_status='published'` (requires reviewed context, schedule, materials, ILO map, checkpoint plan, join route) | `SETUP_NOT_OPEN` → S012 / T028 |
| Checkpoint can publish | status `approved` + session relation + release timing + close rule | `REVIEW_REQUIRED` → studio banner |
| QR can launch | checkpoint published/live + session-bound token + time window | `QR_NOT_AVAILABLE` |
| Score-bearing can publish | score category, points/weight, grading mode, open/due/close dates all set | `SCORE_POLICY_INCOMPLETE` → T067 blocker |
| Report can send | evidence refs present + review state `reviewed` + claim-limit sections | `REPORT_NOT_REVIEWED` → S069 waiting |
| Memory can carry forward | teacher decision recorded + source relation + outcome state | `MEMORY_UNDECIDED` |

### 3.5 Auth (OIDC-ready)

- Today: Better Auth email/password (verified, bcrypt) + Microsoft social provider; JWT plugin at basePath `/api/auth` (default; catch-all `app/api/auth/[...all]/route.ts`).
- This build: rebuild T001/S001 sign-in per Figma with an "HKUST Staff / HKUST Student" routing affordance; add `genericOAuth` plugin config with two provider slots `hkust-staff` and `hkust-student`, each enabled only when its env vars exist (`HKUST_STAFF_MELI_CLIENT_ID/SECRET`, `HKUST_STUDENT_MELI_CLIENT_ID/SECRET`, discovery URLs). Callback paths: verify the concrete generated path (expected `/api/auth/oauth2/callback/{providerId}`) against the installed Better Auth version and record verified URIs in `docs/oidc-redirect-uris.md` for ITSO.
- Affiliation gating (`eduPersonAffiliation`/`voPersonAffiliation` claims, deny other-tenant accounts) implemented in the OIDC mapping hook when providers activate; email-domain gate (`ust.hk`/`connect.ust.hk`) remains as today. Identity keyed on existing `users.better_auth_id`; emails lowercased on linking.

## 4. Data model

Conventions: UUID PKs, `TimestampMixin`, soft delete where user-facing, Alembic migrations, Postgres enums for status columns, transitions validated in the service layer, review-affecting changes appended to `review_actions` (existing append-only table).

### 4.1 Sessions (extend `course_meetings`)

Add columns: `session_no int`, `venue text`, `release_state enum(locked, released, completed, archived) default locked`, `topic_summary text`. Sessions ARE meetings — no new table. Calendar feeds already read meetings.

### 4.2 Checkpoints

- **`checkpoints`**: `course_id FK`, `meeting_id FK nullable`, `kind enum(session, follow_up)`, `status enum(draft, teacher_editing, approved, scheduled, published, live, closed, archived)`, `title`, `release_at`, `close_at`, `close_rule enum(manual, at_close_at, end_of_session)`, `qr_enabled bool`, `carried_from_id self-FK nullable`, `generation_meta JSONB` (job id, source doc ids).
- **`checkpoint_cards`**: `checkpoint_id FK`, `position int`, `kind enum(review_point, final_comments)` — exactly one fixed `final_comments` card per checkpoint (not removable); `prompt text`, source anchors: `document_id FK nullable`, `chunk_id FK nullable`, `objective_id FK nullable`; `removed bool`, `removed_reason enum(not_needed, duplicate, not_covered, other) nullable`, `removed_note text`. Concept links via existing `concept_tags` with new `target_kind='checkpoint_card'`.
- **`checkpoint_responses`**: `checkpoint_id`, `card_id`, `user_id`, `confidence int CHECK (-2..2) nullable` (review-point cards), `text_response text nullable` (final card questions/comments), `status enum(on_time, late)`, `submitted_at`. Unique `(card_id, user_id)`. "Missed" is derived (closed checkpoint, no response). Default per CLE pilot: 3 review-point cards + 1 final comments card; card count is teacher-editable, the final card is fixed.
- Response submission emits `learning_event` (stage `during_class`) and enqueues `update_concept_mastery` for tagged cards — reusing the existing evidence seam unchanged.

### 4.3 Attendance & QR

- **`attendance_records`**: `meeting_id`, `user_id`, `status enum(present, late, excused, absent)`, `source enum(qr, manual_override)`, `override_reason text nullable`, `override_by FK nullable`, `checked_in_at`. Unique `(meeting_id, user_id)`. Participation evidence only — never mastery (doc rule).
- **`checkpoint_launches`**: `checkpoint_id`, `meeting_id`, `token` (signed, short-lived, rotating), `window_start`, `window_end`, `launched_by`, `status enum(active, closed)`. QR scan validates token → creates/updates attendance + routes into checkpoint intro. Single active launch per checkpoint; scans rate-limited; token single-use per student (uniqueness on attendance).

### 4.4 Activities

- **`activities`**: `course_id`, `meeting_id nullable`, `format enum(swipe, vote, comment_reaction)`, `title`, `config JSONB` (prompts, options, reaction set), `status enum(draft, published, live, closed, archived)`, `open_at/due_at/close_at`, score fields (§4.5), `anonymous bool`.
- **`activity_responses`**: `activity_id`, `user_id`, `payload JSONB`, `submitted_at`. Unique `(activity_id, user_id)` (comment_reaction may allow multiple reactions inside payload). Live monitor reuses the live-quiz WebSocket hub pattern. Emits `learning_event`.

### 4.5 Score policy

- **`score_categories`**: `course_id`, `name`, `weight numeric nullable`, `points_pool numeric nullable`, `sort int`. Seeded from pilot config defaults at course creation; teacher-editable (T024/T035).
- Publish-settings columns on **`quizzes`** and **`activities`**: `score_category_id FK nullable`, `points numeric nullable`, `grading_mode enum(auto, manual, participation) nullable`, `open_at/due_at/close_at`, `late_rule enum(accept_late, reject_late, accept_with_flag)`. `quizzes.purpose` (exists) distinguishes `practice` (score fields optional/absent) from `quiz` (score gate requires all fields at publish).
- **`grade_exports`**: `course_id`, `exported_by`, `format`, `filters JSONB`, `row_count`, `created_at` — audit of every export (append-only).

### 4.6 Checklist spine (student work items)

- **`work_items`**: `course_id`, `source_kind enum(checkpoint, practice, quiz, activity, material, follow_up, report)`, `source_id UUID`, `title`, `required bool`, `score_bearing bool`, `due_at/close_at nullable`, `visible_from`, `created_by`. Created automatically when a teacher publishes anything; teacher Checklist Manager can add/remove/reorder.
- **`work_item_progress`**: `work_item_id`, `user_id`, `status enum(pending, in_progress, submitted, late, missed, completed, follow_up_assigned)`, `updated_at`. Written transactionally by the same services that record responses/attempts. Student checklist, student calendar overlays, and dashboard "next action" all read this single spine. A nightly cron marks `missed` for overdue-unstarted items.

### 4.7 Entry & readiness

- **`readiness_responses`**: `user_id`, `course_id`, `phase enum(eligibility_survey, ready_check, diagnostic, recommendation)`, `answers JSONB`, `result JSONB` (includes claim-limit wording from config), `status enum(in_progress, completed)`, timestamps. Survey/check question definitions live in the pilot config, not the DB. Designed so a future full placement test writes a new `phase` value + richer `result` without schema change.
- **Join approval**: `courses.join_mode enum(code, code_plus_approval)`, `courses.enroll_code_active bool`; `enrollments.status` already supports `pending` → approve/deny endpoints move to `active`/`rejected`.

### 4.8 Setup gate

Columns on `courses`: `setup_status enum(draft, in_review, published) default draft`, `setup_checklist JSONB` (step flags: basics, syllabus, materials, schedule, analyzer_review, ilo_map, checkpoints, score_policy, class_code). Students cannot enroll or view the workspace until `published`. Reopening setup (edits after publish) does not lock students out; it flags affected artifacts `needs_source_check` where sources changed.

### 4.9 Reports

- **`reports`**: `course_id`, `audience enum(student, teacher)`, `user_id nullable` (per-student weekly/end-term; null = teacher course-level), `period enum(weekly, end_term)`, `period_start/end`, `body JSONB` (typed sections: summary, completed work, weak points, next actions, claim limits), `evidence_refs UUID[]` (learning_note/evidence ids → evidence appendix T084), `status enum(draft, reviewed, sent, archived)`, `reviewed_by/at`, `sent_at`, `export_history JSONB`.
- Drafted by task-queue job from **reviewed** learning notes only (`learning_notes.report_eligibility` exists for exactly this). Teacher reviews/edits → approves → sends (student sees delivery state S069) or exports. No report leaves `draft` without evidence refs.

### 4.10 Course memory

No new table — **`course_record_items`** (exists: carry_forward, report_history) gains its missing API/service/UI. Kinds cover repeated weak concept, checkpoint history note, follow-up outcome, activity effectiveness, score-policy outcome, teacher note. Decisions: keep / revise / reject / carry_forward, recorded with `review_actions` audit. **Next-term import**: new course setup step lists prior-term kept items for the same course code and feeds accepted ones into checkpoint-generation context (T023).

## 5. API surface

All under `/api`, `APIResponse[T]` envelope, existing role/ownership deps, enrollment-scoped access, RLS on new student-owned tables (`checkpoint_responses`, `activity_responses`, `work_item_progress`, `readiness_responses`, `attendance_records`, student `reports`).

| Router | Endpoints (abridged) |
|---|---|
| `setup.py` | `GET/PATCH /courses/{id}/setup` (wizard state per step), `POST /courses/{id}/setup/analyze` (enqueue), `GET .../setup/analysis` (course map + missing-source), `POST .../setup/publish` (course-open gate), `POST .../setup/reopen` |
| `checkpoints.py` | Teacher: `POST /courses/{id}/checkpoints/generate` (enqueue), CRUD, `PATCH cards/{id}` (edit/remove+reason), `POST {id}/carry-over`, `POST {id}/approve`, `POST {id}/schedule`, `POST {id}/publish`, `POST {id}/close`, `GET {id}/results`, `GET /courses/{id}/checkpoints?history=1`; Student: `GET {id}/intro`, `POST {id}/responses`, `GET /users/me/courses/{id}/checkpoints` |
| `attendance.py` | `POST /checkpoints/{id}/launch` (QR token), `POST /attend/{token}` (scan), `GET /meetings/{id}/attendance`, `PATCH /attendance/{id}` (override + reason) |
| live monitor | `WS /api/checkpoints/{id}/monitor` and `WS /api/activities/{id}/monitor` — reuse live-quiz hub (submission count, confidence distribution, close events) |
| `activities.py` | Builder CRUD, `POST {id}/publish` (score gate), `POST {id}/responses`, `GET {id}/results` (evidence view), live state |
| `scores.py` | `GET/POST/PATCH /courses/{id}/score-categories`, `GET /courses/{id}/scores` (teacher) / `GET /users/me/courses/{id}/scores` (student S059), `GET /courses/{id}/grade-export.csv` (+audit row) |
| `checklist.py` | `GET /users/me/courses/{id}/checklist`, `GET /users/me/checklist` (dashboard/calendar feed), teacher: `POST/DELETE /courses/{id}/work-items`, reorder |
| `readiness.py` | `POST /courses/{id}/readiness/{phase}`, `GET /courses/{id}/readiness/summary`, `GET /courses/{id}/preview` (public-ish short/deep preview, gated on code validity) |
| courses.py (extend) | `POST /courses/enroll-by-code` (respect join_mode + setup gate), `GET/POST /courses/{id}/join-requests` (approve/deny), `POST /courses/{id}/enroll-code/rotate|deactivate`, roster |
| `reports.py` | `GET /courses/{id}/reports` (archive), `GET/PATCH /reports/{id}` (review/edit), `POST /reports/{id}/approve|send|export`, `GET /users/me/courses/{id}/reports` |
| `memory.py` | `GET /courses/{id}/memory`, `GET /memory/{id}`, `POST /memory/{id}/decide` (keep/revise/reject/carry_forward), `GET /courses/{id}/memory/next-term-suggestions`, `POST /courses/{id}/setup/import-memory` |
| `insights.py` | `GET /courses/{id}/insights` (re-shape existing evidence/mastery/alerts), `GET /signals/{id}` (drawer), `GET /evidence/{id}/source` (source view), `GET /courses/{id}/effectiveness` (from outcome_checks) |

**New task types** (existing worker + idempotency patterns): `analyze_course_setup`, `generate_checkpoints` (grounded via existing retriever + syllabus grounding; cards concept-tagged via existing tagger), `draft_report` (cadence-checked from cron), `close_due_checkpoints` + `mark_missed_work_items` (cron transitions).

**Evidence wiring rule:** every student submission path emits a `learning_event` and (where concept-tagged) an `update_concept_mastery` task. Review queue, follow-ups, effectiveness tracker, learning profile, and reports all flow from that one seam. No parallel evidence system.

## 6. Figma screen → route/feature map

Implementation sessions pull per-screen design context from Figma MCP (file `EhzLyFCTZBIGU4iNyHUqvl`; node ids in page metadata, e.g. T040 = `1372:92`). Mapping by group:

| Figma group | Screens | Destination |
|---|---|---|
| Teacher 1 Global Entry/Home | T001–T013 | `/sign-in`, `/teacher/dashboard`, `/teacher/courses`, `/teacher/calendar` (month/week), `/teacher/insights` (+course selector), `/teacher/profile`, `/teacher/notifications` |
| Teacher 2 Course Setup | T014–T028 | `/teacher/courses/new` + `/teacher/courses/[id]/setup/*` (basics, syllabus, materials, schedule, analyzer, ILO map, session gen, checkpoint gen, memory import, score policy, class code, checklist, publish success, missing-source error) |
| Teacher 3 Overview/Enrollment | T029–T036 | `/teacher/courses/[id]/overview`, `schedule`, `enrollment` (roster, join approval, code modal), `score categories`, `memory` summary |
| Teacher 4 Sessions & Checkpoints | T037–T051 | `/teacher/courses/[id]/sessions` (+detail, edit/release), `/checkpoints` studio (+card editor, remove modal, carry-over modal, publish confirm, QR launch, live monitor, attendance result, closed results, history, archive, no-data) |
| Teacher 5 Materials | T052–T058 | `/teacher/courses/[id]/materials` (library, upload, link modal, session folders, preview, assign-to-session, remove confirm) |
| Teacher 6 Activities/Practice/Quiz/Score | T059–T075 | `/teacher/courses/[id]/activities` (home, practice builder ×4, quiz builder ×4, activity builders swipe/vote/comment, live monitor, results/evidence, grade export) |
| Teacher 7 Insights/Reports/Memory | T076–T087 | `/teacher/courses/[id]/insights` (+signal drawer, evidence source, effectiveness, next-term suggestions, report archive, weekly/end-term detail, appendix, export settings, no-evidence, memory detail) |
| Student 1 Entry/Readiness | S001–S013 | `/sign-in`, `/student/join` funnel (code, invalid, short preview, survey, ready check, diagnostic, recommendation, deep preview, summary, not-open, success) |
| Student 2 Home/Calendar | S014–S022 | `/student/dashboard`, `/student/courses`, `/student/calendar` (month/week, event detail), `/student/profile`, `/student/notifications` |
| Student 3 Course Workspace | S023–S032, S072 | `/student/courses/[id]/*` (overview, checklist, schedule, sessions+detail+locked, materials+reader, activities, no-materials, no-activities) |
| Student 4 Checkpoint/Attendance | S033–S042 | `/attend/[token]` (QR landing), checkpoint intro → confidence cards → final comments → complete → missed/late → history → follow-up suggested → revisit response → attendance confirmed (mobile-first) |
| Student 5 Practice/Quiz/Activities | S043–S059, S073 | practice start/question types (MC, matching, ordering, short answer)/feedback/complete; quiz landing (score-bearing disclosure)/taking/result; activity waiting/swipe/vote/comment/submitted/record; score & participation record |
| Student 6 Follow-up/Profile/Reports | S060–S071 | follow-up checklist item + action detail; learning profile, signal detail, ILO strength map, skill pattern map; report archive/weekly/end-term/delivery; waiting-instructor-feedback; no-evidence |

Screens are abstract wireframes: follow flow + content structure, apply our own enterprise-grade visual design (frontend-design + ui-ux-pro-max skills at implementation time, existing token system).

## 7. UX / design system

- **Tokens:** existing "Honey & Salt" oklch system (`styles/tokens.css`) is the base; extend, never bypass. No hardcoded colors.
- **Pattern layer:** new `components/patterns/` on top of `components/ui/`: PageHeader, StateBanner, ReviewStateChip, SourceAnchorChip, ConfidenceScaleInput (−2..+2), EmptyState/WaitingState, PublishGateDialog, DataTable, DetailDrawer, StepWizard, StatusTimeline, QRPanel. One visual treatment per state-machine status, used everywhere — review/waiting states are the product's trust language.
- **Empty & waiting states are designed features** (doc §7.4): setup-under-review, no-materials, session-locked, waiting-for-feedback, needs-source-check, no-evidence, activity-waiting, missed/late — each a real component with reason + next action, never a blank div.
- **Responsive:** student checkpoint/QR/activity flows mobile-first; teacher cockpit desktop-first responsive; both from the same route tree.
- **Accessibility:** WCAG AA contrast on tokens, focus-visible everywhere, keyboard-completable checkpoint flow, `prefers-reduced-motion` respected.
- **i18n:** next-intl keys for every string; `en` only in this build.

## 8. Security & compliance (maps to `HKUST_IT_Policy_Compliance` register)

- **RBAC:** every new endpoint behind existing role/ownership deps; enrollment-scoped queries; RLS policies on new student-owned tables (existing migration pattern `28236be3d7b3`).
- **Audit (MSS logging):** publish/review/export/override/carry-forward/send actions append to `review_actions` or new append-only `audit_events` (no update/delete path). Grade exports and report deliveries always audited.
- **QR anti-abuse:** signed short-lived rotating tokens, session+window bound, single-use per student, scan endpoint rate-limited.
- **CI security gates (MSS items 2 & 8 — currently OPEN):** CodeQL or Semgrep SAST on PRs + `pip-audit`/`npm audit` dependency alerts, added in P7. Closes two register blockers.
- **Release hygiene (App-Dev Guidelines):** seed/demo data excluded from production; no test accounts; secrets env-only (OIDC secrets never committed; rotate before 2028-06-28).
- **Carried forward:** nonce CSP + security headers (proxy.ts), Pydantic validation at all boundaries, per-user rate limiting on AI endpoints (extend to QR scan + readiness submit), TLS everywhere, Fernet-encrypted third-party tokens.
- **Data minimization (doc §5.6/§7.3):** no time-on-page/surveillance metrics; evidence = explicit submissions only; audio remains transient (no change); course memory is course-bound, never cross-course student profiling.
- **PIA inputs:** new personal-data categories (attendance records, checkpoint responses, readiness responses, reports) documented in the data inventory when the PIA is written (register §5.3).

## 9. Testing

- **Backend (pytest, target 80%+ on new code):** state-machine transition tests (legal + illegal transitions per object), gate-refusal tests (each §3.4 gate), RLS isolation tests, QR token expiry/reuse tests, work-item progress transactional tests, report-drafting eligibility tests, evidence-seam tests (checkpoint/activity response → learning_event → mastery task). Follow existing suite patterns (85 files).
- **Frontend (Playwright):** per-phase critical-flow specs — setup wizard→publish→join; QR scan→checkpoint→results; score-bearing quiz disclosure→attempt→export; follow-up assignment→revisit→effectiveness; report review→send→student delivery.
- **Manual UAT anchors:** Meli feedback 2nd UAT ~7 Sep 2026, in-class ~21 Sep 2026.

## 10. Phasing (multi-session, checkbox-driven)

Eight phases; each independently shippable and committed; each sized for one focused session. The implementation plan (written next via writing-plans) carries per-task checkboxes and a session-handoff header (done/next/key files) so a fresh session resumes cleanly. Implementation executes with Opus agents; each phase's session pulls its own Figma group via MCP before building UI.

- **P0 — Shell & foundations:** pilot config module + `/api/config`; role-scoped route trees + redirects + proxy role guards; nav/layouts per Figma; pattern component library; sign-in rebuild (OIDC-ready slots + ITSO callback doc). *(T001–T013 shell, S001–S002, S014–S022 shell)*
- **P1 — Course setup wizard & gates:** setup state + checklist + publish/reopen; `analyze_course_setup` job; analyzer review UI; ILO map builder; session generation review; `generate_checkpoints` job + review; score policy setup; class code controls; missing-source error; publish success. *(T014–T028)*
- **P2 — Student entry & enrollment:** join funnel (code/invalid/previews/survey/ready check/diagnostic/recommendation/summary/not-open/pending/success); join approval + roster + code modal; teacher course overview + schedule table. *(S003–S013, T029–T035)*
- **P3 — Checkpoint loop core:** checkpoint/card/response models + API; studio + card editor + remove/carry-over modals; approve/schedule/publish/close; QR launch + attendance + override; live monitor WS; student checkpoint flow (intro→confidence→comments→complete→missed/late→history); results + history + archive + no-data. *(T037–T051, S033–S042)*
- **P4 — Student workspace & materials:** work-item spine + checklist + calendar merge + dashboard next-action; sessions list/detail/locked; materials library/reader/link-resources/session folders/assign/remove; empty states. *(S023–S032, S072, T052–T059)*
- **P5 — Practice/quiz/activities/score:** practice + quiz builders per Figma on existing quiz engine (publish settings + score gate); activity formats (swipe/vote/comment) + live monitor + results/evidence; student practice question types/feedback/complete, quiz landing disclosure/taking/result, activity flows; score & participation record; CSV grade export + audit. *(T060–T075, S043–S059, S073)*
- **P6 — Follow-up & insights:** follow-ups into checklist + action detail + revisit response; learning profile + signal detail + ILO strength map + skill pattern map; course insights + signal drawer + evidence source view + effectiveness tracker; waiting/no-evidence states. *(S060–S065, S070–S071, T076–T079)*
- **P7 — Reports, course memory & hardening:** `draft_report` job + archive/review/edit/approve/send/export + evidence appendix + delivery states; course memory API/UI + decisions + next-term suggestions + memory import into setup (completes T023/T036); CI security gates (SAST + dependency alerts); i18n key audit; seed-data production exclusion; full E2E pass; design-review polish. *(T080–T087, S066–S069)*

## 11. Out of scope (explicit)

- Full multi-section placement/streaming test (separate project; readiness data model is forward-compatible).
- Canvas grade sync (CSV only; Canvas file/roster import remains as-is).
- zh-Hant translations (keys ready; translation is a fast follow with CLE review).
- Multi-tenant/entitlement infrastructure (pilot config module only).
- XiYouQuest (separate product/repo).
- Mobile native apps; CITARS/PIA/CSP-checklist paperwork (tracked in the compliance register, not code).

## 12. Risks & mitigations

| Risk | Mitigation |
|---|---|
| IA restructure breaks existing users mid-build | P0 ships redirects; legacy routes keep working until each phase replaces them; feature fold-ins land with their phase, not before. |
| 160 screens × context limits | Per-phase sessions read only their Figma group + this spec + the plan's handoff header; plan carries checkboxes. |
| Checkpoint generation quality | Grounded via existing retriever + syllabus grounding + concept tagger; cards default to `draft`; `needs_source_check` path designed in (missing-source states T028/§4.8). |
| Work-item spine consistency | Progress written in the same transaction as the source response; nightly cron reconciles missed states; tests cover the seam. |
| OIDC callback mismatch with ITSO | Verified paths documented in P0 (`docs/oidc-redirect-uris.md`) before any ITSO follow-up. |
