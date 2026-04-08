<p align="center">
  <img src="https://img.shields.io/badge/-%F0%9F%8D%AF%20Meli-F5A623?style=for-the-badge&labelColor=1a1a2e" alt="Meli" />
</p>

<h1 align="center">
  Meli
</h1>

<p align="center">
  <strong>AI-powered language learning for university classrooms</strong>
</p>

<p align="center">
  Upload course materials. Generate quizzes, flashcards, and summaries in seconds.<br/>
  Built for HKUST's Center for Language Education.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-0.128-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Next.js-16-000000?style=flat-square&logo=next.js&logoColor=white" alt="Next.js" />
  <img src="https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black" alt="React" />
  <img src="https://img.shields.io/badge/PostgreSQL-17-4169E1?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/pgvector-HNSW-4169E1?style=flat-square" alt="pgvector" />
  <img src="https://img.shields.io/badge/TypeScript-strict-3178C6?style=flat-square&logo=typescript&logoColor=white" alt="TypeScript" />
</p>

<br/>

---

<br/>

## What is Meli?

Meli (_honey_ in several languages, _salt_ in Hebrew) is a RAG-powered platform that transforms static course materials into interactive study tools. Instructors upload PDFs, slides, or audio recordings; the system parses, chunks, and embeds them into a vector store. Students then get AI-generated quizzes with instant grading, spaced-repetition flashcards, and concise summaries - all grounded in their actual course content.

### For Instructors

- **Upload anything** - PDF, DOCX, PPTX, MP3, MP4. Docling parses documents; Whisper transcribes audio.
- **Generate quizzes** from uploaded materials with one click. Edit, publish, and track student attempts.
- **Generate flashcard sets** tied to specific documents or entire courses.
- **Canvas LMS integration** - import files directly from connected Canvas courses.
- **Usage analytics** - per-student rate limiting protects against API cost overruns.

### For Students

- **Practice quizzes** - take AI-generated quizzes with explanations for every answer.
- **Flashcards with SM-2** - spaced repetition algorithm schedules reviews at optimal intervals.
- **Summaries** - get markdown summaries of any subset of course materials.
- **Enrollment-scoped** - students only see courses and materials they're enrolled in.

<br/>

---

<br/>

## Architecture

```
                                    ┌─────────────────────┐
                                    │   Clerk (Auth)       │
                                    └──────────┬──────────┘
                                               │ JWT
                    ┌──────────────────────────┐│┌──────────────────────────┐
                    │                          │││                          │
                    │   Next.js 16 (Vercel)    │││   FastAPI (Railway)      │
                    │                          ├┤│                          │
                    │   App Router + React 19  │ │   Async Python 3.12     │
                    │   TanStack Query         │ │                          │
                    │   Tailwind CSS 4         │ │   ┌──────────────────┐   │
                    │   shadcn/ui              │ │   │  API Routers     │   │
                    │                          │ │   │  auth, courses,  │   │
                    └──────────────────────────┘ │   │  documents, rag, │   │
                                                 │   │  quizzes, flash  │   │
                                                 │   └────────┬─────────┘   │
                                                 │            │             │
                                                 │   ┌────────▼─────────┐   │
                                                 │   │  Service Layer   │   │
                                                 │   │                  │   │
                                                 │   │  parser embedder │   │
                                                 │   │  chunker retriev │   │
                                                 │   │  generator       │   │
                                                 │   └──┬────┬────┬─────┘   │
                                                 │      │    │    │         │
                                                 │   ┌──▼──┐ │ ┌──▼──────┐  │
                                                 │   │Task │ │ │OpenAI   │  │
                                                 │   │Queue│ │ │Embedder │  │
                                                 │   └──┬──┘ │ └─────────┘  │
                                                 │      │    │              │
                                                 └──────┼────┼──────────────┘
                                                        │    │
                                              ┌─────────▼────▼──────────┐
                                              │  PostgreSQL 17          │
                                              │  + pgvector (HNSW)      │
                                              │                         │
                                              │  users, courses, docs,  │
                                              │  chunks, quizzes,       │
                                              │  flashcards, tasks,     │
                                              │  api_usage              │
                                              └─────────────────────────┘
                                                        │
                              ┌──────────────────────────┼──────────────────────────┐
                              │                          │                          │
                     ┌────────▼────────┐       ┌─────────▼────────┐      ┌──────────▼──────────┐
                     │ Cloudflare R2   │       │ OpenRouter       │      │ OpenAI Whisper      │
                     │ File Storage    │       │ LLM Generation   │      │ Audio Transcription │
                     └─────────────────┘       └──────────────────┘      └─────────────────────┘
```

### Monolith-first, splittable later

A single FastAPI process serves both HTTP requests and a background task worker. The worker runs as an asyncio task in the [lifespan context](backend/app/main.py), polling a PostgreSQL-backed job queue with `SELECT FOR UPDATE SKIP LOCKED`. When scale demands it, the worker can become a separate Railway service with the same codebase and a different entrypoint.

<br/>

---

<br/>

## RAG Pipeline

The document processing pipeline is the core of Meli. When an instructor uploads a file:

```
 Upload                Parse                 Chunk                  Embed                Store
┌──────┐  R2 store   ┌──────┐  Markdown    ┌──────┐  ~500 tok    ┌──────┐  vector     ┌──────┐
│ File │ ──────────► │Docling│ ──────────► │Chunker│ ──────────► │OpenAI│ ──────────► │pgvec │
│      │             │Whisper│             │       │  overlap     │      │  1536 dim   │ tor  │
└──────┘             └──────┘             └──────┘              └──────┘             └──────┘
                         │                     │
                    PDF/DOCX/PPTX        Sentence-aligned
                    MP3/MP4              50-token overlap
```

| Stage | Service | Details |
|-------|---------|---------|
| **Parse** | [parser.py](backend/app/services/parser.py) | Docling for PDF/DOCX/PPTX with page-level extraction. Whisper for MP3/MP4. |
| **Chunk** | [chunker.py](backend/app/services/chunker.py) | Sentence-aligned splitting at ~500 tokens with 50-token overlap. Page numbers preserved. |
| **Embed** | [embedder.py](backend/app/services/embedder.py) | OpenAI `text-embedding-3-large` (1536 dims). Batched in groups of 100. |
| **Retrieve** | [retriever.py](backend/app/services/retriever.py) | pgvector cosine similarity (`<=>` operator). Course-scoped, optionally filtered by document. |
| **Generate** | [generator.py](backend/app/services/generator.py) | OpenRouter LLM with automatic fallback. Primary model tried first; on JSON parse failure, secondary model retried. |

### Generation outputs

| Endpoint | Output | Who can call |
|----------|--------|--------------|
| `POST /api/rag/query` | Retrieved chunks with similarity scores | Any enrolled user |
| `POST /api/rag/generate-quiz` | Multiple-choice quiz (persisted) | Instructors only |
| `POST /api/rag/generate-summary` | Markdown summary | Any enrolled user |
| `POST /api/rag/generate-flashcards` | Flashcard set (persisted) | Any enrolled user |

<br/>

---

<br/>

## Tech Stack

### Backend

| Layer | Technology |
|-------|-----------|
| Framework | **FastAPI** 0.128 (async, Python 3.12) |
| ORM | **SQLAlchemy** 2.0 async + asyncpg |
| Migrations | **Alembic** with async engine |
| Auth | **Clerk** JWT verification via PyJWKClient |
| Storage | **Cloudflare R2** (S3-compatible, boto3) |
| Vectors | **pgvector** HNSW cosine similarity |
| Parsing | **Docling** 2.31 (PDF/DOCX/PPTX) + **Whisper** (audio) |
| LLM | **OpenRouter** (OpenAI-compatible SDK) |
| Embeddings | **OpenAI** text-embedding-3-large |
| Testing | **pytest** + pytest-asyncio |

### Frontend

| Layer | Technology |
|-------|-----------|
| Framework | **Next.js** 16 (App Router, Turbopack) |
| UI | **React** 19 + **TypeScript** strict |
| Components | **shadcn/ui** + **Tailwind CSS** 4 |
| Data fetching | **TanStack Query** v5 |
| Auth | **@clerk/nextjs** 7 |
| Icons | **Lucide React** |
| E2E testing | **Playwright** |

### Infrastructure

| Service | Provider |
|---------|----------|
| Database | **PostgreSQL 17 + pgvector** on Railway |
| Backend | **Railway** (Docker) |
| Frontend | **Vercel** |
| File storage | **Cloudflare R2** |
| Auth | **Clerk** |

<br/>

---

<br/>

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker (for PostgreSQL)
- Clerk account
- OpenAI API key
- OpenRouter API key (free tier available)

### 1. Clone and configure

```bash
git clone https://github.com/your-org/meli.git
cd meli

# Backend environment
cp .env.example backend/.env
# Edit backend/.env with your keys
```

### 2. Start the database

```bash
docker compose up -d
```

This starts PostgreSQL 17 with pgvector on port 5432.

### 3. Backend setup

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Seed demo data (optional)
python seed.py

# Start the dev server
uvicorn app.main:app --reload
```

The API is now at `http://localhost:8000`. Health check: `GET /health`. Docs: `GET /docs`.

### 4. Frontend setup

```bash
cd frontend
npm install
npm run dev
```

The app is now at `http://localhost:3000`.

### 5. Testing

```bash
# Backend (requires langassistant_test database)
cd backend && pytest

# Frontend E2E
cd frontend && npm run e2e
```

<br/>

---

<br/>

## Environment Variables

<details>
<summary><strong>Backend</strong> (<code>backend/.env</code>)</summary>

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL async connection string |
| `CLERK_SECRET_KEY` | Clerk backend API key |
| `CLERK_JWKS_URL` | Clerk JWKS endpoint for JWT verification |
| `R2_ACCOUNT_ID` | Cloudflare account ID |
| `R2_ACCESS_KEY_ID` | R2 access key |
| `R2_SECRET_ACCESS_KEY` | R2 secret key |
| `R2_BUCKET_NAME` | R2 bucket name |
| `R2_ENDPOINT_URL` | R2 S3-compatible endpoint |
| `OPENAI_API_KEY` | For embeddings + Whisper |
| `OPENROUTER_API_KEY` | For LLM generation |
| `OPENROUTER_PRIMARY_MODEL` | Primary model (default: `qwen/qwen3.6-plus:free`) |
| `OPENROUTER_FALLBACK_MODEL` | Fallback model (default: `google/gemini-2.5-flash-lite`) |
| `ALLOWED_EMAIL_DOMAINS` | Comma-separated (e.g., `connect.ust.hk,ust.hk`) |
| `STUDENT_RATE_LIMIT` | AI requests per hour for students (default: 10) |
| `INSTRUCTOR_RATE_LIMIT` | AI requests per hour for instructors (default: 50) |

</details>

<details>
<summary><strong>Frontend</strong> (<code>frontend/.env.local</code>)</summary>

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Clerk publishable key |
| `CLERK_SECRET_KEY` | Clerk secret key |
| `NEXT_PUBLIC_API_URL` | Backend API URL (default: `http://localhost:8000/api`) |
| `NEXT_PUBLIC_CLERK_SIGN_IN_URL` | Sign-in route (default: `/sign-in`) |
| `NEXT_PUBLIC_CLERK_SIGN_UP_URL` | Sign-up route (default: `/sign-up`) |

</details>

<br/>

---

<br/>

## API Reference

All endpoints are prefixed with `/api` and require `Authorization: Bearer <clerk_jwt>` except `/health`.

Response envelope:

```json
{
  "success": true,
  "data": { ... },
  "error": null
}
```

<details>
<summary><strong>Courses</strong></summary>

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/courses` | Instructor | Create a course |
| `GET` | `/api/courses` | Any | List enrolled courses |
| `GET` | `/api/courses/:id` | Enrolled | Course detail |
| `PUT` | `/api/courses/:id` | Instructor | Update course |
| `DELETE` | `/api/courses/:id` | Instructor | Soft delete |
| `POST` | `/api/courses/:id/enroll` | Any | Enroll in course |

</details>

<details>
<summary><strong>Documents</strong></summary>

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/courses/:id/documents/upload` | Instructor | Upload file (PDF, DOCX, PPTX, MP3, MP4) |
| `GET` | `/api/courses/:id/documents` | Enrolled | List course documents |
| `DELETE` | `/api/courses/:id/documents/:docId` | Instructor | Soft delete |

Accepted MIME types: `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `application/vnd.openxmlformats-officedocument.presentationml.presentation`, `video/mp4`, `audio/mpeg`. Max size: 100MB (configurable).

</details>

<details>
<summary><strong>RAG Generation</strong></summary>

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/rag/query` | Enrolled | Semantic search over course chunks |
| `POST` | `/api/rag/generate-quiz` | Instructor | Generate and persist a quiz |
| `POST` | `/api/rag/generate-summary` | Enrolled | Generate a markdown summary |
| `POST` | `/api/rag/generate-flashcards` | Enrolled | Generate and persist flashcards |

Rate limited: students 10/hr, instructors 50/hr (configurable).

</details>

<details>
<summary><strong>Quizzes</strong></summary>

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/courses/:id/quizzes` | Enrolled | List quizzes (students see published only) |
| `GET` | `/api/quizzes/:id` | Enrolled | Quiz with all questions |
| `PUT` | `/api/quizzes/:id` | Instructor | Update quiz metadata |
| `DELETE` | `/api/quizzes/:id` | Instructor | Soft delete |
| `POST` | `/api/quizzes/:id/publish` | Instructor | Publish quiz |
| `POST` | `/api/quizzes/:id/attempt` | Enrolled | Submit answers, get graded results |

</details>

<details>
<summary><strong>Flashcards</strong></summary>

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/courses/:id/flashcard-sets` | Enrolled | List flashcard sets |
| `GET` | `/api/flashcard-sets/:id` | Enrolled | Set with all cards |
| `PUT` | `/api/flashcard-sets/:id/progress` | Enrolled | Update SM-2 spaced repetition progress |

</details>

<details>
<summary><strong>Canvas LMS</strong></summary>

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/courses/:id/canvas/connect` | Instructor | Connect to Canvas course |
| `GET` | `/api/courses/:id/canvas/files` | Instructor | List Canvas course files |
| `POST` | `/api/courses/:id/canvas/import` | Instructor | Import Canvas files into Meli |

</details>

<br/>

---

<br/>

## Project Structure

```
meli/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app + lifespan (worker startup)
│   │   ├── config.py            # pydantic-settings from .env
│   │   ├── database.py          # SQLAlchemy async engine
│   │   ├── api/                 # Route handlers
│   │   │   ├── deps.py          #   get_current_user, require_instructor
│   │   │   ├── rag.py           #   RAG query + generation endpoints
│   │   │   ├── courses.py       #   Course CRUD
│   │   │   ├── documents.py     #   Upload + file management
│   │   │   ├── quizzes.py       #   Quiz CRUD + attempts + grading
│   │   │   ├── flashcards.py    #   Flashcard sets + SM-2 progress
│   │   │   └── canvas.py        #   Canvas LMS integration
│   │   ├── models/              # SQLAlchemy 2.0 models
│   │   │   ├── base.py          #   UUID PK, timestamps, soft delete mixins
│   │   │   └── ...              #   user, course, document, chunk, quiz, flashcard, task
│   │   ├── schemas/             # Pydantic v2 request/response models
│   │   ├── services/            # Business logic
│   │   │   ├── pipeline.py      #   Orchestrates download → parse → chunk → embed → store
│   │   │   ├── worker.py        #   PostgreSQL task queue consumer
│   │   │   ├── parser.py        #   Docling + Whisper dispatch
│   │   │   ├── chunker.py       #   Sentence-aligned ~500-token chunks
│   │   │   ├── embedder.py      #   OpenAI text-embedding-3-large
│   │   │   ├── retriever.py     #   pgvector cosine similarity search
│   │   │   ├── generator.py     #   OpenRouter LLM with fallback strategy
│   │   │   ├── storage.py       #   Cloudflare R2 via boto3
│   │   │   └── auth.py          #   Clerk JWT verification + role detection
│   │   └── middleware/          # ASGI middleware
│   │       ├── auth.py          #   Early Bearer token gate
│   │       └── rate_limit.py    #   Per-user hourly limits on /api/rag/*
│   ├── alembic/                 # Database migrations (async)
│   ├── tests/                   # pytest + pytest-asyncio
│   ├── seed.py                  # Demo data seeder
│   ├── Dockerfile
│   ├── railway.toml
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── app/                 # Next.js 16 App Router
│   │   │   ├── dashboard/       #   Authenticated views (courses, quizzes, flashcards)
│   │   │   ├── sign-in/         #   Clerk sign-in
│   │   │   └── sign-up/         #   Clerk sign-up
│   │   ├── components/          # Feature-organized (course/, quiz/, flashcard/, documents/)
│   │   ├── hooks/               # useApiToken, useCourses, useQuizzes, useDocuments, etc.
│   │   ├── lib/api.ts           # Typed fetch wrapper with Clerk Bearer token
│   │   ├── proxy.ts             # Next.js 16 proxy (replaces middleware.ts)
│   │   └── styles/tokens.css    # Design tokens (oklch, "Honey & Salt" palette)
│   ├── e2e/                     # Playwright tests
│   └── package.json
│
├── docs/superpowers/            # Design specs + implementation plans
├── docker-compose.yml           # PostgreSQL 17 + pgvector local dev
└── .env.example                 # Environment variable template
```

<br/>

---

<br/>

## Design

Meli uses a **"Honey & Salt"** design system - warm amber primary tones paired with cool slate blue accents. All colors are defined as CSS custom properties in oklch color space in [`styles/tokens.css`](frontend/src/styles/tokens.css), along with a 4px spacing grid, semantic shadows, and motion tokens.

<br/>

---

<br/>

## Database

PostgreSQL 17 with pgvector extension. Key design decisions:

- **UUID primary keys** on all tables via `UUIDPrimaryKeyMixin`
- **Soft deletes** on courses, documents, quizzes, flashcard sets (`deleted_at` timestamp)
- **Timestamps** on all records via `TimestampMixin` (`created_at`, `updated_at`)
- **Task queue** backed by the `tasks` table with `FOR UPDATE SKIP LOCKED` claiming
- **Vector storage** in `chunks.embedding` column (1536-dim vectors, HNSW index)
- **Junction tables** for quiz-document and flashcard-document relationships (not UUID arrays)
- **SM-2 spaced repetition** state in `flashcard_progress` with per-user-per-card tracking

### Running migrations

```bash
cd backend

# Apply all pending migrations
alembic upgrade head

# Create a new migration after model changes
alembic revision --autogenerate -m "add new table"

# Rollback one step
alembic downgrade -1
```

<br/>

---

<br/>

## Auth & Authorization

Authentication is handled by **Clerk**. The frontend wraps the app in `<ClerkProvider>` and uses `proxy.ts` to protect routes. The backend verifies JWTs independently:

1. **Middleware** ([`middleware/auth.py`](backend/app/middleware/auth.py)) - cheap Bearer token presence check on `/api/*` paths
2. **Dependency** ([`api/deps.py`](backend/app/api/deps.py)) - full JWT signature verification via JWKS, user lookup/auto-creation
3. **Role detection** - email domain determines role: `ust.hk` = instructor, `connect.ust.hk` = student
4. **Enforcement** - `require_instructor` dependency blocks students from admin endpoints

<br/>

---

<br/>

## Roadmap

| Phase | Status | Features |
|-------|--------|----------|
| **1a** Foundation | Done | Auth, models, storage, migrations, Docling validation |
| **1b** RAG Pipeline | Done | Task queue, document processing, vector search, LLM generation |
| **1c** Frontend + Deploy | In Progress | Dashboard UI, deploy to Railway + Vercel |
| **2** Features | Planned | Pronunciation grading, live quiz WebSockets, hybrid search, gamification, i18n |

<br/>

---

<br/>

## License

This project is developed for HKUST's Center for Language Education.

<br/>
