# CLAUDE.md

MUST READ THE ACUTAL RELEVANT FILES BEFORE DOING ANYTHING!!
This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Meli is an AI-powered language learning platform for HKUST. Instructors upload course materials (PDF, DOCX, PPTX, audio); the backend parses, chunks, and embeds them into pgvector. Students get auto-generated quizzes, flashcards, and summaries via RAG.

## Commands

### Backend (run from `backend/`)

```bash
# Start dev server (auto-reloads)
uvicorn app.main:app --reload

# Run all tests (requires langassistant_test database)
pytest

# Run a single test file
pytest tests/test_auth_service.py

# Run a single test by name
pytest tests/test_auth_service.py -k "test_name"

# Database migrations
alembic upgrade head           # apply all
alembic revision --autogenerate -m "description"  # create new

# Seed dev data
python seed.py
```

### Frontend (run from `frontend/`)

```bash
npm run dev       # Next.js dev server (Turbopack)
npm run build     # production build
npm run lint      # ESLint
npm run e2e       # Playwright E2E tests
npm run e2e:ui    # Playwright with interactive UI
```

### Infrastructure

```bash
# Start PostgreSQL 17 + pgvector (from repo root)
docker compose up -d

# Default connection: postgresql+asyncpg://postgres:postgres@localhost:5432/langassistant
# Test database: create langassistant_test manually with same creds
```

## Architecture

### Monorepo layout

- `backend/` — Python FastAPI API server
- `frontend/` — Next.js 16 App Router (TypeScript, React 19)
- `docs/superpowers/` — Specs and implementation plans

### Backend

```
backend/app/
├── api/           # FastAPI routers (all under /api prefix)
│   ├── deps.py    # Dependency injection: get_current_user, require_instructor, get_db
│   ├── rag.py     # RAG endpoints: query, generate-quiz, generate-summary, generate-flashcards
│   ├── courses.py, documents.py, quizzes.py, flashcards.py, auth.py, canvas.py
├── models/        # SQLAlchemy 2.0 async models (UUID PKs, TimestampMixin, SoftDeleteMixin)
├── schemas/       # Pydantic v2 request/response schemas
├── services/      # Business logic
│   ├── pipeline.py   # Document processing: download → parse → chunk → embed → store
│   ├── worker.py     # Background task queue (polls tasks table, skip_locked)
│   ├── generator.py  # LLM generation via OpenRouter (primary + fallback model strategy)
│   ├── retriever.py  # pgvector similarity search
│   ├── embedder.py   # OpenAI text-embedding-3-large
│   ├── parser.py     # PDF via Docling (+VLM figure captions) w/ pymupdf fallback; DOCX via python-docx; PPTX via python-pptx (+VLM image captions); mp3/mp4 via Whisper
│   ├── vlm.py        # Vision-LLM caption client (OpenRouter) — non-raising
│   ├── chunker.py    # Text chunking
│   ├── storage.py    # Cloudflare R2 (S3-compatible via boto3)
│   └── auth.py       # Better Auth JWT verification (PyJWKClient against /api/auth/jwks)
├── middleware/    # ASGI middleware (auth gate + rate limiting on /api/rag/* only)
└── config.py      # pydantic-settings, reads from .env
```

**Auth flow:** Better Auth (self-hosted) issues JWTs on the Next.js side via its JWT plugin (EdDSA / Ed25519). The frontend `useApiToken` hook calls `authClient.token()` to fetch a fresh JWT for each backend request. Backend middleware does a cheap Bearer-token check; the `get_current_user` dependency verifies the JWT against the JWKS at `BETTER_AUTH_JWKS_URL` (e.g. `http://localhost:3000/api/auth/jwks`), auto-creates `public.users` rows on first login keyed on `better_auth_id`, and assigns roles by email domain (`ust.hk` = instructor, `connect.ust.hk` = student). Better Auth's own tables (`user`, `session`, `account`, `verification`, `jwks`) live in the `auth` schema of the same Postgres. Sign-up flows from the Next.js side fire a `databaseHooks.user.create.after` hook that POSTs to `POST /api/internal/users/link` (guarded by `BETTER_AUTH_INTERNAL_SECRET`) so the local row is created/linked atomically.

**API envelope:** All endpoints return `APIResponse[T]` with `{success, data, error}`. Paginated endpoints use `PaginatedResponse[T]` adding `{meta: {total, page, limit, pages}}`.

**Task queue:** Background document processing uses a simple polling worker (`worker.py`) that claims rows from the `tasks` table with `FOR UPDATE SKIP LOCKED`. The worker runs as an asyncio task in the FastAPI lifespan. Phase 2 added the concept/mastery family: `extract_concept_candidates` (LLM concept extraction → cluster), `tag_artifact_concepts` (chunk LLM tag or inheritance from source chunk), `update_concept_mastery` (Beta-Binomial update with `_task_created_at` watermark dedupe to handle worker retries safely), `replay_attempt_history` (90-day backfill, instructor-triggered with 409 in-flight guard).

**Concept layer (Phase 2):** `concepts` (per-course ontology with `canonical_id` soft-merge + `cluster_id` for curation), `concept_prerequisites` (DAG edges with WITH RECURSIVE cycle check at write), `concept_tags` (single polymorphic table; `target_kind` ∈ chunk|question|flashcard_card|pool_item|pronunciation_item|objective|meeting|assignment), `concept_mastery` (per-user-per-concept with composite PK and a GENERATED STORED `mastery_score = α/(α+β)` column), `concept_mastery_history` (append-only audit log). Concept embeddings are `vector(3072)` (native dim of `text-embedding-3-large`); HNSW index intentionally absent because pgvector caps HNSW at 2000 dims for `vector` type and clustering runs in-process.

**Mastery flow:** Each attempt-recording endpoint (`api/quizzes.py`, `api/flashcards.py`, `api/revision.py`) enqueues an `update_concept_mastery` task after committing the user's attempt (try/except so attempt durability is preserved on enqueue failure). Generation jobs (`run_generate_quiz`/`flashcards`/`pronunciation`) and pool replenishment enqueue `tag_artifact_concepts` tasks that inherit concept tags from the source chunk at weight × 0.7. The mastery handler (`services/mastery.py::apply_attempt_evidence`) joins `ConceptTag` for the target, runs Beta-Binomial update `α += w·outcome, β += w·(1−outcome)`, recomputes `confidence = 1 − sqrt(αβ / ((α+β)²(α+β+1)))`, and appends a history row. A nightly cron (`worker.py`'s `last_decay_run` watermark) calls `decay_due_mastery_rows` for HLR-style forgetting (`decay = 2^(−days/τ)`, default τ=14d). Pronunciation attempts are not yet wired (schema gap: `pronunciation_scores` lacks `pronunciation_item_id` FK).

### Frontend

```
frontend/src/
├── app/                  # Next.js 16 App Router pages
│   ├── dashboard/        # Authenticated area (courses, quizzes, flashcards)
│   ├── sign-in/, sign-up/  # Better Auth screens (custom-built, see components/auth/)
│   └── page.tsx          # Landing page
├── components/           # By feature: course/, documents/, flashcard/, quiz/, summary/, layout/, ui/
├── hooks/                # Custom hooks (useApiToken, useCourses, useDocuments, etc.)
├── lib/
│   ├── api.ts            # apiFetch<T>() — typed fetch wrapper, adds Bearer token
│   └── utils.ts, format.ts
├── proxy.ts              # Next.js 16 proxy (replaces middleware.ts) — Better Auth session check
└── styles/tokens.css     # Design tokens (oklch color space, "Honey & Salt" palette)
```

**Data fetching:** TanStack Query wraps `apiFetch()`. Hooks in `hooks/` abstract query keys and mutations. The `useApiToken` hook calls `authClient.token()` to retrieve a Better Auth JWT for backend calls.

## Key Conventions

- **Next.js 16**: Uses `proxy.ts` instead of `middleware.ts`. Read `frontend/AGENTS.md` and `node_modules/next/dist/docs/` before writing frontend code — APIs differ from training data.
- **Database**: All models use UUID primary keys. Soft deletes via `deleted_at` column. Alembic manages migrations with async engine.
- **Environment**: Copy `.env.example` to `backend/.env`. Frontend env vars prefixed with `NEXT_PUBLIC_`.
- **LLM calls**: OpenRouter with OpenAI SDK. Primary model is tried first; on JSON parse failure, falls back to secondary model. Both configured in settings.
- **Embeddings**: Also via OpenRouter (not direct OpenAI). `embedder.py` uses `openai.AsyncOpenAI` with `base_url=settings.openrouter_base_url` and `api_key=settings.openrouter_api_key`. Model IDs must be provider-prefixed (e.g. `openai/text-embedding-3-large`). No `OPENAI_API_KEY` is required.
- **Figure captions**: PDFs are parsed by Docling with its remote `PictureDescriptionApiOptions` pointed at OpenRouter (`vlm_model`, default `google/gemini-2.5-flash`). PPTX Picture shapes are captioned by `app/services/vlm.py::caption_image`. Captions are inlined into page text as `[Figure: ...]` so the chunker keeps them adjacent to surrounding context; resulting chunks get `metadata.has_figure=True`. Disable via `ENABLE_FIGURE_CAPTIONS=false` in dev to save OpenRouter spend. Docling runs in the async worker (not request path); first run downloads ~400 MB of model weights.
- **Rate limiting**: Only applies to `/api/rag/*` endpoints. Tracked per-user per-hour in `api_usage` table. Instructors get 50 req/hr, students get 10.
- **Email domains**: `ust.hk` = instructor, `connect.ust.hk` = student. Configured via `ALLOWED_EMAIL_DOMAINS`.
- **Deployment**: Backend on Railway (Dockerfile), frontend on Vercel. Operate infra directly — Railway CLI + GraphQL API (`jq -r '.user.accessToken' ~/.railway/config.json`), Vercel CLI. Don't route the user through web dashboards when an API exists.
- **Design tokens**: Use CSS custom properties from `styles/tokens.css`, not hardcoded colors. oklch color space.
- **WSL2**: If Next.js OOMs, use `NODE_OPTIONS=--max-old-space-size=4096`.
- **Canvas OAuth (Phase 1)**: Single HKUST Canvas developer key (`CANVAS_CLIENT_ID` / `CANVAS_CLIENT_SECRET`) drives per-user OAuth — tokens are stored per user in `canvas_user_credentials`, never per course. All Canvas REST calls go through `CanvasClient` (`app/services/canvas_client.py`), which transparently refreshes the access token on a 401. The daily sync scheduler lives in `app/services/canvas_sync.py::run_scheduler` and starts as an asyncio task in the FastAPI lifespan alongside the worker. Roster sync preserves the instructor who linked the course via `preserve_user_ids` so they never get dropped by a Canvas roster diff.
- **Race-safe upsert:** New rows in `concept_mastery` (and similar per-user state) use `pg_insert(...).on_conflict_do_nothing(index_elements=[...]).returning(...)` then re-fetch on conflict — see `services/mastery.py::_get_or_create_mastery`. Avoids `IntegrityError` aborting the whole transaction under concurrent first-attempt races.
- **Worker retry idempotency:** Tasks that mutate user-facing state (e.g. `update_concept_mastery`) carry a `_task_created_at` watermark injected by the dispatcher. The handler checks `concept_mastery_history` for `recorded_at >= watermark` and skips if already-applied. Closes the seam between handler-commit and complete_task-commit when `_reset_stuck_tasks` requeues.
- **GENERATED columns mirrored in ORM:** `concept_mastery.mastery_score` is `GENERATED ALWAYS AS (alpha/(alpha+beta)) STORED` in PG. The SQLAlchemy model declares it via `Computed("alpha / (alpha + beta)", persisted=True)` so `Base.metadata.create_all` (used by tests) reproduces the constraint. Never set `mastery_score` from Python — only `alpha`/`beta`.
- **`Task.payload` is JSON (not JSONB).** Use `Task.payload.op("->>")("course_id")` for queries; `astext` won't work.
