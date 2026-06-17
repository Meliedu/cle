# Meli — Work History (2026-03-30 → 2026-05-09)

Meli is an AI-powered language learning platform for HKUST (FastAPI + Next.js 16 + pgvector + Cloudflare R2). This document summarizes work delivered week by week from project kickoff through 2026-05-09. Week 1 was research and design only; the first commit landed on 2026-04-08 (Week 2). The **Implemented** column reflects what shipped to the branch that week; the **Planned** column lists the specs and implementation plans authored that week or earlier in `docs/superpowers/{specs,plans}/`. Period totals: ~346 non-merge commits on the active branch.

## Weekly Summary

| Week | Dates | Theme | Implemented | Planned |
|------|-------|-------|-------------|---------|
| **1** | 30/3 – 5/4 | Research & brainstorm | — *(no commits — design phase)* | • Phase 1a foundation plan<br>• Platform design spec<br>• Stack selection: FastAPI + Next.js 16 + pgvector + R2 |
| **2** | 6/4 – 12/4 | Scaffolding & foundation | • FastAPI skeleton, async Postgres, Alembic migrations<br>• Core schema: users, courses, documents, flashcards, quizzes, tasks<br>• Clerk JWT auth + role detection (`ust.hk` vs `connect.ust.hk`)<br>• Cloudflare R2 storage adapter<br>• Next.js 16 shell, dashboard, auth pages, quiz/flashcard players<br>• Docker Compose, pytest, Playwright E2E scaffolding | • Phase 1b RAG pipeline plan<br>• Phase 1c frontend / deploy plan<br>• Difficulty adapter spec |
| **3** | 13/4 – 19/4 | RAG + security + Canvas OAuth foundation | • End-to-end RAG (parse → chunk → embed → retrieve → generate)<br>• Hybrid search + RRF, FlashRank reranker<br>• FSRS-5 flashcard scheduler + Bayesian difficulty recalibration<br>• Live quiz + speech grading (Azure / iFlytek)<br>• Gamification: XP, streaks, badges<br>• Revision practice with REINFORCE bandit<br>• `next-intl` i18n + language toggle<br>• Canvas OAuth phase 1 (state JWT, models, migration)<br>• Postgres RLS, rate limiting, input validation | • FSRS-5 + recalibration spec (11/4)<br>• Neural spaced-repetition design (11/4)<br>• Canvas integration design (14/4)<br>• Security hardening plan (16/4)<br>• Image-coverage / VLM ingestion roadmap (16/4) |
| **4** | 20/4 – 26/4 | Canvas (P2) + folders + dashboard redesign | • Canvas full flow: OAuth → roster → file sync → enqueue processing<br>• Quiz/flashcard folder hierarchies + browser UI + cycle-safe move<br>• Dashboard redesign: warm cream surfaces, dark bronze rail, Inter type system<br>• Hero + to-do + mini-calendar home, dedicated calendar route<br>• Live-quiz bank browser, sessions panel, post-review experience<br>• Parser migration: Docling → PyMuPDF / python-docx / python-pptx + VLM rescue captions | • Mobile app design spec (26/4)<br>• Mobile plans A–E: Capacitor foundation, backend notifications, FE notification UX, native pronunciation, native flashcards (26/4) |
| **5** | 27/4 – 3/5 | Adaptive engine (P1+P2) + Better Auth migration | • **Adaptive Engine Phase 1:** curriculum tables (modules, meetings, objectives, assignments), calendar feed, syllabus parser + applier, assignment submission flow<br>• **Adaptive Engine Phase 2:** concept extraction (LLM + embeddings), clustering, prerequisite DAG, mastery (Beta-Binomial + HLR decay), tagging pipeline<br>• Clerk → **Better Auth** migration (backend verifier, frontend wiring, settings page, ~30-component codemod)<br>• Pronunciation: instructor sets, async generator, grading service, student practice UI<br>• Per-item editor for quizzes/flashcards (add / edit / delete / regenerate) | • Adaptive engine design doc (28/4)<br>• Adaptive engine Phase 1 plan (28/4)<br>• Adaptive engine Phase 2 plan (28/4)<br>• Adaptive engine Phase 3 plan (30/4) |
| **6** | 4/5 – 9/5 | Adaptive engine (P3) + correctness / polish | • **Adaptive Engine Phase 3:** `next_actions` materialization (outer-fringe SQL), 7 instructor alert rules, engine settings (mode + per-user overrides), action-outcome telemetry, daily horizon-scan cron, quarterly coefficient retune, event-driven recompute<br>• Student "Today" page (top-10 next actions), instructor alerts center, course landing nav (Today / Alerts / Engine)<br>• Instructor inline-edit for course description<br>• Correctness & perf: off-arm dedupe, cohort race lock via `pg_advisory_xact_lock`, CTE rewrites, `deleted_at` filters, NaN guard, blake2b lock key, covering index on `concept_mastery` | • Phase 3 hardening continuation (race conditions, replay split)<br>• Mobile app implementation kick-off (plans queued from W4) |

## Notes

- "Planned" entries map to files under `docs/superpowers/plans/` and `docs/superpowers/specs/` — filenames are date-prefixed (e.g. `2026-04-30-adaptive-engine-phase3-plan.md`).
- Some weeks shipped substantially more raw commits than others (W3 ≈ 96, W5 ≈ 118; W2 ≈ 49, W4 ≈ 51, W6 ≈ 32 partial); the table emphasizes **shipped feature surfaces** rather than commit volume.
- Adaptive Engine work spans W5 (P1+P2) and W6 (P3); Better Auth migration overlaps W5 alongside curriculum/mastery delivery.

## Forward Roadmap (2026-05-11 → 2026-08-31)

The next ~16 weeks are organized into **eight 2-week sprints**, executed at a realistic solo-dev pace (~1 major theme per sprint plus polish). Mobile work, production observability, and outbound email / SMS delivery infrastructure are explicitly **deferred to the post-Aug launch budget**, not silently dropped. Continuous tracks (research, dependency upkeep, Canvas sync robustness, cost monitoring) run in parallel.

| Sprint | Dates | Theme | Planned deliverables | Notes / risks |
|--------|-------|-------|----------------------|---------------|
| **S1** | 11/5 – 24/5 | Stabilization + UI/UX pass 1 | • Adaptive Engine P3 race / replay hardening (carryover from W6)<br>• Design review of Today / Alerts / Engine surfaces<br>• Empty / loading / error state polish on shipped pages<br>• Bug bash from W3–W6 surfaces | Pays down debt before new feature work; highest-leverage starting sprint. |
| **S2** | 25/5 – 7/6 | AI Resource Agent (instructor) | • Spec + safety policy<br>• Backend agent loop: web + YouTube search, citation extraction, quality / safety filter<br>• Frontend "Discover" tab in course; approval queue<br>• Ingestion of accepted items into supplementary chunk store with `source_kind=external` tag | Tool-calling + search workload will spike OpenRouter spend this sprint. |
| **S3** | 8/6 – 21/6 | Pronunciation upgrade | • Add `pronunciation_scores.pronunciation_item_id` FK + backfill<br>• Wire pronunciation attempts into mastery (closes schema gap noted in `CLAUDE.md`)<br>• Multi-language phoneme + IPA hints<br>• Practice modes: shadowing / repetition / free-speak<br>• Conversation practice prototype (TTS + ASR loop) | TTS / ASR free tiers cover dev usage; no extra cost expected. |
| **S4** | 22/6 – 5/7 | Revision mode upgrade | • REINFORCE bandit reward refinement<br>• New session formats: weak-spot drill, mixed-modality, timed sprint<br>• Per-session debrief: concept mastery delta panel<br>• Difficulty calibration smoothing | Builds on W3 revision foundation; mostly UX + tuning. |
| **S5** | 6/7 – 19/7 | DB upgrade + perf | • pgvector tuning; HNSW where dim ≤ 2000<br>• Index / FK / `deleted_at`-filter audit<br>• Connection-pool review<br>• Backup / restore drill<br>• Query-plan audit on Today / Alerts hot paths | Enables larger user base in Sept; no schema-breaking changes planned. |
| **S6** | 20/7 – 2/8 | Instructor Alert Agent | • Daily morning brief: at-risk students, struggling concepts<br>• Prioritized to-do list with severity (P0 / P1 / P2)<br>• Email digest — log-only during dev (no transactional email service wired yet)<br>• Suggested actions sourced from existing 7-rule alert system | Wiring an actual email/SMS sender is deferred to the launch budget; dev uses a log-only digest. |
| **S7** | 3/8 – 16/8 | Student analytics dashboard | • Concept mastery heatmap (module / objective)<br>• Learning velocity + retention curves<br>• Anonymized cohort percentile<br>• Instructor cohort view (at-risk list, mastery distribution)<br>• CSV / PDF export | Read-only — no new write paths; lower risk. |
| **S8** | 17/8 – 31/8 | UI/UX pass 2 + beta-readiness | • Onboarding flow polish (instructor + student)<br>• Empty / error / loading state audit<br>• Accessibility audit (WCAG AA)<br>• E2E coverage on critical flows (signup → upload → quiz / flashcard)<br>• Instructor & student guide docs, API reference | Aimed at "ready to invite first real cohort" by 1 Sept. |

**Continuous tracks (parallel):** new-feature research log · dependency / security patches · Canvas sync robustness · cost monitoring & prompt-cache tuning.

**Explicitly deferred (post-Aug launch budget):** Mobile app (Capacitor + native pronunciation / flashcards) · production observability (Sentry, structured logs, uptime) · outbound email / SMS delivery infrastructure. Meli itself remains free for HKUST users — none of these are user-facing premium features.

## Dev Budget Estimate (2026-05-11 → 2026-08-31)

Period: ~3.7 months / 16 weeks of **development only**. A separate budget will be authored for the September launch (production hosting tier upgrades, observability, email / SMS delivery infrastructure, support tooling). The dominant variable cost during dev is OpenRouter API usage; everything else is fixed and small.

| Item | Mo. low | Mo. high | Period (low – high) | Notes |
|------|---------|----------|---------------------|-------|
| Railway Hobby (Postgres + backend host) | $5 | $5 | $20 | Already paying. |
| OpenRouter — embeddings (`openai/text-embedding-3-large`) | $1 | $5 | $4 – $19 | Driven by re-ingestion test cycles. |
| OpenRouter — generation (Sonnet 4.6 / Haiku 4.5 / Gemini Flash via gateway) | $10 | $30 | $37 – $111 | Quiz / flashcard / summary / concept extraction. Spikes during S2 (resource agent) and S6 (alert agent). |
| OpenRouter — VLM captions (Gemini 2.5 Flash) | $1 | $3 | $4 – $11 | Figure / image captions during ingestion testing. |
| OpenRouter — adaptive engine workloads | $3 | $10 | $11 – $37 | Concept extraction, mastery batch, tagging. |
| Vercel — frontend (Hobby plan, free tier) | $0 | $0 | $0 | Stays free for dev / pre-beta. |
| Cloudflare R2 — object storage | $0 | $1 | $0 – $4 | 10 GB + 1M reads free; dev usage trivial. |
| Azure / iFlytek speech APIs | $0 | $5 | $0 – $19 | Free / dev tiers. |
| Domain (optional, if registered) | $1 | $1 | $4 | E.g. a `.com` for staging. |
| Buffer (10–15%) | $2 | $7 | $7 – $26 | Unexpected spikes (failed regenerations, prompt iteration). |
| **Total** | **~$23** | **~$67** | **~$87 – $251** | Mid-point estimate ≈ **$170 over the dev period**. |

**Currently incurred (8/4 → 9/5, est.):** Railway Hobby ≈ $5 + OpenRouter usage to date — actuals available from the OpenRouter / Railway dashboards.

