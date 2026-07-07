# P6 — Follow-up & Insights: Detailed Implementation Plan

> **Phase:** P6 of the Meli × CLE roadmap (`docs/superpowers/plans/2026-07-07-meli-cle-roadmap.md`).
> **Spec:** `docs/superpowers/specs/2026-07-06-meli-cle-checkpoint-loop-design.md` §4.6 (work-item spine, the `follow_up` source_kind), §4.9/§4.10 (evidence → memory), §5 (`insights.py` router row + evidence-wiring rule), §7.4 (designed empty/waiting states).
> **Branch:** `feat/cle-p0-shell`. **Depends on:** the EXISTING evidence engine (`learning_notes` / `follow_up_actions` / `outcome_checks` / `instructor_alerts` / `concept_mastery` — shipped in the "meli evidence engine" merge), P3's checkpoint response + follow-up/revisit surface, P4's `work_items` / `work_item_progress` spine (the `follow_up` source_kind is already in the CHECK enum, reserved here), P5's activity/quiz evidence flowing into the same seam.
> **Method:** `superpowers:writing-plans` shape — TDD, one committable task at a time, failing test first. Check boxes IN THIS FILE as tasks land.
> **Governing constraint (Global rule):** P6 RESHAPES existing evidence — it does NOT compute a second evidence path. Every insight reads `concept_mastery` / `learning_notes` / `outcome_checks` / `instructor_alerts` / `concept_tags`. No new mastery math, no new note drafting, no new alert evaluator. `app/api/insights.py` is **pure-read**; the only WRITES P6 adds are the `follow_up_action → follow_up` work_item seam (wiring an already-created row onto the existing spine).

---

## Session bootstrap (every new session for this phase starts here)

1. Read the roadmap Global Rules + the P6 phase brief + this file top-to-bottom.
2. Read spec §4.6 (spine), §4.9–4.10 (evidence→memory), §5 (`insights.py` endpoints + "Evidence wiring rule: … No parallel evidence system"), §7.4 (designed empty/waiting states), and the Handoff Log entries for the evidence-engine merge + P3/P4/P5.
3. **P6 adds NO new tables and (almost certainly) NO migration** — it reshapes existing tables and wires the existing `work_items`/`work_item_progress` spine. Before writing ANY migration, stop and prove it is genuinely new state; the default is zero migrations. (If one is ever needed, chain from the ACTUAL current head via `python -m alembic heads` — do not trust a literal in this file.)
4. Re-read the REAL code each task names before editing — never trust this plan over the code:
   - `backend/app/models/evidence.py` — `LearningEvent`, `LearningNote` (`review_status`, `evidence_category`, `observed_signal`, `draft_interpretation`, `limitation_note`, `suggested_follow_up`, `report_eligibility`, `user_id` NULL = cohort), `ReviewAction`, `FollowUpAction` (`assignment_status` CHECK `suggested|assigned|viewed|completed|checked|closed|carried_forward`, polymorphic `target_kind`/`target_id`, `learning_note_id`), `OutcomeCheck` (`status` CHECK `pending|completed|improved|persistent|resolved|needs_review|carried_forward`, partial-unique on `follow_up_action_id`), `CourseRecordItem`.
   - `backend/app/models/decision.py` — **`InstructorAlert` lives HERE, not in `evidence.py`** (the brief's grouping is loose): `alert_type` CHECK broadened to include `readiness_gap|course_fit_concern|skill_gap`, `severity`, `status open|dismissed|resolved`, `reason JSONB`, `linked_note_id`, `linked_follow_up_id`, partial-unique idempotency index.
   - `backend/app/models/concept.py` — `Concept`, `ConceptTag` (`target_kind` CHECK includes `objective` = the ILO link, and `checkpoint_card`; **no `skill` target_kind exists**), `ConceptMastery` (`mastery_score` GENERATED, `confidence`, `alpha`/`beta`, `attempt_count`, `last_attempt_at`), `ConceptMasteryHistory`, `ConceptPrerequisite`.
   - `backend/app/models/curriculum.py::LearningObjective` (`learning_objectives`: `statement`, `module_id`/`meeting_id`, `bloom_level`) — the ILO rows the strength map aggregates over.
   - `backend/app/api/review.py` — the follow-up SEAM: `review_learning_note` creates the `FollowUpAction` (`assignment_status='assigned'`, `db.add(follow_up)` … `await db.commit()`) — B1 hooks the `follow_up` work_item write in BEFORE that commit; `list_my_follow_ups` (`GET /users/me/courses/{id}/follow-ups`, only `assigned`/`viewed`) + `mark_follow_up_viewed`.
   - `backend/app/services/mastery.py` — `_close_follow_ups` (the outcome-closure: flips `FollowUpAction`→`completed`, writes one `OutcomeCheck` `improved|persistent`, promotes to `CourseRecordItem` when the note is `reviewed`) — B2 hooks the `work_item_progress`→`completed` sync here; runs in the privileged worker (BYPASSRLS per migration `28236be3d7b3`).
   - `backend/app/api/mastery.py` — `GET /users/me/courses/{id}/mastery` (student per-concept list) + `GET /courses/{id}/mastery` (cohort avg / weak-count) — insights RESHAPES these, does not recompute them.
   - `backend/app/api/instructor_alerts.py` — `GET /courses/{id}/alerts`, `PATCH …/{id}` (the teacher signal surface insights reads).
   - `backend/app/api/analytics.py` — quiz-centric course overview (NOT evidence) — insights is a SEPARATE surface; do not fold quiz stats into it.
   - `backend/app/services/work_items.py` — `upsert_work_item` (idempotent on `(course_id, source_kind, source_id)`), `upsert_progress` (on `(work_item_id, user_id)`), `remove_work_item`; commit owned by the caller (Decision 3 of P4).
   - `backend/app/api/checklist.py` — `_build_checklist` already surfaces ANY non-deleted work_item (so a `follow_up` item appears the instant B1 writes it); the `checkpoint_responses` fallback is checkpoint-only, so a `follow_up` item's status comes from `work_item_progress` or defaults `pending`.
   - `backend/app/api/checkpoints.py::publish_checkpoint` (lines ~600–670) — the transactional publish→work_item seam B1 MIRRORS (upsert BEFORE `await db.commit()`, alongside `_append_review_action`); note the code comment "the spine's `follow_up` source_kind is reserved for P6."
   - `backend/app/pilot/base.py` + `cle.py` — `PilotProfile.skill_taxonomy` (8 skills: reading/speaking/listening/writing/vocabulary/grammar/pronunciation/task_comprehension) + `claim_limits` (already has `learning_profile` + `report` + `recommendation` copy) — the skill-map + profile disclaimer source.
   - `backend/app/api/__init__.py` (register `insights_router` — follow the two-router `checklist`/`attendance` registration pattern), `backend/app/api/_helpers.py::verify_enrollment` (active-only student guard), `backend/app/api/deps.py` (`get_owned_course`, `require_instructor`, `require_student`, `get_current_user` sets the RLS GUC).
   - Frontend: `frontend/src/app/(app)/teacher/insights/page.tsx` (TODAY = a P0 `EmptyState variant="waiting"` "No evidence yet" — P6 fills it), `frontend/src/app/(app)/student/` (has `courses/[courseId]/checkpoints`, `checkpoints/[checkpointId]/follow-up` = the P3 checkpoint-level revisit, NOT the FollowUpAction detail P6 adds), `frontend/src/components/course/course-workspace-shell.tsx` (`insights` tab is `enabled:false` — P6 flips it + adds the route), `frontend/src/components/patterns/` (`EmptyState`, `StateBanner`, `tones.ts` — the no-evidence + waiting-for-feedback states), `frontend/src/hooks/` (`use-work-items.ts` already types `follow_up` + `follow_up_assigned`; `use-analytics.ts`, `use-me.ts`, `use-pilot-config.ts`, `use-authed-query.ts`, `use-checkpoints.ts` for hook shape), `frontend/messages/en.json` (namespaces `student.*`/`teacher.*`/`patterns.*`), `frontend/AGENTS.md` (Next.js 16).
5. Before each UI task pull its Figma node via `get_metadata` on the GROUP frame first (individual screen ids are children — NOT in this plan), then `get_design_context` per screen. Group ids in the table below.
6. Session-end: update the roadmap Phase Tracker + append a Handoff Log entry; commit with `git add -f` (docs/ is gitignored). **The controller owns roadmap/RESUME edits — do not touch them from a task.**

---

## Decisions locked (reconciliation with spec + the real evidence engine)

1. **P6 RESHAPES; it never recomputes (Global "no parallel evidence path" rule).** `app/api/insights.py` is PURE-READ over `concept_mastery` / `concept_mastery_history` / `learning_notes` / `outcome_checks` / `instructor_alerts` / `concept_tags` / `learning_objectives`. It adds NO mastery math, NO note drafting, NO alert evaluation — those stay in `services/mastery.py` + `services/alerts.py` + `services/adaptive_jobs.py` (P6 does not touch their logic except the one `work_item_progress` sync in B2). If an insight cannot be sourced from existing rows, it renders a designed no-evidence state (Decision 6) — it does not invent the number.

2. **The follow-up→checklist seam REUSES the existing spine — NO new table.** `work_items.source_kind` already ships the full §4.6 CHECK enum including `follow_up` (P4 Decision 1), and `work_item_progress.status` already includes `follow_up_assigned`. So a reviewed `FollowUpAction` becomes a `follow_up` work_item via the existing `upsert_work_item` (`source_id = follow_up_action.id`) + a per-student `upsert_progress(status='follow_up_assigned')`. `work_item_progress` DOES track its completion. **Zero migrations** for the seam.

3. **The seam write is TRANSACTIONAL + idempotent, mirroring P4 B4's publish→work_item.** Inside `api/review.py::review_learning_note`, when a `FollowUpAction` is created, `await db.flush()` to materialize `follow_up.id`, then call `upsert_work_item(source_kind='follow_up', source_id=follow_up.id, title=<from note/spec>, required=True, score_bearing=False, due_at=follow_up.due_at, close_at=follow_up.due_at, created_by=actor.id)` and `upsert_progress(work_item_id=…, user_id=follow_up.user_id, status='follow_up_assigned')` — ALL before the single existing `await db.commit()`, so the follow-up, its ReviewAction, its work_item and its progress row commit atomically. Idempotent via the `(course_id, source_kind, source_id)` unique index (a re-review that re-adds a follow-up for the same note is guarded upstream; the upsert never double-inserts). A cohort note with no target still cannot create a follow-up (existing 400) — so no orphan work_item.

4. **Follow-up COMPLETION is synced onto the spine at the existing outcome-closure — not a second cron.** `services/mastery.py::_close_follow_ups` already flips `FollowUpAction.assignment_status` to `completed` and writes the `OutcomeCheck` when a later attempt satisfies the follow-up. B2 hooks a best-effort `upsert_progress(status='completed')` for each closed follow-up's `follow_up` work_item into that SAME transaction (the handler commits). It runs in the privileged worker connection (BYPASSRLS), so it may write any student's row. If the follow-up never had a work_item (a pre-P6 follow-up), the sync is a no-op — never a raise. This keeps the checklist and the evidence loop consistent without a new reconciliation job (P4's `mark_missed_work_items` deliberately protects `follow_up_assigned` from being flipped to `missed`, so the spine stays coherent).

5. **Skill-pattern map is HONEST about its missing dimension.** The pilot `skill_taxonomy` (8 skills) exists in config, but **no `skill` link exists anywhere in the schema** — `concept_tags.target_kind` has `objective`/`checkpoint_card`/… but NOT `skill`, and `learning_notes.evidence_category` carries drafting tags (`attempt_signal`/`concept_weakness`/`falling_behind`), not skills. Therefore the skill-pattern map is a config-driven grid of the taxonomy skills where **every cell renders the designed no-evidence state until a concept→skill mapping exists** (a future, out-of-scope enrichment). B6 exposes the skill list with an explicit `has_evidence=false` per skill (never a fabricated score); F4 renders it as the "we don't have skill-level evidence yet" state. This satisfies "only render where evidence exists" without inventing a classifier.

6. **No-evidence + waiting-for-feedback are designed states (spec §7.4), sourced from real gates.**
   - *No-evidence* (S065/S070, T-insights empty): a student/course with zero `concept_mastery` rows (or all `confidence < 0.5`) shows the designed EmptyState — reason + next action, never a blank div. This REPLACES today's placeholder in `teacher/insights/page.tsx`.
   - *Waiting-for-instructor-feedback* (S071): a `learning_note` in `review_status ∈ draft|queued` that the student's evidence produced, OR a `follow_up_action` in `assignment_status='suggested'` (drafted, not yet instructor-assigned), surfaces as a StateBanner "your instructor is reviewing this" — the student never sees an unreviewed AI draft's content (Core §0.2: AI drafts, instructors review). Only `assigned`/`viewed`/`completed` follow-ups get a student-facing detail.

7. **The ILO strength map is the well-grounded map; it aggregates mastery per objective.** ILO strength for a `learning_objective` = the (confidence-weighted) aggregate of `concept_mastery.mastery_score` over the concepts tagged to that objective (`concept_tags` where `target_kind='objective'` AND `target_id=objective.id`, `review_status` confirmed/reviewed where relevant), filtered to the caller (student view) or the cohort (teacher view). Objectives with no tagged concept that has evidence render the no-evidence cell. Pure read — no new column.

8. **`insights.py` scoping mirrors existing guards exactly.** Student reads (`/users/me/courses/{id}/…`) go through `verify_enrollment` (active-only) and only ever read the caller's own `user_id` rows; the RLS GUC set by `get_current_user` is defense-in-depth. Teacher reads (`/courses/{id}/…`) go through `get_owned_course` (404 on non-owner, no existence leak). `GET /signals/{id}` and `GET /evidence/{id}/source` resolve the row, then re-derive the course and apply the SAME owner/enrollment guard on it (404 on mismatch) — an id is never trusted to imply access.

9. **Effectiveness tracker reads `outcome_checks`, nothing new.** The tracker (T079) is a reshape of `outcome_checks.status` counts (`improved` vs `persistent` vs `resolved` vs `needs_review`) grouped by follow-up `action_type` / linked note, over an owned course. It is the read side of the loop `_close_follow_ups` already writes — no new persistence, no new job.

---

## Reality checks (brief-named model/endpoint vs what actually exists)

| Brief names | Actually exists? | Real location / shape | Plan adaptation |
|---|---|---|---|
| `learning_notes` / `LearningNote` | ✅ yes | `app/models/evidence.py`; `review_status` CHECK `draft…archived`, `evidence_category` free string, `observed_signal`, `draft_interpretation`, `limitation_note`, `suggested_follow_up JSONB`, `report_eligibility`, `user_id` NULL = cohort | Signal detail (B7) reads these; waiting-state (Dec 6) gates on `review_status`. |
| `follow_up_actions` / `FollowUpAction` | ✅ yes | `app/models/evidence.py`; `assignment_status` CHECK `suggested\|assigned\|viewed\|completed\|checked\|closed\|carried_forward`, polymorphic `target_kind`/`target_id`, `learning_note_id`, `due_at` | The seam source (B1). `review.py` already CREATES it on review (`assigned`); B1 only adds the spine write. |
| `outcome_checks` / `OutcomeCheck` | ✅ yes | `app/models/evidence.py`; `status` CHECK `pending…carried_forward`, partial-unique on `follow_up_action_id`; written by `mastery.py::_close_follow_ups` | Effectiveness tracker (B8) reshapes these; completion sync (B2) rides the write path. |
| `instructor_alerts` / `InstructorAlert` | ✅ yes — **but in `decision.py`, not `evidence.py`** | `app/models/decision.py`; `alert_type` broadened w/ `readiness_gap\|course_fit_concern\|skill_gap`, `linked_note_id`, `linked_follow_up_id`, `reason JSONB` | Teacher insights (B5) + signal drawer read via existing `api/instructor_alerts.py`; cite `decision.py` not `evidence.py`. |
| `concept_mastery` + `concept_mastery_history` | ✅ yes | `app/models/concept.py`; `mastery_score` GENERATED, `confidence`, `alpha/beta`, `attempt_count`, `last_attempt_at` | Learning profile (B4) + ILO map (B5) reshape these. `api/mastery.py` already exposes student + cohort reads — insights composes, not recomputes. |
| `review_actions` / `ReviewAction` | ✅ yes | `app/models/evidence.py`; append-only, `action_type` CHECK incl. `assign_followup` | Read-only for evidence-source view (B7); B1 does NOT add a new review action type. |
| concept ontology: `concepts`/`concept_prerequisites`/`concept_tags` (ILO/objective links) | ✅ yes | `app/models/concept.py`; `concept_tags.target_kind` includes **`objective`** (ILO link) + `checkpoint_card`; `learning_objectives` in `curriculum.py` | ILO map (B5) joins `concept_tags(target_kind='objective')` → `concept_mastery`. |
| skill taxonomy → evidence link | ⚠️ **partial** — taxonomy exists, link does NOT | `pilot/cle.py::skill_taxonomy` (8 skills); **no `skill` target_kind, no skill column** on any evidence row | Skill map (B6/F4) renders config skills with honest per-skill `has_evidence=false` no-evidence state (Decision 5) — no fabricated scores. |
| `app/api/review.py`, `mastery.py`, `analytics.py`, `instructor_alerts.py` | ✅ all exist | as read above | insights RESHAPES review/mastery/alerts; `analytics.py` is quiz-only and stays separate. |
| `app/services/mastery.py`, `alerts.py`, `adaptive_jobs.py` | ✅ all exist | `mastery.py::_close_follow_ups` = the completion + OutcomeCheck writer; `alerts.py`/`adaptive_jobs.py` draft notes/alerts (`evidence_category` = drafting tag) | B2 hooks `mastery.py`; B-tasks otherwise read the rows these produce. No logic change to alerts/adaptive_jobs. |
| `app/api/insights.py` | ❌ **does NOT exist** | — | B4 creates it (pure-read) + registers `insights_router` in `api/__init__.py`. |
| work-item `follow_up` source | ✅ ready | `work_items.source_kind` CHECK + `work_item_progress.status='follow_up_assigned'` already shipped (P4); `checklist.py::_build_checklist` surfaces any item | Seam (B1) writes onto it — no schema change. |
| Frontend insights routes | ✅ placeholder only | `teacher/insights/page.tsx` = P0 no-evidence EmptyState; `insights` workspace tab `enabled:false`; NO student learning-profile route yet | P6 fills the teacher page + workspace tab, adds `student/courses/[courseId]/profile`. |

**Net:** P6 = **zero new tables, zero migrations** (reshape + wire the existing spine). The follow-up→work_item seam reuses `work_items`/`work_item_progress`; the only genuinely new file is `app/api/insights.py` (pure-read) + its schemas.

---

## Figma node map (file `EhzLyFCTZBIGU4iNyHUqvl`, page `final`)

Individual screen node ids are CHILDREN of these group frames and are intentionally not listed — call `get_metadata` on the group first, then `get_design_context` per screen. Wireframes are abstract: follow flow + content structure, apply our enterprise design system (tokens only).

| Group frame | Node | Screens (from brief) |
|---|---|---|
| Student "6. Follow-up / Profile" | `1372:330` | S060 follow-up checklist item, S061 follow-up action detail + revisit response, S062 learning profile, S063 signal detail, S064 ILO strength map, S065 skill pattern map, **S070** no-evidence state, **S071** waiting-for-instructor-feedback state |
| Teacher "7. Insights" (head of the group) | `1372:168` | T076 course insights, T077 signal detail drawer, T078 evidence source view, T079 effectiveness tracker — **T080–T087 (reports/memory) are P7; do NOT build them here** |

> Note: the roadmap brief lists P6's student screens as "S060–S065 + S070–S071 (group `1372:330`)" and teacher "T076–T079 (group `1372:168`)". S066–S069 (reports) and T080–T087 (reports/memory/appendix) belong to P7 — even though they share the group frames, they are out of scope for P6.

---

## Tasks

Each task: failing test first → minimal impl → refactor → code review (`/code-review` or code-reviewer agent) → conventional commit. Backend B1–B8, frontend F1–F6. Backend FIRST.

### Backend

- [x] **B1 — `follow_up_action` → `follow_up` work_item transactional seam (in `review.py`).**  *(riskiest — combined-review)*
  - Test first (`tests/test_review_api.py` additions, or a new `tests/test_follow_up_work_item_seam.py`): after `POST /learning-notes/{id}/review` with an `assign_followup` action (or an inline `follow_up` spec) on a student-scoped note, a `work_items` row exists with `source_kind='follow_up'`, `source_id = <new FollowUpAction.id>`, `required=true`, `due_at = follow_up.due_at`; the target student has a `work_item_progress` row `status='follow_up_assigned'`; a SECOND review that re-assigns for the same note does NOT duplicate the work_item (unique index); a forced failure BEFORE commit rolls back the follow-up AND its work_item AND its progress (atomicity); a COHORT note (no target) still 400s and writes NO work_item. The `follow_up` item then appears in `GET /courses/{id}/checklist` for that student (integration assertion through `_build_checklist`).
  - Impl: in `api/review.py::review_learning_note`, after `db.add(follow_up)`, `await db.flush()` to get `follow_up.id`, then call `services.work_items.upsert_work_item(...)` + `upsert_progress(..., status="follow_up_assigned")` BEFORE the existing single `await db.commit()` (mirror `checkpoints.py::publish_checkpoint` B4 seam). Title from `body.follow_up` action label or the note's `observed_signal` (short). Import the service; do NOT commit inside the service (Decision 3 of P4). No new schema.
  - Commit `feat(followup): reviewed follow-up writes a follow_up work_item (transactional)`.

- [x] **B2 — outcome-closure syncs `follow_up` work_item_progress → `completed` (in `mastery.py`).**  *(riskiest — combined-review)*
  - Test first (`tests/test_mastery_outcome_closure.py` additions): when `_close_follow_ups` flips a `FollowUpAction` to `completed` (a later attempt satisfies it) and writes its `OutcomeCheck`, the matching `follow_up` work_item's `work_item_progress` for that user flips to `completed` in the SAME transaction; a follow-up with NO work_item (pre-P6) is a no-op (no raise); idempotent on worker retry (a second closure pass leaves the already-`completed` progress unchanged); the sync runs under the privileged/BYPASSRLS worker connection so it may write the student's row.
  - Impl: in `services/mastery.py::_close_follow_ups`, for each `fua` set to `completed`, resolve its `follow_up` work_item (`WorkItem.source_kind='follow_up'`, `source_id=fua.id`, not deleted) and call `upsert_progress(..., user_id=fua.user_id, status="completed")` — best-effort inside the handler's transaction (a missing work_item just skips). Do NOT add a commit (the handler owns it). Guard the import to avoid a cycle (local import, as `work_items.py` does).
  - Commit `feat(followup): sync follow_up checklist progress on outcome closure`.

- [x] **B3 — follow-up action detail + revisit read (`insights.py` OR extend `review.py`).**
  - Test first (`tests/test_follow_up_detail.py`): `GET /users/me/follow-ups/{id}` (student, owner-scoped — 404 for another student's row) returns the follow-up (`action_type`, `target_kind`/`target_id`, `assignment_status`, `due_at`) merged with its linked `LearningNote`'s **reviewed** fields only (`observed_signal`, instructor-`edited`/`reviewed` `draft_interpretation`, `limitation_note`) — a `draft`/`queued` note's interpretation is NOT exposed (Decision 6, Core §0.2); plus its `OutcomeCheck.status` if one exists (the "did it move" state). A `suggested` (not yet `assigned`) follow-up returns the waiting-for-feedback shape (no action content). Marking viewed still uses the existing `POST /follow-ups/{id}/viewed`.
  - Impl: add the read to `api/review.py` (it already owns follow-ups) — reuse `verify_enrollment` is unnecessary (owner-scoped by `user_id`), 404-mask other students. New schema `FollowUpDetailResponse` in `app/schemas/evidence.py`. Revisit connection: when `target_kind='checkpoint'`, surface the existing P3 `revisit-response` path (link only — no new revisit engine).
  - Commit `feat(followup): student follow-up action detail + revisit link`.

- [x] **B4 — `insights.py` router + student learning profile (pure-read) + register.**
  - Test first (`tests/test_insights_api.py`): `GET /users/me/courses/{id}/insights` (student, `verify_enrollment` active-only — 403 otherwise) returns the caller's learning profile RESHAPED from `concept_mastery` (per-concept `mastery_score`/`confidence`/`attempt_count`, grouped into strong/developing/weak by the SAME thresholds `api/mastery.py::cohort_mastery` uses — `< 0.5` weak, `confidence >= 0.5` counted) + the pilot `claim_limits['learning_profile']` disclaimer verbatim; a student with zero mastery rows returns an empty profile with `has_evidence=false` (Decision 6); the endpoint recomputes NOTHING (asserts it reads existing rows — e.g. equals the sum from `GET /users/me/courses/{id}/mastery`). Register: `GET` reachable through the app router.
  - Impl: new `app/api/insights.py` (`router` under `/`), schemas in new `app/schemas/insights.py`. Reshape `ConceptMastery` ⋈ `Concept`. Read pilot via the same accessor `config.py`/`api/config.py` uses. Register `insights_router` in `app/api/__init__.py` (follow the alpha-ordered import + `include_router` pattern).
  - Commit `feat(insights): insights router + student learning profile (reshape mastery)`.

- [x] **B5 — ILO strength map (student + cohort).**
  - Test first (`tests/test_insights_ilo.py`): `GET /users/me/courses/{id}/ilo-map` (student) returns one row per `learning_objective` in the course, each with an aggregate strength over the concepts tagged to it (`concept_tags` `target_kind='objective'`, `target_id=objective.id`) joined to the caller's `concept_mastery`, plus `has_evidence` (false when no tagged concept has a mastery row) — Decision 7; `GET /courses/{id}/ilo-map` (teacher, `get_owned_course`) returns the cohort aggregate (avg strength + weak-student count per objective, reusing the `cohort_mastery` weak definition). Objectives with no tagged concept render `has_evidence=false`, never a fabricated 0.
  - Impl: extend `app/api/insights.py`; a shared aggregation helper (objective → tagged concept_ids → mastery aggregate). Pure read.
  - Commit `feat(insights): ILO strength map (student + cohort)`.

- [x] **B6 — skill pattern map (honest, config-driven).**
  - Test first (`tests/test_insights_skill.py`): `GET /users/me/courses/{id}/skill-map` returns one entry per pilot `skill_taxonomy` skill, each with `has_evidence=false` (Decision 5 — no schema link exists) and the skill label; the response NEVER contains a fabricated score; the endpoint is enrollment-scoped. (If a future concept→skill mapping lands, this test is the seam to extend — documented in the docstring.)
  - Impl: extend `app/api/insights.py`; read `skill_taxonomy` from the pilot profile. Keep the shape forward-compatible (a `strength`/`sample_size` field that is `null` today).
  - Commit `feat(insights): skill pattern map (config taxonomy, no-evidence honest)`.

- [x] **B7 — signal detail + evidence source view (reshape notes/events).**
  - Test first (`tests/test_insights_signal.py`): `GET /signals/{id}` resolves a `learning_note`, re-derives its `course_id`, and applies the guard — a student sees ONLY their own (`user_id`) **reviewed** signal (404 otherwise; a `draft`/`queued` note → waiting-state, not content); an instructor sees any signal in an owned course (incl. cohort `user_id IS NULL`), else 404. `GET /evidence/{id}/source` resolves a `learning_event` (or the note's `source_event_ids`) and returns its `source_kind`/`source_id`/`stage`/`value` + the anchor (`context_anchor`) for the "where did this come from" view; same owner/enrollment guard, id never trusted (Decision 8).
  - Impl: extend `app/api/insights.py`; reuse `LearningNoteResponse`/`LearningEventResponse` schemas from `app/schemas/evidence.py` where they fit; add a `SignalDetail`/`EvidenceSource` schema only if the composition needs it. Pure read.
  - Commit `feat(insights): signal detail + evidence source view`.

- [x] **B8 — teacher course insights + effectiveness tracker.**
  - Test first (`tests/test_insights_teacher.py`): `GET /courses/{id}/insights` (teacher, `get_owned_course`) reshapes into a single payload: cohort mastery summary (from `cohort_mastery` shape), open `instructor_alerts` counts by severity, and review-queue depth (open alerts / `draft`+`queued` notes) — recomputing nothing (asserts the alert counts equal `GET /courses/{id}/alerts?status=open`); `GET /courses/{id}/effectiveness` returns `outcome_checks` grouped by `status` (`improved`/`persistent`/`resolved`/`needs_review`) and by follow-up `action_type` for the owned course (Decision 9); a course with no evidence returns the designed empty payload (`has_evidence=false`). Non-owner → 404 on both.
  - Impl: extend `app/api/insights.py`; the effectiveness read joins `OutcomeCheck` → `FollowUpAction`. Pure read; no new job.
  - Commit `feat(insights): teacher course insights + effectiveness tracker`.

### Frontend (pull Figma per screen via `get_metadata` on the group first)

- [x] **F1 — hooks (`use-insights`, `use-follow-ups`) + enable the `insights` tab.**
  - New `hooks/use-insights.ts` (`useLearningProfile(courseId)`, `useIloMap(courseId)`, `useSkillMap(courseId)`, `useSignal(id)`, `useEvidenceSource(id)`, teacher `useCourseInsights(courseId)`/`useEffectiveness(courseId)` — `useAuthedQuery` reads, query-key factory, mirror `use-analytics.ts`/`use-checkpoints.ts`); new `hooks/use-follow-ups.ts` (`useMyFollowUps(courseId)`, `useFollowUpDetail(id)`, `useMarkFollowUpViewed` via `authedWrite`). Flip `insights` to `enabled:true` in `course-workspace-shell.tsx` `TABS` + add the workspace route segment. Vitest for one query + one mutation (mocked, per the offline convention — e2e/session infra unavailable, see P0–P5 handoffs).
  - Commit `feat(hooks): insights + follow-up hooks + enable insights tab`.

- [x] **F2 — student follow-up checklist item + action detail + revisit (S060, S061).**
  - The `follow_up` work_item already renders in the student checklist (P4 `_build_checklist`) — give it its own visual treatment/label (`ReviewStateChip`/`StateBanner` tone for `follow_up_assigned`) in the checklist view (S060). New route `student/courses/[courseId]/follow-ups/[followUpId]/` (Next.js 16: `params` is a **Promise — `await params`**) = action detail (S061) over `useFollowUpDetail`: shows the reviewed observed signal + instructor interpretation + limitation, the "did it move" outcome state, a "mark viewed" action, and — when `target_kind='checkpoint'` — a link into the existing P3 revisit flow. i18n `student.followUp.*`. Tokens only. Pull group `1372:330` (S060/S061).
  - Commit `feat(student): follow-up checklist item + action detail + revisit link`.

- [x] **F3 — student learning profile + signal detail (S062, S063).**
  - New route `student/courses/[courseId]/profile/` (learning profile per spec §3.3, await `params`) over `useLearningProfile` — strong/developing/weak concept groups, each concept opening a signal detail (S063) via `useSignal`/`useEvidenceSource` (the "where did this come from" drawer). Render the pilot `claim_limits.learning_profile` disclaimer verbatim (from `use-pilot-config`). i18n `student.profile.*`. Pull `1372:330` (S062/S063).
  - Commit `feat(student): learning profile + signal detail`.

- [x] **F4 — student ILO strength map + skill pattern map + no-evidence/waiting states (S064, S065, S070, S071).**
  - ILO strength map (S064) over `useIloMap` — a heat/strength grid over objectives, no-evidence cells for objectives without evidence (Decision 7). Skill pattern map (S065) over `useSkillMap` — the config skill grid, **every cell in the designed no-evidence state** with the honest "we don't have skill-level evidence yet" reason (Decision 5). Designed no-evidence (S070, `EmptyState variant="waiting"`) + waiting-for-instructor-feedback (S071, `StateBanner`) states wired to `has_evidence=false` / a `suggested`/`draft` signal (Decision 6). i18n `student.insights.*` / `patterns.*`. Pull `1372:330` (S064/S065/S070/S071).
  - Commit `feat(student): ILO + skill maps + no-evidence/waiting states`.

- [x] **F5 — teacher course insights + signal detail drawer (T076, T077).**
  - Fill the workspace `insights` tab route `teacher/courses/[courseId]/insights/` (await `params`) AND the top-level `teacher/insights/page.tsx` (course selector → per-course) over `useCourseInsights` — cohort mastery summary + open-alert severity counts + review-queue depth; REPLACE today's P0 "No evidence yet" `EmptyState` with the real view (keeping the designed empty state for a genuinely evidence-free course). Signal detail drawer (T077, `DetailDrawer` pattern) over `useSignal`/`useEvidenceSource`, incl. cohort signals. i18n `teacher.insights.*`. Pull group `1372:168` (T076/T077).
  - Commit `feat(teacher): course insights + signal detail drawer`.

- [x] **F6 — teacher evidence source view + effectiveness tracker + P6 close-out (T078, T079).**
  - Evidence source view (T078) — the instructor "where did this signal come from" panel over `useEvidenceSource` (learning_event source + anchor). Effectiveness tracker (T079) over `useEffectiveness` — `outcome_checks` improved-vs-persistent breakdown by follow-up type, the read side of the loop. Designed no-evidence state for a course with no outcomes. Playwright happy-path (review a note → assign follow-up → student sees it on the checklist → detail → later attempt closes it → effectiveness reflects it) where infra allows; else vitest against mocked hooks (offline convention). i18n `teacher.insights.*`. **P6 close-out is a SEPARATE controller step** — ship code only; do not edit the roadmap/RESUME here. Pull `1372:168` (T078/T079).
  - Commit `feat(teacher): evidence source view + effectiveness tracker + P6 verification`.

---

## Self-review checklist (before P6 close-out)

- [x] `app/api/insights.py` is PURE-READ — no mastery math, no note drafting, no alert evaluation; every number traces to an existing row (`concept_mastery`/`learning_notes`/`outcome_checks`/`instructor_alerts`/`concept_tags`) (Decision 1, B4–B8).
- [x] The follow-up→checklist seam REUSES the `work_items`/`work_item_progress` spine (`source_kind='follow_up'`, `status='follow_up_assigned'`) — **zero new tables, zero migrations** (Decision 2).
- [x] The seam write is TRANSACTIONAL + idempotent inside `review.py::review_learning_note` (atomic with the follow-up + ReviewAction; unique-index guarded), mirroring P4 B4's publish seam (Decision 3, B1).
- [x] Follow-up COMPLETION syncs onto the spine at `mastery.py::_close_follow_ups` (same transaction, best-effort, worker-privileged, idempotent) — no second reconciliation cron; `mark_missed_work_items` still protects `follow_up_assigned` (Decision 4, B2).
- [x] The skill-pattern map is HONEST — config taxonomy with per-skill `has_evidence=false`, never a fabricated score (Decision 5, B6/F4).
- [x] No-evidence + waiting-for-instructor-feedback are DESIGNED states sourced from real gates (`has_evidence=false`; `review_status ∈ draft|queued` / `assignment_status='suggested'`); a student NEVER sees an unreviewed AI draft's content (Core §0.2, Decision 6, F4/F5).
- [x] ILO strength map aggregates `concept_mastery` over `concept_tags(target_kind='objective')`; no-evidence cells never fabricated (Decision 7, B5/F4).
- [x] `insights.py` scoping mirrors existing guards: student `verify_enrollment` active-only + own-`user_id`; teacher `get_owned_course`; `/signals/{id}` + `/evidence/{id}/source` re-derive the course and re-guard (id never trusted) (Decision 8, B7).
- [x] Effectiveness tracker reads `outcome_checks` only — the read side of `_close_follow_ups`, no new job (Decision 9, B8).
- [x] `InstructorAlert` cited from `app/models/decision.py` (NOT `evidence.py`); insights reads open alerts via existing `api/instructor_alerts.py` (Reality checks).
- [x] Student S060–S065 + S070–S071 and teacher T076–T079 shipped with designed no-evidence / waiting states (never blank divs); T080–T087 + S066–S069 (reports/memory) left for P7 (F2–F6, Figma map).
- [x] `insights` workspace tab flipped `enabled:true` + route added; `teacher/insights/page.tsx` P0 placeholder replaced with the real view + its designed empty state (F1/F5).
- [x] Next.js 16: every new `page` awaits `params` (Promise); `proxy.ts` not `middleware.ts`; read `frontend/AGENTS.md` before FE work.
- [x] No hardcoded strings (next-intl `student.*`/`teacher.*`/`patterns.*`), no hardcoded colors (tokens.css), pilot `claim_limits` copy rendered verbatim; conventional commits; code review per task cluster.
