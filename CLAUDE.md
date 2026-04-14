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
│   ├── parser.py     # Docling document parsing
│   ├── chunker.py    # Text chunking
│   ├── storage.py    # Cloudflare R2 (S3-compatible via boto3)
│   └── auth.py       # Clerk JWT verification
├── middleware/    # ASGI middleware (auth gate + rate limiting on /api/rag/* only)
└── config.py      # pydantic-settings, reads from .env
```

**Auth flow:** Clerk issues JWTs on the frontend. Backend middleware does a cheap Bearer-token check. The `get_current_user` dependency does full JWT verification via JWKS, auto-creates users on first login, and assigns roles by email domain (`ust.hk` = instructor, `connect.ust.hk` = student).

**API envelope:** All endpoints return `APIResponse[T]` with `{success, data, error}`. Paginated endpoints use `PaginatedResponse[T]` adding `{meta: {total, page, limit, pages}}`.

**Task queue:** Background document processing uses a simple polling worker (`worker.py`) that claims rows from the `tasks` table with `FOR UPDATE SKIP LOCKED`. The worker runs as an asyncio task in the FastAPI lifespan.

### Frontend

```
frontend/src/
├── app/                  # Next.js 16 App Router pages
│   ├── dashboard/        # Authenticated area (courses, quizzes, flashcards)
│   ├── sign-in/, sign-up/  # Clerk auth pages
│   └── page.tsx          # Landing page
├── components/           # By feature: course/, documents/, flashcard/, quiz/, summary/, layout/, ui/
├── hooks/                # Custom hooks (useApiToken, useCourses, useDocuments, etc.)
├── lib/
│   ├── api.ts            # apiFetch<T>() — typed fetch wrapper, adds Bearer token
│   └── utils.ts, format.ts
├── proxy.ts              # Next.js 16 proxy (replaces middleware.ts) — Clerk route protection
└── styles/tokens.css     # Design tokens (oklch color space, "Honey & Salt" palette)
```

**Data fetching:** TanStack Query wraps `apiFetch()`. Hooks in `hooks/` abstract query keys and mutations. The `useApiToken` hook retrieves Clerk tokens for API calls.

## Key Conventions

- **Next.js 16**: Uses `proxy.ts` instead of `middleware.ts`. Read `frontend/AGENTS.md` and `node_modules/next/dist/docs/` before writing frontend code — APIs differ from training data.
- **Database**: All models use UUID primary keys. Soft deletes via `deleted_at` column. Alembic manages migrations with async engine.
- **Environment**: Copy `.env.example` to `backend/.env`. Frontend env vars prefixed with `NEXT_PUBLIC_`.
- **LLM calls**: OpenRouter with OpenAI SDK. Primary model is tried first; on JSON parse failure, falls back to secondary model. Both configured in settings.
- **Embeddings**: Also via OpenRouter (not direct OpenAI). `embedder.py` uses `openai.AsyncOpenAI` with `base_url=settings.openrouter_base_url` and `api_key=settings.openrouter_api_key`. Model IDs must be provider-prefixed (e.g. `openai/text-embedding-3-large`). No `OPENAI_API_KEY` is required.
- **Rate limiting**: Only applies to `/api/rag/*` endpoints. Tracked per-user per-hour in `api_usage` table. Instructors get 50 req/hr, students get 10.
- **Email domains**: `ust.hk` = instructor, `connect.ust.hk` = student. Configured via `ALLOWED_EMAIL_DOMAINS`.
- **Deployment**: Backend on Railway (Dockerfile), frontend on Vercel. Operate infra directly — Railway CLI + GraphQL API (`jq -r '.user.accessToken' ~/.railway/config.json`), Vercel CLI, Clerk REST API with `CLERK_SECRET_KEY`. Don't route the user through web dashboards when an API exists.
- **Design tokens**: Use CSS custom properties from `styles/tokens.css`, not hardcoded colors. oklch color space.
- **WSL2**: If Next.js OOMs, use `NODE_OPTIONS=--max-old-space-size=4096`.
- **Canvas OAuth (Phase 1)**: Single HKUST Canvas developer key (`CANVAS_CLIENT_ID` / `CANVAS_CLIENT_SECRET`) drives per-user OAuth — tokens are stored per user in `canvas_user_credentials`, never per course. All Canvas REST calls go through `CanvasClient` (`app/services/canvas_client.py`), which transparently refreshes the access token on a 401. The daily sync scheduler lives in `app/services/canvas_sync.py::run_scheduler` and starts as an asyncio task in the FastAPI lifespan alongside the worker. Roster sync preserves the instructor who linked the course via `preserve_user_ids` so they never get dropped by a Canvas roster diff.
