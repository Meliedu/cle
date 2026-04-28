# Adaptive Engine — Resume Pointer

> **Purpose:** drop-in context for a fresh Claude Code session picking up the adaptive engine work after a `/compact`. Read this first, then the spec, then the active plan.

**Last updated:** 2026-04-28

## State

| Doc | Path | Commit | Status |
|---|---|---|---|
| Design spec | `docs/superpowers/specs/2026-04-28-adaptive-engine-design.md` | `f63c6e5` | ✅ approved by user |
| Phase 1 plan | `docs/superpowers/plans/2026-04-28-adaptive-engine-phase1-plan.md` | `5d7487b` | ✅ ready to execute (15 tasks, TDD-shaped) |
| Phase 2 plan | not written | — | ⏳ write AFTER Phase 1 ships + ≥2 weeks soak |
| Phase 3 plan | not written | — | ⏳ write AFTER Phase 2 mastery has produced real data |

## What we're building

A curriculum-centered adaptive learning engine that layers above (does not replace) the existing bandit + FSRS-5 + recalibration policy stack. Three independently-shippable phases:

1. **Phase 1 — Curriculum spine + calendar + scoped syllabus parser.** Standalone product win even before any concept work. 6 new tables (`course_modules`, `course_meetings`, `learning_objectives`, `assignments`, `assignment_submissions`, `syllabus_imports`) + `documents.kind` column. Plan ready.
2. **Phase 2 — Concepts knowledge graph + Beta-Binomial mastery + HLR decay + syllabus-as-generation-context.** Adds the "meaning layer." `concepts`, `concept_prerequisites`, polymorphic `concept_tags`, `concept_mastery`. Pre-fills mastery via 90-day attempt replay.
3. **Phase 3 — Decision layer.** `next_actions` ranked by KST "outer fringe" predicate, `instructor_alerts`, `action_outcomes` telemetry, engine on/off toggle (`courses.adaptive_engine_mode` + `engine_overrides.random_50` for A/B).

## Locked product decisions (do not re-litigate)

| # | Decision | Reason |
|---|---|---|
| 1 | Concept curation = **medium-touch** (LLM extracts → cluster → instructor curates per cluster, ~30 min/course) | Pure LLM extraction produces unstable join keys (literature consensus 2025) |
| 2 | Outcome telemetry uses **per-cohort A/B switch** with toggle (engine on/off/random_50) | Investors want measurable lift, not just "feels better" |
| 3 | ALOSI / Open edX = **reference only**, not fork | Their schema is XBlock-coupled |
| 4 | Phase 1 ships **standalone** (no concepts in it) | Validates calendar UX before harder layer; pause point ≥2 weeks |
| 5 | Pronunciation feeds `concept_mastery` via `overall_score / 100` | Single uniform evidence model |
| 6 | `assignment_submissions` shipped in Phase 1 (un-deferred) | Canvas integration not confirmed; planned publish flow needs real submission tracking |
| 7 | Scoped syllabus parser shipped in Phase 1 (un-deferred, reframed) | Parses ONLY documents with `kind='syllabus'`; not arbitrary lecture notes |

## Locked technical decisions (research-grounded; do not re-litigate)

| # | Decision | Replaces | Evidence |
|---|---|---|---|
| 1 | Beta-Binomial posterior for `concept_mastery` | EMA in initial spec | EMA is not a published mastery method; PDT/Beta gives mean+variance+cold-start for same complexity |
| 2 | HLR-style nightly decay shipped in Phase 2.2 (with mastery) | Decay deferred to "future" in initial spec | Duolingo +9.5% retention, ~50% error reduction |
| 3 | KST "outer fringe" predicate as first-class candidate filter for `next_actions` | Hand-tuned coefficients alone | ALEKS uses KST; instructor-explainable |
| 4 | Single polymorphic `concept_tags(target_kind, target_id, concept_id, weight)` | 8 separate tagging tables | One migration, one write path, partial indexes per kind |
| 5 | `course_meetings` (not `class_sessions`) | Avoid collision with existing `LiveSession` model | Naming clarity |
| 6 | `concept.embedding vector(3072)` | Was `vector(1536)` in initial spec | Matches `openai/text-embedding-3-large` native dim |

## Triggers to write Phase 2 plan

Wait for ALL of these before invoking the writing-plans skill on Phase 2:

- [ ] Phase 1 PR merged + deployed to production
- [ ] At least 2 weeks of real instructor use on calendar / assignments / syllabus uploader
- [ ] Phase-1-feedback note captured (instructor pain points, calendar UX issues, parser quality observations)
- [ ] Spec re-read with Phase 1 reality in mind (any decisions invalidated by what we learned shipping?)

Phase 2 plan should reference real Phase 1 codebase patterns (file paths, conventions, what worked, what didn't) — that's why writing it now would produce lower quality.

## Triggers to write Phase 3 plan

- [ ] Phase 2 PR merged + deployed
- [ ] At least 4 weeks of real student attempt data flowing through Beta-Binomial mastery
- [ ] Mastery distribution sanity-checked (no concept stuck at 0.0 or 1.0 for everyone, decay behaving)
- [ ] Concept curation effort actually measured per course (validates the "30 min/course" assumption)

## Critical context for any future session

- **Existing stack:** FastAPI + SQLAlchemy 2.0 async + Alembic + Postgres 17 + pgvector + Next.js 16 App Router (proxy.ts NOT middleware.ts) + React 19 + TanStack Query + Better Auth.
- **Existing strong layers (DO NOT REPLACE):**
  - Content: `documents` → `chunks` (HNSW + tsvector) → quiz/flashcard/summary generators (`app/services/generator.py`)
  - Evidence: `quiz_attempts`, `flashcard_progress` (FSRS-5), `revision_attempts` (with bandit-selected difficulty), `pronunciation_scores`
  - Policy: `bandit_models` (per user/course/content_type), `scheduler_models` (FSRS-5 19 params per user/course), `recalibration_*` machinery
- **Worker:** `app/services/worker.py:196` already uses `FOR UPDATE SKIP LOCKED`. New `task_type` values are dispatched via the if/elif chain at `worker.py:273+`. Add new branches there.
- **Auth:** Better Auth (self-hosted), JWTs verified against JWKS at `BETTER_AUTH_JWKS_URL`. `get_current_user` dependency creates user rows on first login.
- **Test DB:** `langassistant_test`. `conftest.py` provides `db_session`, `async_client`, `logged_in_user`, `test_instructor`, `test_student` fixtures.

## Validation refs (kept here so they don't drift)

Spec was validated against:
- ALEKS / Knowledge Space Theory ([Falmagne ALEKS science](https://www.aleks.com/about_aleks/Science_Behind_ALEKS.pdf))
- ALOSI / Open edX adaptive engine ([wiki](https://openedx.atlassian.net/wiki/spaces/AC/pages/575799401/Adaptive+Learning+Tools+and+Engines))
- Duolingo HLR ([paper](https://research.duolingo.com/papers/settles.acl16.pdf))
- DAS3H ([arxiv 1905.06873](https://arxiv.org/abs/1905.06873))
- KT survey ([ACM Computing Surveys 2023](https://dl.acm.org/doi/full/10.1145/3569576))
- Lan & Baraniuk contextual bandits for learning ([EDM 2016](https://people.umass.edu/~andrewlan/papers/16edm-bandits.pdf))
- 2025 LLM-for-educational-KG papers ([Springer](https://link.springer.com/article/10.1007/s42979-024-03341-y), [MDPI 2025](https://www.mdpi.com/2504-4990/7/3/103))

## How to resume

If Phase 1 is not yet started:
1. Read this file
2. Read `docs/superpowers/specs/2026-04-28-adaptive-engine-design.md`
3. Read `docs/superpowers/plans/2026-04-28-adaptive-engine-phase1-plan.md`
4. Invoke `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to execute Task 1

If Phase 1 is in progress:
1. Read this file
2. Check git log for the latest committed task
3. Resume executing-plans from the next unchecked task in the plan file

If Phase 1 just shipped and triggers above are met:
1. Read this file
2. Capture Phase-1-feedback observations
3. Re-read spec with that lens
4. Invoke `superpowers:writing-plans` for Phase 2

Do NOT write Phase 2 or 3 plans before their triggers are met. The plans will be lower quality without real Phase 1 codebase context.
