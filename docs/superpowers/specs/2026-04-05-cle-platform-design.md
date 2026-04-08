# CLE Platform — Design Specification

**Date:** 2026-04-05
**Status:** Approved
**Author:** badur + Claude

---

## 1. Overview

CLE is an AI-powered language learning assistant for HKUST university instructors and students. It supports a before/during/after class cycle: instructors upload course materials, the system uses RAG to generate quizzes, summaries, and flashcards, students practice pronunciation with AI grading, and instructors run live Kahoot-style quizzes during class.

### 1.1 Key Decisions (Deviations from Original Prompt)

| Decision | Rationale |
|----------|-----------|
| Drop LlamaIndex — use direct pgvector + Anthropic SDK | Two function calls don't need an orchestration framework |
| PostgreSQL-backed task queue instead of FastAPI BackgroundTasks | Survives container restarts, retries, progress tracking |
| Normalize questions + flashcards into tables | Per-question analytics, safe reordering, proper relational queries |
| Junction tables instead of UUID[] arrays | Proper indexing and joins |
| Add soft deletes on key tables | University audit trail requirements |
| Per-user rate limits on AI endpoints | Cost protection against API abuse |
| English-first UI, i18n-ready structure | Design for Chinese UI later without rewrites |
| Next.js 15 (latest stable) | No reason to start on older version |
| Monolith-first architecture | Simplest for solo dev; splittable to worker later |
| Validate Docling for CJK early | Untested dependency risk for Chinese content |

## 2. Architecture

### 2.1 High-Level

```
[Next.js 15 on Vercel] <--HTTPS--> [FastAPI on Railway] <--asyncpg--> [PostgreSQL 17 + pgvector on Railway]
                                         |
                                    [Cloudflare R2]  (file storage)
                                         |
                                    [External APIs]
                                    - Anthropic Claude (quiz/summary/flashcard generation)
                                    - OpenAI (embeddings + Whisper transcription)
                                    - iFlytek (Chinese speech — Phase 2)
                                    - Azure Speech (English speech — Phase 2)
```

### 2.2 Monolith-First Design

Single FastAPI process on Railway handles both API requests and background task processing:

- **API layer:** HTTP endpoints + WebSocket for live quizzes
- **Task worker:** Async polling coroutine started in FastAPI lifespan, picks up pending tasks from PostgreSQL
- **Splittable:** Worker can become a separate Railway service by changing deploy config — same codebase, different entrypoint

### 2.3 Request Flow

```
Client → Clerk JWT in header → FastAPI auth middleware (verify JWT, resolve user) → Route handler → Service layer → Database/External APIs
```

### 2.4 Document Processing Flow

```
Upload request → Store file in R2 → Create document record (status=pending) → Insert task row (type=process_document)
                                                                                        ↓
Worker polls tasks table → Claims task (SELECT FOR UPDATE SKIP LOCKED) → Download from R2 → Parse (Docling/Whisper) → Chunk → Embed (OpenAI) → Store chunks+vectors in pgvector → Update document status=ready
```

## 3. Tech Stack

### Infrastructure
- **Platform:** Railway (FastAPI + PostgreSQL)
- **Database:** PostgreSQL 17 + pgvector 0.8.0 (HNSW indexing)
- **File Storage:** Cloudflare R2 (S3-compatible, boto3)
- **Frontend Hosting:** Vercel
- **Task Queue:** PostgreSQL-backed (no Redis/Celery)

### Backend
- **Framework:** FastAPI (Python 3.12+)
- **ORM:** SQLAlchemy 2.0 async (asyncpg driver)
- **Migrations:** Alembic
- **Auth:** Clerk JWT verification via PyJWKClient

### Frontend
- **Framework:** Next.js 16 (App Router) with TypeScript strict mode
- **UI:** shadcn/ui + Tailwind CSS
- **Data Fetching:** TanStack Query v5
- **Auth UI:** Clerk pre-built components
- **i18n-ready:** next-intl (English only initially, structure supports adding Chinese later)

### AI/ML
- **LLM:** OpenRouter API (OpenAI-compatible) — primary: `qwen/qwen3.6-plus:free`, fallback: `google/gemini-2.5-flash-lite`
- **Embeddings:** OpenAI text-embedding-3-large (1536 dims)
- **Vector Search:** pgvector cosine similarity
- **Document Parsing:** Docling (with PyMuPDF/python-docx/python-pptx fallback)
- **Video Transcription:** OpenAI Whisper API

## 4. Database Schema

### 4.1 Core Tables (unchanged from original)

- **users** — synced from Clerk (id, clerk_id, email, full_name, role, avatar_url, timestamps)
- **courses** — instructor-owned (id, name, code, description, language, semester, instructor_id, settings JSONB, timestamps)
- **enrollments** — course membership (course_id, user_id, role, enrolled_at, UNIQUE(course_id, user_id))
- **documents** — uploaded files (course_id, uploaded_by, filename, file_type, file_size, r2_key, status, page_count, word_count, metadata JSONB, timestamps). Add `deleted_at TIMESTAMPTZ`.
- **chunks** — parsed+embedded text (document_id, course_id, content, chunk_index, page_number, token_count, embedding vector(1536), metadata JSONB, tsvector_content, created_at)
- **quiz_attempts** — student quiz results (quiz_id, user_id, answers JSONB, score, total_questions, correct_count, time_taken_seconds, completed_at, created_at)
- **pronunciation_scores** — speech grading results (unchanged)
- **session_summaries** — generated class summaries (unchanged)
- **live_sessions** — WebSocket state tracking (unchanged)
- **student_progress** — gamification XP/streaks (unchanged)

### 4.2 Revised Tables

**quizzes** (soft deletable):
```sql
CREATE TABLE quizzes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES users(id),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    quiz_type VARCHAR(20) DEFAULT 'practice',
    settings JSONB DEFAULT '{}',
    is_published BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

**questions** (normalized from JSONB):
```sql
CREATE TABLE questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quiz_id UUID NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    question_index INTEGER NOT NULL,
    type VARCHAR(30) NOT NULL DEFAULT 'multiple_choice',
    question_text TEXT NOT NULL,
    options JSONB,
    correct_answer TEXT NOT NULL,
    explanation TEXT,
    source_chunk_id UUID REFERENCES chunks(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**flashcard_sets** (soft deletable):
```sql
CREATE TABLE flashcard_sets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES users(id),
    title VARCHAR(255) NOT NULL,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**flashcard_cards** (normalized):
```sql
CREATE TABLE flashcard_cards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flashcard_set_id UUID NOT NULL REFERENCES flashcard_sets(id) ON DELETE CASCADE,
    card_index INTEGER NOT NULL,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    source_chunk_id UUID REFERENCES chunks(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**flashcard_progress** (revised FK):
```sql
CREATE TABLE flashcard_progress (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    flashcard_card_id UUID NOT NULL REFERENCES flashcard_cards(id) ON DELETE CASCADE,
    ease_factor DECIMAL(3,2) DEFAULT 2.5,
    interval_days INTEGER DEFAULT 0,
    repetitions INTEGER DEFAULT 0,
    next_review TIMESTAMPTZ,
    last_reviewed TIMESTAMPTZ,
    UNIQUE(user_id, flashcard_card_id)
);
```

### 4.3 New Tables

**tasks** (PostgreSQL job queue):
```sql
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_type VARCHAR(50) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_tasks_poll ON tasks (status, created_at) WHERE status = 'pending';
```

**quiz_documents** (junction):
```sql
CREATE TABLE quiz_documents (
    quiz_id UUID NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    PRIMARY KEY (quiz_id, document_id)
);
```

**flashcard_set_documents** (junction):
```sql
CREATE TABLE flashcard_set_documents (
    flashcard_set_id UUID NOT NULL REFERENCES flashcard_sets(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    PRIMARY KEY (flashcard_set_id, document_id)
);
```

**canvas_integrations** (Canvas LMS connection per course):
```sql
CREATE TABLE canvas_integrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE UNIQUE,
    canvas_course_id VARCHAR(100) NOT NULL,
    canvas_base_url VARCHAR(500) NOT NULL,
    access_token_encrypted VARCHAR(500),
    last_sync_at TIMESTAMPTZ,
    sync_status VARCHAR(20) DEFAULT 'idle',
    sync_config JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

**api_usage** (rate limiting):
```sql
CREATE TABLE api_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    endpoint VARCHAR(100) NOT NULL,
    tokens_used INTEGER DEFAULT 0,
    model VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_api_usage_rate_limit ON api_usage (user_id, endpoint, created_at);
```

### 4.4 Additional Indexes

```sql
CREATE INDEX idx_enrollments_user_id ON enrollments (user_id);
CREATE INDEX idx_quiz_attempts_user_id ON quiz_attempts (user_id);
CREATE INDEX idx_documents_course_status ON documents (course_id, status);
CREATE INDEX idx_questions_quiz_id ON questions (quiz_id);
CREATE INDEX idx_flashcard_cards_set_id ON flashcard_cards (flashcard_set_id);
```

## 5. API Design

### 5.1 Auth Middleware

Every request:
1. Extract `Authorization: Bearer <clerk_jwt>` header
2. Verify JWT signature against Clerk JWKS endpoint (cached)
3. Extract `clerk_id` and `email` from claims
4. Look up user in PostgreSQL; auto-create on first call
5. Detect role from email domain: `@connect.ust.hk` → student, `@ust.hk` → instructor
6. Attach user to request state

### 5.2 Rate Limiting Middleware

For AI generation endpoints (`/api/rag/generate-*`):
- Check `api_usage` table: count requests in last hour
- Limits: students 10/hour, instructors 50/hour
- Return 429 with `Retry-After` header when exceeded

### 5.3 Endpoints

**Auth:**
- `GET /api/auth/me` — current user info

**Courses:**
- `POST /api/courses` — create course (instructor only)
- `GET /api/courses` — list user's courses
- `GET /api/courses/{id}` — course detail
- `PUT /api/courses/{id}` — update course (instructor only)
- `DELETE /api/courses/{id}` — soft delete (instructor only)
- `POST /api/courses/{id}/enroll` — enroll student
- `GET /api/courses/{id}/students` — list enrolled students

**Documents:**
- `POST /api/courses/{id}/documents/upload` — upload file (instructor only)
- `GET /api/courses/{id}/documents` — list documents
- `GET /api/documents/{id}` — document detail + processing status
- `DELETE /api/documents/{id}` — soft delete (instructor only)

**RAG:**
- `POST /api/rag/query` — retrieve relevant chunks for a question
- `POST /api/rag/generate-quiz` — generate quiz from course materials
- `POST /api/rag/generate-summary` — generate summary
- `POST /api/rag/generate-flashcards` — generate flashcard set

**Quizzes:**
- `GET /api/courses/{id}/quizzes` — list quizzes
- `GET /api/quizzes/{id}` — quiz detail with questions
- `PUT /api/quizzes/{id}` — update quiz (instructor only)
- `DELETE /api/quizzes/{id}` — soft delete
- `POST /api/quizzes/{id}/publish` — publish quiz
- `POST /api/quizzes/{id}/attempt` — submit quiz attempt (student)

**Flashcards:**
- `GET /api/courses/{id}/flashcard-sets` — list sets
- `GET /api/flashcard-sets/{id}` — set detail with cards
- `PUT /api/flashcard-sets/{id}/progress` — update spaced repetition progress

**Canvas LMS Integration:**
- `POST /api/courses/{id}/canvas/connect` — connect CLE course to a Canvas course (instructor only)
- `GET /api/courses/{id}/canvas/files` — list files in connected Canvas course
- `POST /api/courses/{id}/canvas/import` — import selected Canvas files into CLE (downloads → R2 → process)
- `GET /api/courses/{id}/canvas/status` — sync status

**Speech (stubs):**
- `POST /api/speech/grade` — stub for pronunciation grading
- `POST /api/speech/tts` — stub for text-to-speech

**Live Quiz (stub):**
- `WS /api/live/{session_id}` — WebSocket connection handler (basic connect/disconnect only)

## 6. Project Structure

```
project-root/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app, CORS, lifespan (starts worker)
│   │   ├── config.py               # Pydantic Settings
│   │   ├── database.py             # async engine + session factory
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── course.py
│   │   │   ├── document.py
│   │   │   ├── chunk.py
│   │   │   ├── quiz.py             # quizzes + questions
│   │   │   ├── flashcard.py        # flashcard_sets + flashcard_cards + flashcard_progress
│   │   │   ├── score.py            # pronunciation_scores + student_progress
│   │   │   ├── task.py             # task queue
│   │   │   └── api_usage.py        # rate limit tracking
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── course.py
│   │   │   ├── document.py
│   │   │   ├── quiz.py
│   │   │   └── flashcard.py
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── deps.py             # Dependency injection (get_current_user, get_db)
│   │   │   ├── courses.py
│   │   │   ├── documents.py
│   │   │   ├── rag.py
│   │   │   ├── quizzes.py
│   │   │   ├── flashcards.py
│   │   │   ├── speech.py           # stubs
│   │   │   └── live.py             # WebSocket stub
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py             # Clerk JWT verification
│   │   │   ├── storage.py          # R2 via boto3
│   │   │   ├── parser.py           # Docling (+ fallback)
│   │   │   ├── embedder.py         # OpenAI embeddings
│   │   │   ├── retriever.py        # pgvector search
│   │   │   ├── generator.py        # Claude quiz/summary/flashcard generation
│   │   │   ├── transcriber.py      # Whisper API
│   │   │   ├── chunker.py          # text chunking
│   │   │   └── worker.py           # task queue polling + dispatch
│   │   └── middleware/
│   │       ├── __init__.py
│   │       ├── auth.py             # JWT verification middleware
│   │       └── rate_limit.py       # per-user rate limiting
│   ├── alembic/
│   ├── tests/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── railway.toml
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx
│   │   │   ├── sign-in/[[...sign-in]]/page.tsx
│   │   │   ├── sign-up/[[...sign-up]]/page.tsx
│   │   │   ├── dashboard/          # instructor
│   │   │   └── student/            # student
│   │   ├── components/
│   │   ├── lib/
│   │   │   ├── api.ts              # fetch wrapper with Clerk token
│   │   │   └── utils.ts
│   │   └── middleware.ts           # Clerk Next.js middleware
│   ├── package.json
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── next.config.ts
├── docs/
├── .env.example
├── docker-compose.yml
└── README.md
```

## 7. Implementation Phases

### Phase 1a — Foundation (weeks 1-3)
- Project scaffolding (backend + frontend)
- Docker-compose with pgvector
- All SQLAlchemy models + Alembic migration
- Clerk auth integration (both ends)
- R2 storage service
- Docling CJK validation test

### Phase 1b — RAG Pipeline (weeks 4-6)
- PostgreSQL task queue + worker
- Document upload → parse → chunk → embed → store pipeline
- Basic retrieval (cosine similarity search)
- Claude-powered quiz/summary/flashcard generation
- Rate limiting middleware

### Phase 1c — Frontend + Deploy (weeks 7-8)
- Instructor dashboard (courses, materials, quiz management)
- Student dashboard (courses, practice, quizzes)
- File upload UI with progress
- Deploy to Railway + Vercel

### Phase 2 — Features (June-July)
- Pronunciation grading (iFlytek + Azure)
- Live quiz WebSocket game logic
- Hybrid search (tsvector + pgvector)
- Spaced repetition algorithm
- Gamification
- i18n (Traditional Chinese)

## 8. Error Handling

Consistent API error envelope:
```json
{
  "success": false,
  "error": {
    "code": "DOCUMENT_NOT_FOUND",
    "message": "Document not found or you don't have access"
  }
}
```

Success envelope:
```json
{
  "success": true,
  "data": { ... }
}
```

## 9. File Upload Constraints

- Max file size: 100MB (configurable)
- Allowed types: PDF, DOCX, PPTX, MP4, MP3
- File type validated by MIME type (not just extension)
- Files stored in R2 with key pattern: `courses/{course_id}/documents/{document_id}/{filename}`

## 10. Security

- All endpoints behind Clerk JWT auth (no unauthenticated access)
- All database queries course-scoped (never leak data between courses)
- Role-based access: instructors manage courses/materials, students access enrolled courses only
- File type + MIME validation on uploads
- Rate limiting on AI generation endpoints
- No hardcoded secrets (all via environment variables)
- CORS restricted to frontend origin
