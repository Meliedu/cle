# CLE Phase 1a — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Set up the full project foundation — backend scaffolding, database schema, auth middleware, R2 storage, and frontend scaffold — so Phase 1b can focus on the RAG pipeline.

**Architecture:** Monolith-first FastAPI backend with PostgreSQL 17 + pgvector on Railway, Next.js 15 frontend on Vercel, Clerk JWT auth, Cloudflare R2 file storage. PostgreSQL-backed task queue for async processing.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, asyncpg, pgvector, boto3, Clerk, Next.js 15, TypeScript, shadcn/ui, Tailwind CSS, TanStack Query, Docker Compose.

---

## File Structure

### Backend (`backend/`)

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI app, CORS, lifespan
│   ├── config.py                   # Pydantic BaseSettings
│   ├── database.py                 # async engine + session factory
│   ├── models/
│   │   ├── __init__.py             # re-export all models for Alembic
│   │   ├── base.py                 # DeclarativeBase + common mixins
│   │   ├── user.py
│   │   ├── course.py               # courses + enrollments
│   │   ├── document.py
│   │   ├── chunk.py
│   │   ├── quiz.py                 # quizzes + questions + quiz_documents + quiz_attempts
│   │   ├── flashcard.py            # flashcard_sets + flashcard_cards + flashcard_progress + flashcard_set_documents
│   │   ├── score.py                # pronunciation_scores + student_progress
│   │   ├── session.py              # session_summaries + live_sessions
│   │   ├── task.py                 # task queue
│   │   └── api_usage.py            # rate limit tracking
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── common.py               # APIResponse envelope, pagination
│   │   ├── user.py
│   │   ├── course.py
│   │   └── document.py
│   ├── api/
│   │   ├── __init__.py             # main router aggregating sub-routers
│   │   ├── deps.py                 # get_db, get_current_user dependencies
│   │   ├── auth.py                 # GET /auth/me
│   │   ├── courses.py              # course CRUD + enrollment
│   │   └── documents.py            # upload, list, delete
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth.py                 # Clerk JWT verification logic
│   │   ├── storage.py              # R2 upload/download/delete via boto3
│   │   └── worker.py               # task queue polling loop
│   └── middleware/
│       ├── __init__.py
│       ├── auth.py                 # JWT auth middleware
│       └── rate_limit.py           # per-user rate limiting
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── alembic.ini
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # fixtures: test DB, async client, test user
│   ├── test_config.py
│   ├── test_auth_service.py
│   ├── test_storage_service.py
│   ├── test_models.py
│   ├── test_api_auth.py
│   ├── test_api_courses.py
│   └── test_api_documents.py
├── requirements.txt
├── Dockerfile
├── railway.toml
└── seed.py                         # seed data script
```

### Frontend (`frontend/`)

```
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx              # ClerkProvider + TanStack QueryProvider
│   │   ├── page.tsx                # Landing page
│   │   ├── sign-in/[[...sign-in]]/page.tsx
│   │   ├── sign-up/[[...sign-up]]/page.tsx
│   │   └── dashboard/
│   │       ├── layout.tsx          # Sidebar + auth guard
│   │       └── page.tsx            # Dashboard home
│   ├── components/
│   │   ├── ui/                     # shadcn/ui (installed via CLI)
│   │   └── layout/
│   │       ├── sidebar.tsx
│   │       └── navbar.tsx
│   ├── lib/
│   │   ├── api.ts                  # fetch wrapper with Clerk token
│   │   └── utils.ts                # cn() helper
│   └── middleware.ts               # Clerk Next.js middleware
├── package.json
├── tailwind.config.ts
├── tsconfig.json
├── next.config.ts
├── postcss.config.mjs
└── .env.local.example
```

### Root

```
project-root/
├── backend/
├── frontend/
├── docs/
├── .env.example
├── docker-compose.yml
└── README.md
```

---

## Task 1: Backend Project Scaffolding

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/app/database.py`
- Create: `backend/app/main.py`
- Create: `backend/Dockerfile`
- Create: `backend/railway.toml`
- Create: `docker-compose.yml`
- Create: `.env.example`

- [ ] **Step 1: Create requirements.txt**

```
# Core
fastapi==0.115.12
uvicorn[standard]==0.34.2
python-dotenv==1.1.0
pydantic[email]==2.11.3
pydantic-settings==2.9.1

# Database
sqlalchemy[asyncio]==2.0.40
asyncpg==0.30.0
alembic==1.15.2
pgvector==0.3.6

# Auth
PyJWT==2.10.1
cryptography==44.0.3
httpx==0.28.1

# Storage
boto3==1.38.12

# AI — OpenRouter (OpenAI-compatible) + OpenAI for embeddings/Whisper
openai==1.82.0

# Document parsing (used in Phase 1b, declare now)
docling==2.31.0

# Testing
pytest==8.3.5
pytest-asyncio==0.26.0
httpx==0.28.1

# Utilities
python-multipart==0.0.20
```

- [ ] **Step 2: Create config.py**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/langassistant"

    # Clerk
    clerk_secret_key: str = ""
    clerk_jwks_url: str = "https://api.clerk.com/v1/jwks"

    # Cloudflare R2
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "langassistant-files"
    r2_endpoint_url: str = ""

    # OpenAI
    openai_api_key: str = ""

    # OpenRouter (LLM)
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_primary_model: str = "qwen/qwen3.6-plus:free"
    openrouter_fallback_model: str = "google/gemini-2.5-flash-lite"

    # App
    backend_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"
    allowed_email_domains: str = "connect.ust.hk,ust.hk"

    # Upload limits
    max_upload_size_mb: int = 100

    # Rate limits (per hour)
    student_rate_limit: int = 10
    instructor_rate_limit: int = 50

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
```

- [ ] **Step 3: Create database.py**

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
```

- [ ] **Step 4: Create main.py**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: future home of task worker
    yield
    # Shutdown


app = FastAPI(title="CLE API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
```

- [ ] **Step 5: Create docker-compose.yml**

```yaml
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

- [ ] **Step 6: Create .env.example**

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/langassistant

# Clerk
CLERK_SECRET_KEY=sk_test_...
CLERK_JWKS_URL=https://api.clerk.com/v1/jwks

# Cloudflare R2
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=langassistant-files
R2_ENDPOINT_URL=https://<account_id>.r2.cloudflarestorage.com

# OpenAI (Whisper + Embeddings)
OPENAI_API_KEY=sk-...

# OpenRouter (LLM)
OPENROUTER_API_KEY=
OPENROUTER_PRIMARY_MODEL=qwen/qwen3.6-plus:free
OPENROUTER_FALLBACK_MODEL=google/gemini-2.5-flash-lite

# App
BACKEND_URL=http://localhost:8000
FRONTEND_URL=http://localhost:3000
ALLOWED_EMAIL_DOMAINS=connect.ust.hk,ust.hk
MAX_UPLOAD_SIZE_MB=100
STUDENT_RATE_LIMIT=10
INSTRUCTOR_RATE_LIMIT=50
```

- [ ] **Step 7: Create Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 8: Create railway.toml**

```toml
[build]
builder = "DOCKERFILE"
dockerfilePath = "backend/Dockerfile"

[deploy]
startCommand = "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/health"
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3
```

- [ ] **Step 9: Create empty __init__.py files**

Create `backend/app/__init__.py` (empty).

- [ ] **Step 10: Verify — start Docker and FastAPI**

```bash
cd project-root && docker compose up -d
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload
# GET http://localhost:8000/health → {"status": "ok"}
```

- [ ] **Step 11: Commit**

```bash
git add backend/ docker-compose.yml .env.example
git commit -m "feat: backend scaffolding with FastAPI, config, database, docker-compose"
```

---

## Task 2: SQLAlchemy Models

**Files:**
- Create: `backend/app/models/base.py`
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/course.py`
- Create: `backend/app/models/document.py`
- Create: `backend/app/models/chunk.py`
- Create: `backend/app/models/quiz.py`
- Create: `backend/app/models/flashcard.py`
- Create: `backend/app/models/score.py`
- Create: `backend/app/models/session.py`
- Create: `backend/app/models/task.py`
- Create: `backend/app/models/api_usage.py`
- Create: `backend/app/models/__init__.py`

- [ ] **Step 1: Create base.py with common mixins**

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
```

- [ ] **Step 2: Create user.py**

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    clerk_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500))
```

- [ ] **Step 3: Create course.py (courses + enrollments)**

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Course(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "courses"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String)
    language: Mapped[str] = mapped_column(String(50), nullable=False)
    semester: Mapped[str | None] = mapped_column(String(20))
    instructor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    settings: Mapped[dict] = mapped_column(JSON, default=dict)

    instructor: Mapped["User"] = relationship("User", lazy="selectin")
    enrollments: Mapped[list["Enrollment"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class Enrollment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("course_id", "user_id"),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    course: Mapped["Course"] = relationship(back_populates="enrollments")
    user: Mapped["User"] = relationship("User", lazy="selectin")
```

- [ ] **Step 4: Create document.py**

```python
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Document(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "documents"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    r2_key: Mapped[str] = mapped_column(String(500), nullable=False)
    r2_url: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    page_count: Mapped[int | None] = mapped_column(Integer)
    word_count: Mapped[int | None] = mapped_column(Integer)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
```

- [ ] **Step 5: Create chunk.py**

```python
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class Chunk(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(String, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    token_count: Mapped[int | None] = mapped_column(Integer)
    embedding = mapped_column(Vector(1536))
    metadata_: Mapped[dict] = mapped_column("metadata", type_=String, default="{}")
    tsvector_content = mapped_column(TSVECTOR)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 6: Create quiz.py (quizzes + questions + quiz_documents + quiz_attempts)**

```python
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Quiz(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "quizzes"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String)
    quiz_type: Mapped[str] = mapped_column(String(20), default="practice")
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)

    questions: Mapped[list["Question"]] = relationship(
        back_populates="quiz", cascade="all, delete-orphan", order_by="Question.question_index"
    )
    source_documents: Mapped[list["QuizDocument"]] = relationship(
        cascade="all, delete-orphan"
    )


class Question(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "questions"

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False
    )
    question_index: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(30), default="multiple_choice")
    question_text: Mapped[str] = mapped_column(String, nullable=False)
    options: Mapped[dict | None] = mapped_column(JSON)
    correct_answer: Mapped[str] = mapped_column(String, nullable=False)
    explanation: Mapped[str | None] = mapped_column(String)
    source_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    quiz: Mapped["Quiz"] = relationship(back_populates="questions")


class QuizDocument(Base):
    __tablename__ = "quiz_documents"

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )


class QuizAttempt(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "quiz_attempts"

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    answers: Mapped[dict] = mapped_column(JSON, nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    total_questions: Mapped[int | None] = mapped_column(Integer)
    correct_count: Mapped[int | None] = mapped_column(Integer)
    time_taken_seconds: Mapped[int | None] = mapped_column(Integer)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 7: Create flashcard.py**

```python
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class FlashcardSet(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "flashcard_sets"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    cards: Mapped[list["FlashcardCard"]] = relationship(
        back_populates="flashcard_set", cascade="all, delete-orphan",
        order_by="FlashcardCard.card_index"
    )
    source_documents: Mapped[list["FlashcardSetDocument"]] = relationship(
        cascade="all, delete-orphan"
    )


class FlashcardCard(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "flashcard_cards"

    flashcard_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flashcard_sets.id", ondelete="CASCADE"), nullable=False
    )
    card_index: Mapped[int] = mapped_column(Integer, nullable=False)
    front: Mapped[str] = mapped_column(String, nullable=False)
    back: Mapped[str] = mapped_column(String, nullable=False)
    source_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    flashcard_set: Mapped["FlashcardSet"] = relationship(back_populates="cards")


class FlashcardSetDocument(Base):
    __tablename__ = "flashcard_set_documents"

    flashcard_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flashcard_sets.id", ondelete="CASCADE"),
        primary_key=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True
    )


class FlashcardProgress(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "flashcard_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "flashcard_card_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    flashcard_card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flashcard_cards.id", ondelete="CASCADE"),
        nullable=False
    )
    ease_factor: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("2.5"))
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    repetitions: Mapped[int] = mapped_column(Integer, default=0)
    next_review: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reviewed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

- [ ] **Step 8: Create score.py (pronunciation_scores + student_progress)**

```python
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class PronunciationScore(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "pronunciation_scores"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False
    )
    language: Mapped[str] = mapped_column(String(20), nullable=False)
    target_text: Mapped[str] = mapped_column(String, nullable=False)
    audio_r2_key: Mapped[str | None] = mapped_column(String(500))
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    accuracy_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    fluency_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    completeness_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    prosody_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    detailed_result: Mapped[dict | None] = mapped_column(JSON)
    grading_provider: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class StudentProgress(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "student_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False
    )
    xp_points: Mapped[int] = mapped_column(Integer, default=0)
    streak_days: Mapped[int] = mapped_column(Integer, default=0)
    last_activity_date: Mapped[date | None] = mapped_column(Date)
    quizzes_completed: Mapped[int] = mapped_column(Integer, default=0)
    flashcards_reviewed: Mapped[int] = mapped_column(Integer, default=0)
    speaking_sessions: Mapped[int] = mapped_column(Integer, default=0)
    badges: Mapped[dict] = mapped_column(JSON, default=list)
```

- [ ] **Step 9: Create session.py (session_summaries + live_sessions)**

```python
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class SessionSummary(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "session_summaries"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    generated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    summary_text: Mapped[str] = mapped_column(String, nullable=False)
    key_topics: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LiveSession(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "live_sessions"

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quizzes.id"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False
    )
    host_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="waiting")
    current_question_index: Mapped[int] = mapped_column(Integer, default=0)
    participant_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 10: Create task.py**

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class Task(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "tasks"

    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    error_message: Mapped[str | None] = mapped_column(String)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 11: Create api_usage.py**

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class ApiUsage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "api_usage"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    endpoint: Mapped[str] = mapped_column(String(100), nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 12: Create models/__init__.py**

```python
from app.models.api_usage import ApiUsage
from app.models.base import Base
from app.models.chunk import Chunk
from app.models.course import Course, Enrollment
from app.models.document import Document
from app.models.flashcard import FlashcardCard, FlashcardProgress, FlashcardSet, FlashcardSetDocument
from app.models.quiz import Question, Quiz, QuizAttempt, QuizDocument
from app.models.score import PronunciationScore, StudentProgress
from app.models.session import LiveSession, SessionSummary
from app.models.task import Task
from app.models.user import User

__all__ = [
    "Base",
    "User",
    "Course",
    "Enrollment",
    "Document",
    "Chunk",
    "Quiz",
    "Question",
    "QuizDocument",
    "QuizAttempt",
    "FlashcardSet",
    "FlashcardCard",
    "FlashcardSetDocument",
    "FlashcardProgress",
    "PronunciationScore",
    "StudentProgress",
    "SessionSummary",
    "LiveSession",
    "Task",
    "ApiUsage",
]
```

- [ ] **Step 13: Commit**

```bash
git add backend/app/models/
git commit -m "feat: add all SQLAlchemy models for CLE schema"
```

---

## Task 3: Alembic Migration

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/` (auto-generated)

- [ ] **Step 1: Initialize Alembic**

```bash
cd backend && alembic init alembic
```

- [ ] **Step 2: Edit alembic.ini — set sqlalchemy.url to empty (env.py will handle it)**

Set `sqlalchemy.url =` (empty string) in alembic.ini.

- [ ] **Step 3: Edit alembic/env.py for async + pgvector**

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import settings
from app.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Generate initial migration**

```bash
cd backend && alembic revision --autogenerate -m "initial schema"
```

- [ ] **Step 5: Edit the generated migration to add pgvector + pg_trgm extensions and indexes**

Add at the top of `upgrade()`:
```python
op.execute("CREATE EXTENSION IF NOT EXISTS vector")
op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
```

Add at the bottom of `upgrade()`:
```python
# HNSW index for vector similarity search
op.execute("""
    CREATE INDEX idx_chunks_embedding ON chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 200)
""")

# GIN index for full-text search
op.execute("CREATE INDEX idx_chunks_tsvector ON chunks USING GIN (tsvector_content)")

# Additional performance indexes
op.execute("CREATE INDEX idx_chunks_course_id ON chunks (course_id)")
op.execute("CREATE INDEX idx_enrollments_user_id ON enrollments (user_id)")
op.execute("CREATE INDEX idx_quiz_attempts_user_id ON quiz_attempts (user_id)")
op.execute("CREATE INDEX idx_documents_course_status ON documents (course_id, status)")
op.execute("CREATE INDEX idx_questions_quiz_id ON questions (quiz_id)")
op.execute("CREATE INDEX idx_flashcard_cards_set_id ON flashcard_cards (flashcard_set_id)")
op.execute("CREATE INDEX idx_tasks_poll ON tasks (status, created_at) WHERE status = 'pending'")
op.execute("CREATE INDEX idx_api_usage_rate_limit ON api_usage (user_id, endpoint, created_at)")
```

- [ ] **Step 6: Run migration**

```bash
cd backend && alembic upgrade head
```

- [ ] **Step 7: Verify tables exist**

```bash
docker exec -it $(docker ps -q -f ancestor=pgvector/pgvector:pg17) psql -U postgres -d langassistant -c "\dt"
```

Expected: all 17 tables listed.

- [ ] **Step 8: Commit**

```bash
git add backend/alembic/ backend/alembic.ini
git commit -m "feat: add Alembic config and initial migration with full schema"
```

---

## Task 4: Pydantic Schemas + API Response Envelope

**Files:**
- Create: `backend/app/schemas/__init__.py`
- Create: `backend/app/schemas/common.py`
- Create: `backend/app/schemas/user.py`
- Create: `backend/app/schemas/course.py`
- Create: `backend/app/schemas/document.py`

- [ ] **Step 1: Create common.py (API envelope)**

```python
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str


class APIResponse(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    error: ErrorDetail | None = None


class PaginationMeta(BaseModel):
    total: int
    page: int
    limit: int
    pages: int


class PaginatedResponse(BaseModel, Generic[T]):
    success: bool = True
    data: list[T]
    meta: PaginationMeta
```

- [ ] **Step 2: Create user.py schemas**

```python
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserResponse(BaseModel):
    id: uuid.UUID
    clerk_id: str
    email: EmailStr
    full_name: str | None
    role: str
    avatar_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 3: Create course.py schemas**

```python
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.user import UserResponse


class CourseCreate(BaseModel):
    name: str
    code: str | None = None
    description: str | None = None
    language: str
    semester: str | None = None
    settings: dict = {}


class CourseUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    description: str | None = None
    language: str | None = None
    semester: str | None = None
    settings: dict | None = None


class CourseResponse(BaseModel):
    id: uuid.UUID
    name: str
    code: str | None
    description: str | None
    language: str
    semester: str | None
    instructor_id: uuid.UUID
    settings: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EnrollmentCreate(BaseModel):
    user_email: str | None = None
    course_code: str | None = None


class EnrollmentResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    enrolled_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Create document.py schemas**

```python
import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    uploaded_by: uuid.UUID
    filename: str
    file_type: str
    file_size: int | None
    status: str
    page_count: int | None
    word_count: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 5: Create schemas/__init__.py**

```python
from app.schemas.common import APIResponse, ErrorDetail, PaginatedResponse, PaginationMeta
from app.schemas.course import CourseCreate, CourseResponse, CourseUpdate, EnrollmentCreate, EnrollmentResponse
from app.schemas.document import DocumentResponse
from app.schemas.user import UserResponse
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/
git commit -m "feat: add Pydantic schemas and API response envelope"
```

---

## Task 5: Auth Service (Clerk JWT Verification)

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/auth.py`
- Create: `backend/app/api/deps.py`
- Create: `backend/app/middleware/__init__.py`
- Create: `backend/app/middleware/auth.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_auth_service.py`

- [ ] **Step 1: Create auth.py service**

```python
import httpx
import jwt
from jwt import PyJWKClient

from app.config import settings

_jwks_client: PyJWKClient | None = None


def get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(settings.clerk_jwks_url)
    return _jwks_client


def verify_clerk_token(token: str) -> dict:
    """Verify a Clerk JWT and return the claims."""
    jwks_client = get_jwks_client()
    signing_key = jwks_client.get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        options={"verify_aud": False},
    )
    return claims


def detect_role_from_email(email: str) -> str:
    """Detect user role based on email domain."""
    domain = email.split("@")[-1].lower()
    allowed = settings.allowed_email_domains.split(",")
    if domain not in allowed:
        raise ValueError(f"Email domain {domain} not allowed")
    if domain == "connect.ust.hk":
        return "student"
    elif domain == "ust.hk":
        return "instructor"
    return "student"
```

- [ ] **Step 2: Create api/deps.py**

```python
import uuid

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.auth import detect_role_from_email, verify_clerk_token


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )

    token = auth_header.split(" ", 1)[1]

    try:
        claims = verify_clerk_token(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    clerk_id = claims.get("sub")
    email = claims.get("email", "")

    if not clerk_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
        )

    # Look up or create user
    result = await db.execute(select(User).where(User.clerk_id == clerk_id))
    user = result.scalar_one_or_none()

    if user is None:
        try:
            role = detect_role_from_email(email)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email domain not allowed",
            )

        user = User(
            clerk_id=clerk_id,
            email=email,
            full_name=claims.get("name"),
            role=role,
            avatar_url=claims.get("image_url"),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return user


async def require_instructor(user: User = Depends(get_current_user)) -> User:
    if user.role != "instructor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Instructor access required",
        )
    return user
```

- [ ] **Step 3: Create conftest.py for tests**

```python
import asyncio
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_db
from app.main import app
from app.models import Base
from app.models.user import User

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/langassistant_test"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
test_session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_session_factory() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_instructor(db_session: AsyncSession) -> User:
    user = User(
        clerk_id="clerk_instructor_001",
        email="instructor@ust.hk",
        full_name="Test Instructor",
        role="instructor",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_student(db_session: AsyncSession) -> User:
    user = User(
        clerk_id="clerk_student_001",
        email="student@connect.ust.hk",
        full_name="Test Student",
        role="student",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user
```

- [ ] **Step 4: Create test_auth_service.py**

```python
import pytest

from app.services.auth import detect_role_from_email


class TestDetectRoleFromEmail:
    def test_student_domain(self):
        assert detect_role_from_email("alice@connect.ust.hk") == "student"

    def test_instructor_domain(self):
        assert detect_role_from_email("prof@ust.hk") == "instructor"

    def test_disallowed_domain_raises(self):
        with pytest.raises(ValueError, match="not allowed"):
            detect_role_from_email("user@gmail.com")

    def test_case_insensitive(self):
        assert detect_role_from_email("Alice@CONNECT.UST.HK") == "student"
```

- [ ] **Step 5: Run tests**

```bash
cd backend && python -m pytest tests/test_auth_service.py -v
```

Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/ backend/app/api/deps.py backend/app/middleware/ backend/tests/
git commit -m "feat: add Clerk JWT auth service, deps, and role detection"
```

---

## Task 6: R2 Storage Service

**Files:**
- Create: `backend/app/services/storage.py`
- Create: `backend/tests/test_storage_service.py`

- [ ] **Step 1: Create storage.py**

```python
import uuid
from io import BytesIO

import boto3
from botocore.config import Config

from app.config import settings

_s3_client = None


def get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint_url,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )
    return _s3_client


def build_r2_key(course_id: uuid.UUID, document_id: uuid.UUID, filename: str) -> str:
    return f"courses/{course_id}/documents/{document_id}/{filename}"


def upload_file(r2_key: str, file_data: bytes, content_type: str) -> None:
    client = get_s3_client()
    client.put_object(
        Bucket=settings.r2_bucket_name,
        Key=r2_key,
        Body=file_data,
        ContentType=content_type,
    )


def download_file(r2_key: str) -> bytes:
    client = get_s3_client()
    response = client.get_object(Bucket=settings.r2_bucket_name, Key=r2_key)
    return response["Body"].read()


def delete_file(r2_key: str) -> None:
    client = get_s3_client()
    client.delete_object(Bucket=settings.r2_bucket_name, Key=r2_key)


def generate_presigned_url(r2_key: str, expiration: int = 3600) -> str:
    client = get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.r2_bucket_name, "Key": r2_key},
        ExpiresIn=expiration,
    )
```

- [ ] **Step 2: Create test_storage_service.py (unit tests with mocked S3)**

```python
import uuid
from unittest.mock import MagicMock, patch

from app.services.storage import build_r2_key, upload_file, download_file, delete_file


class TestBuildR2Key:
    def test_key_format(self):
        course_id = uuid.UUID("12345678-1234-1234-1234-123456789012")
        doc_id = uuid.UUID("abcdefab-abcd-abcd-abcd-abcdefabcdef")
        key = build_r2_key(course_id, doc_id, "lecture.pdf")
        assert key == "courses/12345678-1234-1234-1234-123456789012/documents/abcdefab-abcd-abcd-abcd-abcdefabcdef/lecture.pdf"


class TestUploadFile:
    @patch("app.services.storage.get_s3_client")
    def test_upload_calls_put_object(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        upload_file("test/key.pdf", b"content", "application/pdf")

        mock_client.put_object.assert_called_once()
        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs["Key"] == "test/key.pdf"
        assert call_kwargs["Body"] == b"content"
        assert call_kwargs["ContentType"] == "application/pdf"


class TestDownloadFile:
    @patch("app.services.storage.get_s3_client")
    def test_download_returns_bytes(self, mock_get_client):
        mock_client = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"file content"
        mock_client.get_object.return_value = {"Body": mock_body}
        mock_get_client.return_value = mock_client

        result = download_file("test/key.pdf")
        assert result == b"file content"


class TestDeleteFile:
    @patch("app.services.storage.get_s3_client")
    def test_delete_calls_delete_object(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        delete_file("test/key.pdf")

        mock_client.delete_object.assert_called_once()
```

- [ ] **Step 3: Run tests**

```bash
cd backend && python -m pytest tests/test_storage_service.py -v
```

Expected: 4 PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/storage.py backend/tests/test_storage_service.py
git commit -m "feat: add R2 storage service with upload, download, delete"
```

---

## Task 7: Course API Endpoints

**Files:**
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/auth.py`
- Create: `backend/app/api/courses.py`
- Modify: `backend/app/main.py` (register routers)
- Create: `backend/tests/test_api_courses.py`

- [ ] **Step 1: Create api/__init__.py (router aggregator)**

```python
from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.courses import router as courses_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(courses_router)
```

- [ ] **Step 2: Create api/auth.py**

```python
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.user import UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=APIResponse[UserResponse])
async def get_me(current_user: User = Depends(get_current_user)):
    return APIResponse(success=True, data=UserResponse.model_validate(current_user))
```

- [ ] **Step 3: Create api/courses.py**

```python
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_instructor
from app.models.course import Course, Enrollment
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.course import CourseCreate, CourseResponse, CourseUpdate

router = APIRouter(prefix="/courses", tags=["courses"])


@router.post("", response_model=APIResponse[CourseResponse], status_code=201)
async def create_course(
    body: CourseCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    course = Course(
        name=body.name,
        code=body.code,
        description=body.description,
        language=body.language,
        semester=body.semester,
        settings=body.settings,
        instructor_id=user.id,
    )
    db.add(course)

    # Auto-enroll instructor
    enrollment = Enrollment(course_id=course.id, user_id=user.id, role="instructor")
    db.add(enrollment)

    await db.commit()
    await db.refresh(course)
    return APIResponse(success=True, data=CourseResponse.model_validate(course))


@router.get("", response_model=APIResponse[list[CourseResponse]])
async def list_courses(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Course)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .where(Enrollment.user_id == user.id, Course.deleted_at.is_(None))
    )
    courses = result.scalars().all()
    return APIResponse(
        success=True,
        data=[CourseResponse.model_validate(c) for c in courses],
    )


@router.get("/{course_id}", response_model=APIResponse[CourseResponse])
async def get_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Verify enrollment
    enrollment = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == course_id, Enrollment.user_id == user.id
        )
    )
    if not enrollment.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.deleted_at.is_(None))
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    return APIResponse(success=True, data=CourseResponse.model_validate(course))


@router.put("/{course_id}", response_model=APIResponse[CourseResponse])
async def update_course(
    course_id: uuid.UUID,
    body: CourseUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(Course).where(
            Course.id == course_id,
            Course.instructor_id == user.id,
            Course.deleted_at.is_(None),
        )
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(course, field, value)

    await db.commit()
    await db.refresh(course)
    return APIResponse(success=True, data=CourseResponse.model_validate(course))


@router.delete("/{course_id}", response_model=APIResponse[None])
async def delete_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(Course).where(
            Course.id == course_id,
            Course.instructor_id == user.id,
            Course.deleted_at.is_(None),
        )
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    course.deleted_at = datetime.now()
    await db.commit()
    return APIResponse(success=True, data=None)


@router.post("/{course_id}/enroll", response_model=APIResponse[None], status_code=201)
async def enroll_in_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Verify course exists
    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.deleted_at.is_(None))
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    # Check if already enrolled
    existing = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == course_id, Enrollment.user_id == user.id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already enrolled")

    enrollment = Enrollment(course_id=course_id, user_id=user.id, role=user.role)
    db.add(enrollment)
    await db.commit()
    return APIResponse(success=True, data=None)
```

- [ ] **Step 4: Update main.py to include routers**

Add to main.py after CORS middleware:

```python
from app.api import api_router

app.include_router(api_router)
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/ backend/app/main.py
git commit -m "feat: add auth and course CRUD API endpoints"
```

---

## Task 8: Document Upload API

**Files:**
- Create: `backend/app/api/documents.py`
- Modify: `backend/app/api/__init__.py` (add documents router)

- [ ] **Step 1: Create api/documents.py**

```python
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_instructor
from app.config import settings
from app.models.course import Enrollment
from app.models.document import Document
from app.models.task import Task
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.document import DocumentResponse
from app.services.storage import build_r2_key, upload_file

router = APIRouter(prefix="/courses/{course_id}/documents", tags=["documents"])

ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "video/mp4": "mp4",
    "audio/mpeg": "mp3",
}


@router.post("/upload", response_model=APIResponse[DocumentResponse], status_code=201)
async def upload_document(
    course_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    # Verify user is instructor of this course
    result = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == course_id,
            Enrollment.user_id == user.id,
            Enrollment.role == "instructor",
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not course instructor")

    # Validate file type
    content_type = file.content_type or ""
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type {content_type} not allowed. Allowed: {', '.join(ALLOWED_TYPES.values())}",
        )

    # Read file
    file_data = await file.read()
    file_size = len(file_data)

    # Check size limit
    max_size = settings.max_upload_size_mb * 1024 * 1024
    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds {settings.max_upload_size_mb}MB limit",
        )

    # Create document record
    document_id = uuid.uuid4()
    r2_key = build_r2_key(course_id, document_id, file.filename or "unnamed")

    document = Document(
        id=document_id,
        course_id=course_id,
        uploaded_by=user.id,
        filename=file.filename or "unnamed",
        file_type=ALLOWED_TYPES[content_type],
        file_size=file_size,
        r2_key=r2_key,
        status="pending",
    )
    db.add(document)

    # Upload to R2
    upload_file(r2_key, file_data, content_type)

    # Create processing task
    task = Task(
        task_type="process_document",
        payload={"document_id": str(document_id)},
    )
    db.add(task)

    await db.commit()
    await db.refresh(document)

    return APIResponse(success=True, data=DocumentResponse.model_validate(document))


@router.get("", response_model=APIResponse[list[DocumentResponse]])
async def list_documents(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Verify enrollment
    enrollment = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == course_id, Enrollment.user_id == user.id
        )
    )
    if not enrollment.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enrolled")

    result = await db.execute(
        select(Document).where(
            Document.course_id == course_id, Document.deleted_at.is_(None)
        )
    )
    docs = result.scalars().all()
    return APIResponse(
        success=True,
        data=[DocumentResponse.model_validate(d) for d in docs],
    )


@router.delete("/{document_id}", response_model=APIResponse[None])
async def delete_document(
    course_id: uuid.UUID,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.course_id == course_id,
            Document.deleted_at.is_(None),
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    doc.deleted_at = datetime.now()
    await db.commit()
    return APIResponse(success=True, data=None)
```

- [ ] **Step 2: Update api/__init__.py**

```python
from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.courses import router as courses_router
from app.api.documents import router as documents_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(courses_router)
api_router.include_router(documents_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/
git commit -m "feat: add document upload, list, delete endpoints with R2 storage"
```

---

## Task 9: Task Queue Worker

**Files:**
- Create: `backend/app/services/worker.py`
- Modify: `backend/app/main.py` (start worker in lifespan)

- [ ] **Step 1: Create worker.py**

```python
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.task import Task

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5


async def claim_task(session: AsyncSession) -> Task | None:
    """Claim the oldest pending task using SELECT FOR UPDATE SKIP LOCKED."""
    result = await session.execute(
        select(Task)
        .where(Task.status == "pending", Task.attempts < Task.max_attempts)
        .order_by(Task.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    task = result.scalar_one_or_none()
    if task:
        task.status = "running"
        task.attempts += 1
        task.started_at = datetime.utcnow()
        await session.commit()
        await session.refresh(task)
    return task


async def complete_task(session: AsyncSession, task: Task) -> None:
    task.status = "completed"
    task.completed_at = datetime.utcnow()
    await session.commit()


async def fail_task(session: AsyncSession, task: Task, error: str) -> None:
    task.status = "failed" if task.attempts >= task.max_attempts else "pending"
    task.error_message = error
    await session.commit()


async def process_task(task: Task) -> None:
    """Dispatch task to the appropriate handler."""
    if task.task_type == "process_document":
        # Phase 1b: import and call document processing pipeline
        logger.info(f"Document processing task {task.id} — handler not yet implemented")
    else:
        raise ValueError(f"Unknown task type: {task.task_type}")


async def worker_loop(shutdown_event: asyncio.Event) -> None:
    """Main worker loop — polls for tasks and processes them."""
    logger.info("Task worker started")
    while not shutdown_event.is_set():
        try:
            async with async_session_factory() as session:
                task = await claim_task(session)
                if task:
                    logger.info(f"Processing task {task.id} (type={task.task_type}, attempt={task.attempts})")
                    try:
                        await process_task(task)
                        await complete_task(session, task)
                        logger.info(f"Task {task.id} completed")
                    except Exception as e:
                        logger.error(f"Task {task.id} failed: {e}")
                        await fail_task(session, task, str(e))
                else:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
        except Exception as e:
            logger.error(f"Worker error: {e}")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    logger.info("Task worker shutting down")
```

- [ ] **Step 2: Update main.py lifespan to start worker**

```python
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config import settings
from app.services.worker import worker_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    shutdown_event = asyncio.Event()
    worker_task = asyncio.create_task(worker_loop(shutdown_event))
    yield
    shutdown_event.set()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="CLE API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/worker.py backend/app/main.py
git commit -m "feat: add PostgreSQL-backed task queue worker with retry logic"
```

---

## Task 10: Frontend Scaffolding

**Files:**
- Create: `frontend/` (Next.js 15 project via create-next-app)
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/utils.ts`
- Create: `frontend/src/middleware.ts`
- Create: `frontend/src/app/layout.tsx`
- Create: `frontend/src/app/page.tsx`
- Create: `frontend/src/app/sign-in/[[...sign-in]]/page.tsx`
- Create: `frontend/src/app/sign-up/[[...sign-up]]/page.tsx`
- Create: `frontend/src/app/dashboard/layout.tsx`
- Create: `frontend/src/app/dashboard/page.tsx`
- Create: `frontend/.env.local.example`

- [ ] **Step 1: Initialize Next.js 15 project**

```bash
cd project-root && npx create-next-app@latest frontend \
  --typescript --tailwind --eslint --app --src-dir \
  --import-alias "@/*" --no-turbopack
```

- [ ] **Step 2: Install dependencies**

```bash
cd frontend && npm install @clerk/nextjs @tanstack/react-query
npx shadcn@latest init -d
```

- [ ] **Step 3: Create .env.local.example**

```env
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_API_URL=http://localhost:8000/api
```

- [ ] **Step 4: Create lib/api.ts**

```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export async function apiFetch<T>(
  path: string,
  options: RequestInit & { token?: string } = {}
): Promise<T> {
  const { token, ...fetchOptions } = options;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(fetchOptions.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...fetchOptions,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: { message: "Request failed" } }));
    throw new Error(error.error?.message || `HTTP ${response.status}`);
  }

  return response.json();
}
```

- [ ] **Step 5: Create middleware.ts (Clerk)**

```typescript
import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const isPublicRoute = createRouteMatcher(["/", "/sign-in(.*)", "/sign-up(.*)"]);

export default clerkMiddleware(async (auth, request) => {
  if (!isPublicRoute(request)) {
    await auth.protect();
  }
});

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
```

- [ ] **Step 6: Create root layout.tsx with ClerkProvider + TanStack Query**

```tsx
import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { Inter } from "next/font/google";
import "./globals.css";
import { QueryProvider } from "@/components/providers/query-provider";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "CLE - Language Learning Assistant",
  description: "AI-powered language learning for HKUST",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body className={inter.className}>
          <QueryProvider>{children}</QueryProvider>
        </body>
      </html>
    </ClerkProvider>
  );
}
```

- [ ] **Step 7: Create QueryProvider component**

Create `frontend/src/components/providers/query-provider.tsx`:

```tsx
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { staleTime: 60 * 1000 } },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}
```

- [ ] **Step 8: Create sign-in and sign-up pages**

`frontend/src/app/sign-in/[[...sign-in]]/page.tsx`:
```tsx
import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <SignIn />
    </div>
  );
}
```

`frontend/src/app/sign-up/[[...sign-up]]/page.tsx`:
```tsx
import { SignUp } from "@clerk/nextjs";

export default function SignUpPage() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <SignUp />
    </div>
  );
}
```

- [ ] **Step 9: Create dashboard layout + page**

`frontend/src/app/dashboard/layout.tsx`:
```tsx
import { UserButton } from "@clerk/nextjs";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b bg-white px-6 py-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">CLE</h1>
        <UserButton />
      </header>
      <main className="p-6">{children}</main>
    </div>
  );
}
```

`frontend/src/app/dashboard/page.tsx`:
```tsx
export default function DashboardPage() {
  return (
    <div>
      <h2 className="text-2xl font-bold">Dashboard</h2>
      <p className="mt-2 text-gray-600">Welcome to CLE. Select a course to get started.</p>
    </div>
  );
}
```

- [ ] **Step 10: Create landing page**

```tsx
import Link from "next/link";

export default function HomePage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center">
      <h1 className="text-4xl font-bold">CLE</h1>
      <p className="mt-4 text-lg text-gray-600">
        AI-powered language learning assistant for HKUST
      </p>
      <div className="mt-8 flex gap-4">
        <Link
          href="/sign-in"
          className="rounded-md bg-black px-6 py-3 text-white hover:bg-gray-800"
        >
          Sign In
        </Link>
        <Link
          href="/sign-up"
          className="rounded-md border border-gray-300 px-6 py-3 hover:bg-gray-50"
        >
          Sign Up
        </Link>
      </div>
    </div>
  );
}
```

- [ ] **Step 11: Commit**

```bash
git add frontend/
git commit -m "feat: scaffold Next.js 15 frontend with Clerk auth, TanStack Query, shadcn/ui"
```

---

## Task 11: Seed Data Script

**Files:**
- Create: `backend/seed.py`

- [ ] **Step 1: Create seed.py**

```python
"""Seed script for local development. Run: python -m seed"""
import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.course import Course, Enrollment
from app.models.user import User


async def seed():
    async with async_session_factory() as session:
        # Create instructor
        instructor = User(
            clerk_id="dev_instructor_001",
            email="dev_instructor@ust.hk",
            full_name="Dr. Demo Instructor",
            role="instructor",
        )
        session.add(instructor)

        # Create student
        student = User(
            clerk_id="dev_student_001",
            email="dev_student@connect.ust.hk",
            full_name="Demo Student",
            role="student",
        )
        session.add(student)
        await session.flush()

        # Create course
        course = Course(
            name="Introduction to Chinese",
            code="LANG1010",
            description="Beginner Mandarin Chinese for international students",
            language="chinese",
            semester="2026-fall",
            instructor_id=instructor.id,
        )
        session.add(course)
        await session.flush()

        # Enroll both
        session.add(Enrollment(course_id=course.id, user_id=instructor.id, role="instructor"))
        session.add(Enrollment(course_id=course.id, user_id=student.id, role="student"))

        await session.commit()
        print(f"Seeded: instructor={instructor.id}, student={student.id}, course={course.id}")


if __name__ == "__main__":
    asyncio.run(seed())
```

- [ ] **Step 2: Commit**

```bash
git add backend/seed.py
git commit -m "feat: add seed data script for local development"
```

---

## Task 12: Production-Quality UI/UX — Frontend Design System

> **REQUIRED SKILLS:** Invoke `ui-ux-pro-max:ui-ux-pro-max` and `frontend-design:frontend-design` before implementing frontend UI.

This task elevates the frontend from scaffold to enterprise/production-quality. All frontend pages from Task 10 and future tasks must meet these standards.

**Files:**
- Create: `frontend/src/styles/tokens.css` — design tokens (colors, spacing, typography, radii, shadows)
- Create: `frontend/src/components/layout/sidebar.tsx` — production sidebar with nav, active states, role-based menu
- Create: `frontend/src/components/layout/navbar.tsx` — top bar with breadcrumbs, user menu
- Modify: `frontend/src/app/layout.tsx` — apply design tokens, font pairing
- Modify: `frontend/src/app/page.tsx` — production landing page (not placeholder)
- Modify: `frontend/src/app/dashboard/layout.tsx` — production dashboard shell
- Modify: `frontend/src/app/dashboard/page.tsx` — production dashboard home with stats/empty states

**Design Direction:**
- **Style:** Clean, modern EdTech — not dark-luxury, not brutalist. Think Linear/Notion but warmer.
- **Palette:** Light mode primary. Neutral grays, one strong accent (blue or indigo), semantic colors for success/warning/error.
- **Typography:** Inter (already loaded) for body, consider a display font for headings.
- **Must have:** Intentional hierarchy, hover/focus/active states on all interactive elements, smooth transitions (150-300ms), responsive down to 375px, loading skeletons not spinners, empty states with illustrations or copy.

- [ ] **Step 1: Invoke `ui-ux-pro-max:ui-ux-pro-max` skill** — load design intelligence before any UI work

- [ ] **Step 2: Invoke `frontend-design:frontend-design` skill** — load frontend implementation patterns

- [ ] **Step 3: Define design tokens in `frontend/src/styles/tokens.css`**

CSS custom properties for:
- Color palette (surface, text, accent, semantic)
- Typography scale (clamp-based responsive sizes)
- Spacing scale (4px grid)
- Border radii
- Shadows (sm, md, lg)
- Transition durations and easings

- [ ] **Step 4: Build production sidebar component**

Requirements:
- Role-based navigation (instructor sees: Courses, Materials, Quizzes, Students, Settings; student sees: My Courses, Practice, Quizzes, Progress)
- Active state with accent indicator
- Collapsible on mobile (hamburger → slide-out)
- Smooth open/close animation
- Icons for each nav item (use lucide-react)
- Course selector dropdown if user has multiple courses

- [ ] **Step 5: Build production navbar component**

Requirements:
- Breadcrumb trail (Dashboard > Course Name > Materials)
- Search input (placeholder for Phase 1b)
- Notification bell (placeholder)
- UserButton from Clerk
- Responsive: hamburger trigger on mobile

- [ ] **Step 6: Build production landing page**

Requirements:
- Hero section with clear value proposition ("AI-powered language learning for HKUST")
- Feature highlights (3-4 cards: Upload Materials, AI Quizzes, Pronunciation Practice, Live Sessions)
- CTA: Sign In / Sign Up buttons
- Footer with minimal info
- Responsive, looks good on mobile
- No stock photos — use clean illustrations or abstract shapes

- [ ] **Step 7: Build production dashboard home**

Requirements:
- **Instructor view:** Course count stat card, recent uploads, upcoming quiz sessions, quick actions (Create Course, Upload Materials)
- **Student view:** Enrolled courses grid, study streak, recent quiz scores, next flashcard review date
- **Empty states:** When no courses/materials exist, show helpful copy + CTA ("Create your first course")
- Loading skeletons for all data-dependent sections

- [ ] **Step 8: Build course detail page**

`frontend/src/app/dashboard/courses/[courseId]/page.tsx`:
- Tab navigation: Overview | Materials | Quizzes | Students (instructor) or Overview | Practice | Quizzes (student)
- Overview: course info card, stats (materials count, quiz count, student count)
- Materials tab: file list with status badges (pending/processing/ready), upload zone (instructor only)
- Responsive card/list layout

- [ ] **Step 9: Build file upload component**

`frontend/src/components/documents/upload-zone.tsx`:
- Drag-and-drop zone with visual feedback (dashed border → solid on drag-over)
- File type validation (PDF, DOCX, PPTX, MP4, MP3) with clear error messages
- Progress bar during upload
- Document list below with status badges
- Delete confirmation dialog

- [ ] **Step 10: Verify all interactive elements have hover/focus/active states**

- [ ] **Step 11: Verify responsive layout at 375px, 768px, 1024px, 1440px**

- [ ] **Step 12: Commit**

```bash
git add frontend/
git commit -m "feat: production-quality UI with design system, dashboard, and course pages"
```

---

## Task 13: End-to-End QA Test

> **REQUIRED:** Run after all implementation is complete. Use Playwright via the `browse` or `qa` skill, or the Playwright MCP tools.

Full end-to-end verification of every user flow that Phase 1a delivers.

**Files:**
- Create: `frontend/e2e/auth.spec.ts`
- Create: `frontend/e2e/courses.spec.ts`
- Create: `frontend/e2e/documents.spec.ts`
- Create: `frontend/playwright.config.ts`

### QA Test Plan

#### Pre-requisites
- [ ] Docker compose running (PostgreSQL + pgvector)
- [ ] Backend running (`uvicorn app.main:app --reload`)
- [ ] Frontend running (`npm run dev`)
- [ ] `.env` files configured with real Clerk keys
- [ ] Database migrated (`alembic upgrade head`)
- [ ] Seed data loaded (`python -m seed`)

#### Flow 1: Health Check
- [ ] `GET /health` returns `{"status": "ok"}`
- [ ] Frontend loads at `http://localhost:3000` without errors
- [ ] No console errors in browser

#### Flow 2: Authentication — Instructor
- [ ] Navigate to `/sign-in`
- [ ] Clerk sign-in form renders
- [ ] Sign in with `@ust.hk` email → redirects to `/dashboard`
- [ ] `GET /api/auth/me` returns user with `role: "instructor"`
- [ ] UserButton shows in navbar with avatar/name
- [ ] Sign out → redirects to landing page
- [ ] Unauthenticated access to `/dashboard` → redirects to `/sign-in`

#### Flow 3: Authentication — Student
- [ ] Sign up with `@connect.ust.hk` email
- [ ] User created with `role: "student"`
- [ ] Dashboard shows student-specific navigation
- [ ] Cannot access instructor-only endpoints (403)

#### Flow 4: Authentication — Blocked Domain
- [ ] Attempt sign-up with `@gmail.com` → allowed by Clerk but...
- [ ] First API call returns 403 "Email domain not allowed"
- [ ] User cannot access any features

#### Flow 5: Course Management (Instructor)
- [ ] Click "Create Course" → form renders
- [ ] Fill in: Name, Code, Language, Semester → Submit
- [ ] Course appears in sidebar / course list
- [ ] Click into course → course detail page loads
- [ ] Edit course name → save → name updates
- [ ] Delete course → course disappears from list (soft delete)
- [ ] Student cannot create/edit/delete courses (403)

#### Flow 6: Course Enrollment (Student)
- [ ] Student sees "Join Course" option
- [ ] Enter course ID or code → enroll
- [ ] Course appears in student's course list
- [ ] Student can view course details
- [ ] Cannot re-enroll (409 Conflict)

#### Flow 7: Document Upload (Instructor)
- [ ] Navigate to course → Materials tab
- [ ] Drag PDF file onto upload zone → upload starts
- [ ] Progress indicator visible during upload
- [ ] After upload: document appears with "Pending" status badge
- [ ] (Background) Worker picks up task → status changes to "Processing" → "Ready"
- [ ] Upload invalid file type (e.g., .exe) → error message
- [ ] Upload oversized file (>100MB) → error message
- [ ] Delete document → disappears from list
- [ ] Student cannot upload (no upload zone visible / 403 on API)

#### Flow 8: Document Listing (Student)
- [ ] Student navigates to enrolled course → Materials tab
- [ ] Sees list of uploaded documents with status
- [ ] Cannot delete documents (no delete button / 403)

#### Flow 9: API Error Handling
- [ ] Invalid JWT → 401 response with error envelope
- [ ] Access non-enrolled course → 404
- [ ] Missing required fields → 400/422 with clear message
- [ ] All error responses use `{"success": false, "error": {"code": "...", "message": "..."}}` envelope

#### Flow 10: Responsive Layout
- [ ] Landing page renders correctly at 375px (mobile)
- [ ] Dashboard sidebar collapses to hamburger on mobile
- [ ] Course list uses single-column layout on mobile
- [ ] Upload zone is usable on tablet (768px)
- [ ] Full layout renders at 1440px

#### Flow 11: Task Worker
- [ ] Upload a document → verify task row created in `tasks` table
- [ ] Worker log shows "Processing task..." message
- [ ] Task completes or fails with proper status update
- [ ] Failed task retries up to `max_attempts` (3)

#### Flow 12: Database Integrity
- [ ] Verify all tables exist: `\dt` in psql
- [ ] Verify indexes exist: `\di` in psql
- [ ] pgvector extension enabled: `SELECT * FROM pg_extension WHERE extname = 'vector'`
- [ ] pg_trgm extension enabled: `SELECT * FROM pg_extension WHERE extname = 'pg_trgm'`
- [ ] Course deletion cascades enrollments
- [ ] Document soft delete preserves record

- [ ] **Final: Write QA report**

Save results to `docs/superpowers/qa/2026-04-05-phase1a-qa-report.md` with:
- PASS/FAIL per flow
- Screenshots of key screens
- Any bugs found + fix status
- Performance notes (page load times, API response times)
