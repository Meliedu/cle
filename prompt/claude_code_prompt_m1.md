# Claude Code Prompt — Milestone 1 Phase 1 (Late March → End-May)

Paste this entire prompt into Claude Code as your project initialization instruction.

---

## PROJECT CONTEXT

I'm building an AI-powered language learning assistant for university instructors and students. The platform supports a before/during/after class cycle: instructors upload course materials (PDF, DOCX, PPTX, video), the system uses RAG to generate quizzes, summaries, and flashcards, students practice pronunciation with AI grading, and instructors run live Kahoot-style quizzes during class.

This is Phase 1 (Planning & Alignment, Late March → End-May). The goal is to set up the full project foundation — infrastructure, database schema, auth, file upload pipeline, and the initial RAG ingestion pipeline — so that Phase 2 (June–July) can focus purely on feature development.

## TECH STACK (DO NOT DEVIATE)

### Infrastructure
- **Platform**: Railway (hosts FastAPI backend + PostgreSQL database + any other services)
- **Database**: PostgreSQL 17 + pgvector 0.8.0 extension (HNSW indexing for vector search)
- **File Storage**: Cloudflare R2 (S3-compatible, use boto3 with R2 endpoint)
- **Frontend Hosting**: Vercel
- **No Redis, no Celery** — use FastAPI BackgroundTasks for async work

### Backend
- **Framework**: FastAPI (Python 3.12+)
- **Async tasks**: FastAPI BackgroundTasks (NOT Celery)
- **WebSockets**: FastAPI native WebSocket support (for live quizzes)
- **ORM**: SQLAlchemy 2.0 with async support (asyncpg driver)
- **Migrations**: Alembic

### Frontend
- **Framework**: Next.js 14+ (App Router) with TypeScript
- **UI**: shadcn/ui + Tailwind CSS
- **State**: React hooks + SWR or TanStack Query for data fetching
- **Auth UI**: Clerk's pre-built `<SignIn/>`, `<SignUp/>`, `<UserButton/>` components

### Authentication
- **Service**: Clerk
- **Strategy**: Email allowlist — restrict sign-ups to `@connect.ust.hk` (students) and `@ust.hk` (instructors)
- **Role detection**: Based on email domain in FastAPI middleware
- **JWT verification**: Clerk JWT verified in FastAPI middleware on every API request
- **Free tier**: 50K MAU, handle domain restriction in FastAPI middleware (not Clerk's paid allowlist feature)

### RAG Pipeline
- **Orchestration**: LlamaIndex (Python)
- **Document Parsing**: Docling (PDF, DOCX, PPTX → structured text/markdown)
- **Video Transcription**: OpenAI Whisper API ($0.006/min) — for converting lecture videos to text
- **Embedding**: OpenAI text-embedding-3-large (1536 dims) or BGE-M3 self-hosted — start with OpenAI for simplicity
- **Vector Store**: pgvector in PostgreSQL (same database as app data)
- **Chunking**: 500–800 tokens with 100-token overlap, store metadata (source_file, page_number, course_id, instructor_id)
- **Hybrid Search**: pgvector cosine similarity + PostgreSQL tsvector full-text search (implement later in M2, design schema for it now)

### Speech & Language APIs (integrate in Phase 2, design interfaces now)
- **Chinese pronunciation grading + TTS**: iFlytek API (global.xfyun.cn)
- **English pronunciation grading + TTS + STT**: Azure Speech Services
- **Video transcription for RAG**: OpenAI Whisper API

### AI Generation
- **LLM**: Claude API (Anthropic) — use claude-sonnet-4-20250514 for quiz/summary/flashcard generation
- **SDK**: anthropic Python SDK

## PROJECT STRUCTURE

```
project-root/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app, CORS, lifespan
│   │   ├── config.py               # Environment variables, settings
│   │   ├── database.py             # SQLAlchemy async engine, session
│   │   ├── models/                 # SQLAlchemy ORM models
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── course.py
│   │   │   ├── document.py
│   │   │   ├── chunk.py
│   │   │   ├── quiz.py
│   │   │   ├── flashcard.py
│   │   │   └── score.py
│   │   ├── schemas/                # Pydantic request/response schemas
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── course.py
│   │   │   ├── document.py
│   │   │   ├── quiz.py
│   │   │   └── flashcard.py
│   │   ├── api/                    # API route handlers
│   │   │   ├── __init__.py
│   │   │   ├── auth.py             # Clerk JWT verification middleware
│   │   │   ├── courses.py
│   │   │   ├── documents.py        # Upload, list, delete materials
│   │   │   ├── rag.py              # Query, generate quiz/summary/flashcard
│   │   │   ├── quizzes.py          # CRUD + live quiz WebSocket
│   │   │   ├── flashcards.py
│   │   │   ├── scores.py
│   │   │   ├── speech.py           # Pronunciation grading interface (stub)
│   │   │   └── dashboard.py        # Instructor analytics endpoints
│   │   ├── services/               # Business logic
│   │   │   ├── __init__.py
│   │   │   ├── storage.py          # R2 upload/download via boto3
│   │   │   ├── parser.py           # Docling document parsing
│   │   │   ├── embedder.py         # Embedding generation (OpenAI or BGE-M3)
│   │   │   ├── rag.py              # LlamaIndex retrieval + generation
│   │   │   ├── quiz_generator.py   # Claude-powered quiz generation
│   │   │   ├── summary_generator.py
│   │   │   ├── flashcard_generator.py
│   │   │   ├── transcriber.py      # Whisper API for video→text
│   │   │   ├── speech_chinese.py   # iFlytek API client (stub)
│   │   │   └── speech_english.py   # Azure Speech client (stub)
│   │   └── utils/
│   │       ├── __init__.py
│   │       └── chunker.py          # Text chunking with overlap
│   ├── alembic/                    # Database migrations
│   │   ├── alembic.ini
│   │   ├── env.py
│   │   └── versions/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── railway.toml
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx          # Root layout with ClerkProvider
│   │   │   ├── page.tsx            # Landing/home page
│   │   │   ├── sign-in/[[...sign-in]]/page.tsx
│   │   │   ├── sign-up/[[...sign-up]]/page.tsx
│   │   │   ├── dashboard/          # Instructor dashboard
│   │   │   │   ├── page.tsx
│   │   │   │   ├── courses/
│   │   │   │   │   ├── page.tsx        # List courses
│   │   │   │   │   ├── [courseId]/
│   │   │   │   │   │   ├── page.tsx    # Course detail
│   │   │   │   │   │   ├── materials/page.tsx   # Upload & manage materials
│   │   │   │   │   │   ├── quizzes/page.tsx     # Quiz management
│   │   │   │   │   │   ├── students/page.tsx    # Student list & scores
│   │   │   │   │   │   └── live/page.tsx        # Live quiz session
│   │   │   ├── student/            # Student interface
│   │   │   │   ├── page.tsx
│   │   │   │   ├── courses/
│   │   │   │   │   ├── [courseId]/
│   │   │   │   │   │   ├── page.tsx         # Course overview
│   │   │   │   │   │   ├── practice/page.tsx    # Study materials + flashcards
│   │   │   │   │   │   ├── quiz/page.tsx        # Take quiz
│   │   │   │   │   │   └── speak/page.tsx       # Pronunciation practice
│   │   ├── components/
│   │   │   ├── ui/                 # shadcn/ui components
│   │   │   ├── layout/
│   │   │   │   ├── Navbar.tsx
│   │   │   │   └── Sidebar.tsx
│   │   │   ├── course/
│   │   │   ├── quiz/
│   │   │   ├── flashcard/
│   │   │   └── speech/
│   │   ├── lib/
│   │   │   ├── api.ts              # API client (fetch wrapper with Clerk token)
│   │   │   └── utils.ts
│   │   └── middleware.ts           # Clerk auth middleware for Next.js
│   ├── package.json
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   ├── next.config.js
│   └── vercel.json
├── .env.example
├── docker-compose.yml              # Local dev (Postgres + pgvector)
└── README.md
```

## DATABASE SCHEMA

Design and implement these tables. Use SQLAlchemy 2.0 ORM with async. Enable pgvector extension.

```sql
-- Enable extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- for text search

-- Users (synced from Clerk via webhook or on first API call)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clerk_id VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(20) NOT NULL CHECK (role IN ('instructor', 'student', 'admin')),
    avatar_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Courses
CREATE TABLE courses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50),                    -- e.g., "LANG1010"
    description TEXT,
    language VARCHAR(50) NOT NULL,       -- "chinese", "english", etc.
    semester VARCHAR(20),                -- e.g., "2026-fall"
    instructor_id UUID NOT NULL REFERENCES users(id),
    settings JSONB DEFAULT '{}',         -- course-specific RAG/quiz settings
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Course enrollments
CREATE TABLE enrollments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('instructor', 'student', 'ta')),
    enrolled_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(course_id, user_id)
);

-- Uploaded documents (files stored in R2)
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    uploaded_by UUID NOT NULL REFERENCES users(id),
    filename VARCHAR(500) NOT NULL,
    file_type VARCHAR(20) NOT NULL,      -- "pdf", "docx", "pptx", "mp4", "mp3"
    file_size BIGINT,
    r2_key VARCHAR(500) NOT NULL,        -- R2 object key
    r2_url TEXT,
    status VARCHAR(20) DEFAULT 'pending', -- "pending", "processing", "ready", "failed"
    page_count INTEGER,
    word_count INTEGER,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Document chunks (parsed + chunked text)
CREATE TABLE chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,        -- order within document
    page_number INTEGER,
    token_count INTEGER,
    embedding vector(1536),              -- OpenAI text-embedding-3-large dimension
    metadata JSONB DEFAULT '{}',         -- additional chunk metadata
    tsvector_content TSVECTOR,           -- for full-text search (hybrid search)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW index for vector similarity search
CREATE INDEX idx_chunks_embedding ON chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 200);

-- GIN index for full-text search
CREATE INDEX idx_chunks_tsvector ON chunks USING GIN (tsvector_content);

-- Index for course-scoped queries
CREATE INDEX idx_chunks_course_id ON chunks (course_id);

-- Quizzes
CREATE TABLE quizzes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES users(id),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    quiz_type VARCHAR(20) DEFAULT 'practice', -- "practice", "live", "homework"
    questions JSONB NOT NULL,            -- array of question objects
    settings JSONB DEFAULT '{}',         -- time limit, shuffle, etc.
    source_document_ids UUID[],          -- which documents were used to generate
    is_published BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Quiz question JSONB structure:
-- [
--   {
--     "id": "q1",
--     "type": "multiple_choice",
--     "question": "...",
--     "options": ["A", "B", "C", "D"],
--     "correct_answer": "B",
--     "explanation": "...",
--     "source_chunk_id": "uuid"
--   }
-- ]

-- Quiz attempts / scores
CREATE TABLE quiz_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quiz_id UUID NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    answers JSONB NOT NULL,              -- student's answers
    score DECIMAL(5,2),
    total_questions INTEGER,
    correct_count INTEGER,
    time_taken_seconds INTEGER,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Flashcard sets
CREATE TABLE flashcard_sets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES users(id),
    title VARCHAR(255) NOT NULL,
    cards JSONB NOT NULL,                -- array of {front, back, source_chunk_id}
    source_document_ids UUID[],
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Student flashcard progress (spaced repetition)
CREATE TABLE flashcard_progress (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    flashcard_set_id UUID NOT NULL REFERENCES flashcard_sets(id) ON DELETE CASCADE,
    card_index INTEGER NOT NULL,
    ease_factor DECIMAL(3,2) DEFAULT 2.5,
    interval_days INTEGER DEFAULT 0,
    repetitions INTEGER DEFAULT 0,
    next_review TIMESTAMPTZ,
    last_reviewed TIMESTAMPTZ,
    UNIQUE(user_id, flashcard_set_id, card_index)
);

-- Pronunciation scores
CREATE TABLE pronunciation_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    course_id UUID NOT NULL REFERENCES courses(id),
    language VARCHAR(20) NOT NULL,       -- "chinese" or "english"
    target_text TEXT NOT NULL,
    audio_r2_key VARCHAR(500),           -- stored audio in R2
    overall_score DECIMAL(5,2),
    accuracy_score DECIMAL(5,2),
    fluency_score DECIMAL(5,2),
    completeness_score DECIMAL(5,2),
    prosody_score DECIMAL(5,2),          -- English only (Azure)
    detailed_result JSONB,               -- full API response (word/phoneme level)
    grading_provider VARCHAR(20),        -- "iflytek" or "azure"
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Session summaries (generated after each class)
CREATE TABLE session_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    generated_by UUID REFERENCES users(id),
    session_date DATE NOT NULL,
    summary_text TEXT NOT NULL,
    key_topics JSONB,                    -- extracted topics
    source_document_ids UUID[],
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Live quiz sessions (WebSocket state tracking)
CREATE TABLE live_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quiz_id UUID NOT NULL REFERENCES quizzes(id),
    course_id UUID NOT NULL REFERENCES courses(id),
    host_id UUID NOT NULL REFERENCES users(id),  -- instructor
    status VARCHAR(20) DEFAULT 'waiting',  -- "waiting", "active", "question", "results", "ended"
    current_question_index INTEGER DEFAULT 0,
    participant_count INTEGER DEFAULT 0,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Gamification
CREATE TABLE student_progress (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    course_id UUID NOT NULL REFERENCES courses(id),
    xp_points INTEGER DEFAULT 0,
    streak_days INTEGER DEFAULT 0,
    last_activity_date DATE,
    quizzes_completed INTEGER DEFAULT 0,
    flashcards_reviewed INTEGER DEFAULT 0,
    speaking_sessions INTEGER DEFAULT 0,
    badges JSONB DEFAULT '[]',
    UNIQUE(user_id, course_id)
);
```

## WHAT TO BUILD NOW (Phase 1 — by end of May)

### 1. Project Scaffolding
- Initialize FastAPI backend with the full project structure above
- Initialize Next.js frontend with App Router, Tailwind, shadcn/ui
- Set up docker-compose.yml for local dev (PostgreSQL 17 + pgvector)
- Set up Alembic migrations with the full schema above
- Create .env.example with all required env vars
- Create Dockerfile for FastAPI (Railway deployment)
- Create railway.toml config

### 2. Database & Migrations
- Implement all SQLAlchemy models matching the schema above
- Create initial Alembic migration with full schema
- Ensure pgvector extension is enabled in migration
- Add seed data script for testing (sample course, sample user)

### 3. Authentication Flow
- Integrate Clerk with Next.js (ClerkProvider, middleware, sign-in/sign-up pages)
- Build FastAPI middleware that verifies Clerk JWT on every request
- Auto-create user record in Postgres on first authenticated API call (sync from Clerk)
- Detect role from email domain: `@connect.ust.hk` → student, `@ust.hk` → instructor
- Protect all API routes with auth middleware
- Build role-based access control (instructors can create courses, students can only access enrolled courses)

### 4. File Upload Pipeline
- Build R2 storage service (boto3 client with R2 endpoint)
- Build upload endpoint: POST /api/documents/upload (multipart form)
  - Accept PDF, DOCX, PPTX, MP4, MP3
  - Upload raw file to R2
  - Create document record in Postgres with status="pending"
  - Trigger BackgroundTask for processing
- Build document processing BackgroundTask:
  - For PDF/DOCX/PPTX: Parse with Docling → extract text → chunk → embed → store in pgvector
  - For MP4/MP3: Transcribe with Whisper API → chunk → embed → store in pgvector
  - Update document status to "ready" or "failed"
- Build list/delete endpoints for documents

### 5. RAG Ingestion Pipeline
- Build chunking service (500–800 tokens, 100-token overlap, preserve paragraph boundaries)
- Build embedding service (OpenAI text-embedding-3-large via API)
- Build pgvector storage: insert chunks with embeddings
- Build basic retrieval: given a query + course_id, find top-K similar chunks
- Build tsvector population (for future hybrid search)
- Test end-to-end: upload PDF → parse → chunk → embed → query → get relevant chunks

### 6. Basic Course Management
- CRUD endpoints for courses (instructor only)
- Enrollment endpoints (instructor adds students, or student self-enrolls with course code)
- Course-scoped document listing
- Course settings (language, quiz preferences)

### 7. Frontend Foundation
- Landing page with sign-in/sign-up
- Instructor dashboard layout (sidebar nav: Courses, Materials, Quizzes, Students)
- Student dashboard layout (sidebar nav: My Courses, Practice, Quizzes)
- Course creation form (instructor)
- Course detail page showing uploaded materials
- File upload UI with drag-and-drop (using shadcn/ui)
- Document processing status indicator (pending/processing/ready)

### 8. Initial RAG Query Endpoint
- POST /api/rag/query — takes a question + course_id, retrieves relevant chunks, returns them
- POST /api/rag/generate-quiz — takes a course_id + optional document_ids + topic, uses Claude to generate a quiz from retrieved chunks, saves to quizzes table
- POST /api/rag/generate-summary — takes a course_id + document_ids, generates a summary
- POST /api/rag/generate-flashcards — takes a course_id + document_ids, generates flashcard set

### 9. Stub Interfaces (for Phase 2)
- speech_chinese.py — iFlytek client class with placeholder methods (grade_pronunciation, text_to_speech, speech_to_text)
- speech_english.py — Azure Speech client class with placeholder methods
- WebSocket endpoint for live quizzes (basic connection handling, no game logic yet)

## ENVIRONMENT VARIABLES (.env.example)

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/langassistant

# Clerk
CLERK_SECRET_KEY=sk_test_...
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up

# Cloudflare R2
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=langassistant-files
R2_ENDPOINT_URL=https://<account_id>.r2.cloudflarestorage.com

# OpenAI (Whisper + Embeddings)
OPENAI_API_KEY=sk-...

# Anthropic (Claude)
ANTHROPIC_API_KEY=sk-ant-...

# iFlytek (Chinese speech — stub for now)
IFLYTEK_APP_ID=
IFLYTEK_API_KEY=
IFLYTEK_API_SECRET=

# Azure Speech (English speech — stub for now)
AZURE_SPEECH_KEY=
AZURE_SPEECH_REGION=eastasia

# App
BACKEND_URL=http://localhost:8000
FRONTEND_URL=http://localhost:3000
ALLOWED_EMAIL_DOMAINS=connect.ust.hk,ust.hk
```

## KEY IMPLEMENTATION DETAILS

### Clerk JWT Verification in FastAPI
```python
# Use PyJWKClient to fetch Clerk's JWKS and verify tokens
# Extract clerk_id, email from token claims
# Look up or create user in Postgres
# Attach user to request state
```

### R2 Storage with boto3
```python
import boto3

s3_client = boto3.client(
    's3',
    endpoint_url=settings.R2_ENDPOINT_URL,
    aws_access_key_id=settings.R2_ACCESS_KEY_ID,
    aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
    region_name='auto'
)
```

### Document Processing Background Task
```python
@router.post("/upload")
async def upload_document(
    file: UploadFile,
    course_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    # 1. Upload to R2
    # 2. Create document record (status=pending)
    # 3. Trigger background processing
    background_tasks.add_task(process_document, document_id)
    return {"document_id": document_id, "status": "pending"}

async def process_document(document_id: UUID):
    # 1. Download file from R2
    # 2. Parse with Docling (or Whisper for audio/video)
    # 3. Chunk text
    # 4. Generate embeddings
    # 5. Store chunks + embeddings in pgvector
    # 6. Update document status to "ready"
```

### pgvector Similarity Search
```python
# In SQLAlchemy, use the pgvector operators
from pgvector.sqlalchemy import Vector

# Query: find top 5 most similar chunks for a course
results = await session.execute(
    select(Chunk)
    .where(Chunk.course_id == course_id)
    .order_by(Chunk.embedding.cosine_distance(query_embedding))
    .limit(5)
)
```

### Claude Quiz Generation
```python
import anthropic

client = anthropic.Anthropic()

def generate_quiz(context_chunks: list[str], topic: str, num_questions: int = 5):
    context = "\n\n".join(context_chunks)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": f"""Based on the following course material, generate {num_questions} multiple-choice questions.

Course Material:
{context}

Topic focus: {topic}

Return a JSON array of questions with this structure:
[{{"question": "...", "options": ["A", "B", "C", "D"], "correct_answer": "B", "explanation": "..."}}]

Only return valid JSON, no other text."""
        }]
    )
    return json.loads(message.content[0].text)
```

## DOCKER-COMPOSE FOR LOCAL DEV

```yaml
version: '3.8'
services:
  db:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_DB: langassistant
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

## QUALITY REQUIREMENTS

- All API endpoints must have proper error handling and return consistent JSON error responses
- All database queries must be course-scoped (never leak data between courses)
- All endpoints must be protected by auth middleware (no unauthenticated access)
- Use async/await throughout the backend (asyncpg, async SQLAlchemy)
- Type hints on all Python functions
- TypeScript strict mode on frontend
- API responses should use Pydantic models for serialization

## DO NOT

- Do NOT use Redis or Celery
- Do NOT use Supabase, Neon, or any managed database service SDK
- Do NOT use LangChain (use LlamaIndex for RAG)
- Do NOT use Firebase or any Google auth
- Do NOT install packages without checking if they're needed
- Do NOT build the speech grading features yet (just create stub interfaces)
- Do NOT build the live quiz WebSocket game logic yet (just create the connection handler)
- Do NOT add unnecessary abstractions — keep it simple and direct

## START BY

1. Initialize the backend project with FastAPI + all dependencies
2. Set up docker-compose with pgvector
3. Create all SQLAlchemy models and run the first Alembic migration
4. Build the auth middleware (Clerk JWT verification)
5. Build the R2 storage service
6. Build the document upload → parse → chunk → embed → store pipeline
7. Build the basic RAG query endpoint
8. Initialize the frontend with Next.js + Clerk + shadcn/ui
9. Build the instructor dashboard with course management and file upload
10. Build the quiz/summary/flashcard generation endpoints
