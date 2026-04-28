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
  Practice with adaptive difficulty, live Kahoot-style quizzes, and pronunciation grading.<br/>
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
- **Curriculum spine** - structure a course into modules, schedule meetings, attach learning objectives (with Bloom's taxonomy levels), and publish assignments with due dates and weighted grading.
- **Syllabus parser** - upload a syllabus PDF/DOCX, the LLM extracts modules, meetings, objectives, and assignments into an editable JSON payload, then applies them in one transactional step.
- **Assignment grading** - per-student submission roster, score and feedback entry, automatic late-flagging for overdue submissions.
- **Generate quizzes** from uploaded materials with one click. Edit, publish, and track student attempts.
- **Generate flashcard sets** tied to specific documents or entire courses.
- **Host live quizzes** - Kahoot-style real-time sessions with join codes, speed-based scoring, and live leaderboards.
- **Analytics dashboard** - course overview, per-quiz performance, and per-student stats (XP, scores, activity).
- **Canvas LMS integration** - import files directly from connected Canvas courses.
- **Usage analytics** - per-student rate limiting protects against API cost overruns.

### For Students

- **Course calendar** - per-week view across all enrolled courses showing scheduled meetings and published assignment deadlines, sorted by time.
- **Assignment submissions** - draft → submit flow with status tracking (not started / in progress / submitted / late / graded / excused).
- **Practice quizzes** - take AI-generated quizzes with explanations for every answer.
- **Flashcards with SM-2** - spaced repetition algorithm schedules reviews at optimal intervals.
- **Adaptive revision** - infinite practice mode with a contextual bandit that adapts difficulty to your skill level in real time.
- **Pronunciation grading** - record yourself, get per-word accuracy scores via Azure Speech or iFlytek.
- **Live quizzes** - join instructor-hosted sessions with a code, compete for speed and accuracy.
- **Summaries** - get markdown summaries of any subset of course materials.
- **Gamification** - earn XP, maintain streaks, unlock badges, and climb the course leaderboard.
- **Enrollment-scoped** - students only see courses and materials they're enrolled in.

<br/>

---

<br/>

## Architecture

```
                                    +---------------------+
                                    |  Better Auth (JWT)   |
                                    |  + Resend (email)    |
                                    +----------+----------+
                                               | JWT (EdDSA, JWKS-verified)
                    +--------------------------+|+--------------------------+
                    |                          |||                          |
                    |   Next.js 16 (Vercel)    |||   FastAPI (Railway)      |
                    |                          +-+                          |
                    |   App Router + React 19  | |   Async Python 3.12     |
                    |   TanStack Query         | |                          |
                    |   Tailwind CSS 4         | |   +------------------+   |
                    |   shadcn/ui              | |   |  API Routers     |   |
                    |                          | |   |  auth, courses,  |   |
                    +--------------------------+ |   |  documents, rag, |   |
                                                 |   |  quizzes, flash, |   |
                                                 |   |  live, revision, |   |
                                                 |   |  speech, analytics|  |
                                                 |   |  progress        |   |
                                                 |   +--------+---------+   |
                                                 |            |             |
                                                 |   +--------v---------+   |
                                                 |   |  Service Layer   |   |
                                                 |   |                  |   |
                                                 |   |  parser embedder |   |
                                                 |   |  chunker retriev |   |
                                                 |   |  generator       |   |
                                                 |   |  bandit  speech  |   |
                                                 |   |  live_quiz gamif |   |
                                                 |   +--+----+----+-----+   |
                                                 |      |    |    |         |
                                                 |   +--v--+ | +--v------+  |
                                                 |   |Task | | |OpenAI   |  |
                                                 |   |Queue| | |Embedder |  |
                                                 |   +--+--+ | +---------+  |
                                                 |      |    |              |
                                                 +------+----+--------------+
                                                        |    |
                                              +---------v----v--------------+
                                              |  PostgreSQL 17              |
                                              |  + pgvector (HNSW)          |
                                              |  + tsvector (full-text)     |
                                              |                             |
                                              |  users, courses, docs,      |
                                              |  chunks, quizzes,           |
                                              |  flashcards, tasks,         |
                                              |  live_sessions, revision,   |
                                              |  bandit_models, progress,   |
                                              |  pronunciation_scores       |
                                              +-----------------------------+
                                                        |
                              +-------------------------+-------------------------+
                              |                         |                         |
                     +--------v--------+       +--------v--------+      +---------v-----------+
                     | Cloudflare R2   |       | OpenRouter       |      | Azure / iFlytek     |
                     | File Storage    |       | LLM Generation   |      | Speech Grading      |
                     +-----------------+       +------------------+      +---------------------+
                              |
                     +--------v--------+
                     | OpenAI Whisper  |
                     | Transcription   |
                     +-----------------+
```

### Monolith-first, splittable later

A single FastAPI process serves both HTTP requests and a background task worker. The worker runs as an asyncio task in the [lifespan context](backend/app/main.py), polling a PostgreSQL-backed job queue with `SELECT FOR UPDATE SKIP LOCKED`. When scale demands it, the worker can become a separate Railway service with the same codebase and a different entrypoint.

<br/>

---

<br/>

## Features

### RAG Pipeline

The document processing pipeline is the core of Meli. When an instructor uploads a file:

```
 Upload                Parse                 Chunk                  Embed                Store
+------+  R2 store   +------+  Markdown    +------+  ~500 tok    +------+  vector     +------+
| File | ----------> |Docling| ----------> |Chunker| ----------> |OpenAI| ----------> |pgvec |
|      |             |Whisper|             |       |  overlap     |      |  1536 dim   | tor  |
+------+             +------+             +------+              +------+             +------+
                         |                     |
                    PDF/DOCX/PPTX        Sentence-aligned
                    MP3/MP4              50-token overlap
```

| Stage | Service | Details |
|-------|---------|---------|
| **Parse** | [parser.py](backend/app/services/parser.py) | Docling for PDF/DOCX/PPTX with page-level extraction. Whisper for MP3/MP4. |
| **Chunk** | [chunker.py](backend/app/services/chunker.py) | Sentence-aligned splitting at ~500 tokens with 50-token overlap. Page numbers preserved. |
| **Embed** | [embedder.py](backend/app/services/embedder.py) | OpenAI `text-embedding-3-large` (1536 dims). Batched in groups of 100. |
| **Retrieve** | [retriever.py](backend/app/services/retriever.py) | Three modes: vector (pgvector cosine), full-text (tsvector + GIN), or hybrid (Reciprocal Rank Fusion). |
| **Generate** | [generator.py](backend/app/services/generator.py) | OpenRouter LLM with automatic fallback. Primary model tried first; on JSON parse failure, secondary model retried. |

### Hybrid Search

Retrieval supports three modes via the `mode` parameter:

| Mode | Method | Best for |
|------|--------|----------|
| `vector` | pgvector cosine similarity (`<=>`) | Semantic/conceptual queries |
| `fulltext` | PostgreSQL tsvector with GIN index | Exact keyword/phrase matching |
| `hybrid` | Reciprocal Rank Fusion (k=60) | Best of both — default for generation |

A database trigger auto-populates the `tsvector_content` column on chunk insert/update.

### Quizzes

- Instructors generate multiple-choice quizzes from selected documents via RAG
- Publish/unpublish controls student visibility
- Students submit attempts and receive instant grading with explanations
- Instructors can preview with answers, add questions manually, or regenerate individual questions

### Flashcards & Spaced Repetition (SM-2)

- Instructors generate flashcard sets from documents, with publish/unpublish control
- Students review cards and rate recall quality (0-5)
- SM-2 algorithm adjusts ease factor and schedules next review:
  - Quality < 3 resets the repetition counter
  - Intervals: 1 day, 6 days, then ease-factor-based multiplier
- Per-user, per-card progress tracked in `flashcard_progress`

### Adaptive Revision Mode (Contextual Bandit)

Infinite practice sessions where difficulty adapts to the student in real time using a **contextual bandit** trained with the REINFORCE policy gradient algorithm.

#### How it works

Each student gets their own per-(course, content_type) policy network stored in the database. On every answer, the system:

1. **Builds a state vector** (NumPy, 10 dimensions) from the student's attempt history
2. **Selects difficulty** by forward-passing the state through the policy (PyTorch)
3. **Serves an item** from a pre-generated pool at that difficulty
4. **Observes the reward** (score) and runs a single REINFORCE gradient step to update the policy

```
                        +------------------+
                        |  Attempt History  |
                        |  (last 50 rows)   |
                        +--------+---------+
                                 |
                        compute_state_vector()         (NumPy)
                                 |
                    +------------v-----------+
                    |  10-dim state vector    |
                    |                        |
                    |  [0-2] avg score/diff   |
                    |  [3-5] EMA score/diff   |
                    |  [6]   attempt count    |
                    |  [7]   correct streak   |
                    |  [8]   days since last  |
                    |  [9]   session progress |
                    +------------+-----------+
                                 |
                    select_difficulty()                 (PyTorch)
                                 |
                    +------------v-----------+
                    |  DifficultyPolicy MLP  |
                    |  Linear(10, 32) + ReLU  |
                    |  Linear(32, 3) + Softmax |
                    +------------+-----------+
                                 |
                        Categorical.sample()
                                 |
                     +-----------v----------+
                     |  easy / medium / hard |
                     +-----------+----------+
                                 |
                          serve item from pool
                                 |
                         student answers
                                 |
                    +------------v-----------+
                    |  update_policy()        |          (PyTorch)
                    |                        |
                    |  reward = score         |
                    |  advantage = (r - mu)   |
                    |       / sqrt(var)       |
                    |  loss = -log_prob * adv  |
                    |       - 0.01 * entropy  |
                    |  SGD step (lr=0.01)     |
                    |  grad clip (norm=1.0)   |
                    +------------------------+
                                 |
                    serialize weights -> DB
```

#### Policy network (PyTorch)

The `DifficultyPolicy` is a two-layer MLP (`nn.Module`) with Xavier-uniform initialization scaled to 0.01 so initial outputs are near-uniform across the three actions. Weights are serialized to bytes via `torch.save()` and stored in the `bandit_models.weights` column (`LargeBinary`). Each forward pass and gradient update deserializes, operates, and re-serializes — no GPU needed, the network is tiny (~400 parameters).

#### State vector (NumPy)

`compute_state_vector()` builds a 10-dimensional `np.ndarray` from the student's recent attempts:

| Index | Feature | Computation |
|-------|---------|-------------|
| 0-2 | Avg score per difficulty | Mean of last 50 attempts, grouped by easy/medium/hard |
| 3-5 | EMA score per difficulty | Exponentially weighted (decay=0.9) over last 20 attempts |
| 6 | Attempt volume | `min(total_attempts / 100, 1.0)` |
| 7 | Correct streak | Consecutive scores >= 0.8 from most recent, `/10` |
| 8 | Session gap | Days since last attempt, `/30` |
| 9 | Session progress | Current session item count, `/20` |

All features are normalized to [0, 1]. Defaults to 0.5 for score features when no data exists.

#### REINFORCE update

After each answer, `update_policy()` runs a single gradient step:

- **Reward**: raw score (0.0-1.0) from the answer
- **Baseline**: exponential moving average (decay=0.99) of past rewards, tracked per bandit model
- **Advantage**: `(reward - mean) / sqrt(variance)` — normalized to reduce gradient variance
- **Loss**: `-log_prob(chosen_action) * advantage - 0.01 * entropy` — entropy bonus prevents collapse to a single difficulty
- **Optimizer**: SGD with lr=0.01, gradient clipping at norm=1.0
- **Degeneracy guard**: if the last 5 selections are all the same difficulty, 50% uniform noise is mixed into the action probabilities

#### Cold start

Students with fewer than 20 attempts use `cold_start_select()` — a rule-based fallback:

- No history: start at **medium**
- Last score < 0.5: step **down** one level
- Two consecutive scores >= 0.8 at same level: step **up**
- Otherwise: **stay**

After 20 attempts, the `strategy` field transitions from `"rules"` to `"bandit"` and the policy network takes over.

#### Pool management

Items are pre-generated at easy/medium/hard difficulty via the background task worker. When unserved items for any difficulty drop below 5, a `revision_pool_replenish` task is enqueued (7 easy, 7 medium, 6 hard). The `revision_item_served` junction table ensures no student sees the same item twice.

### Curriculum, Calendar & Syllabus (Adaptive Engine — Phase 1)

The curriculum spine layers above the existing content + bandit + FSRS-5 stack. Six new tables (`course_modules`, `course_meetings`, `learning_objectives`, `assignments`, `assignment_submissions`, `syllabus_imports`) plus a `documents.kind` column scoping uploads to `lecture` / `syllabus` / `reading` / `reference` / `other`.

```
                Instructor flow                                Student flow

    +---------------+   parse_syllabus task    +-----------+
    |  Upload PDF   +--->  LLM JSON extract --->  Review   |          +-----------+
    |  kind=syllabus|                          |  payload  |          |  Calendar |
    +---------------+                          +-----+-----+          |   page    |
                                                     | apply          +-----+-----+
                                                     v                      |
    +-------------+   +---------+   +------------+   +-------------+   +----v----+
    |   modules   |<--+ meetings+-->| objectives |   | assignments +-->|  feed   |
    +-------------+   +---------+   +------------+   +------+------+   +---------+
                                                            | publish
                                                     +------v------+
                                                     | submissions |
                                                     | (per user)  |
                                                     +------+------+
                                                            | mark_overdue
                                                            | (24h cron)
                                                            v
                                                       'late' status
```

| Capability | Service / Endpoint |
|------------|-------------------|
| Module CRUD | `/api/courses/{id}/modules` ([modules.py](backend/app/api/modules.py)) |
| Meeting CRUD + calendar feed | `/api/courses/{id}/meetings`, `/api/courses/{id}/calendar` ([meetings.py](backend/app/api/meetings.py)) |
| Objective CRUD with Bloom levels | `/api/courses/{id}/objectives` ([objectives.py](backend/app/api/objectives.py)) |
| Assignments + submissions + grading | `/api/courses/{id}/assignments` ([assignments.py](backend/app/api/assignments.py)) |
| Syllabus parse + apply | `/api/courses/{id}/syllabus/imports` ([syllabus.py](backend/app/api/syllabus.py)) — LLM extraction in [services/syllabus.py](backend/app/services/syllabus.py) |
| Overdue cron (daily) | `mark_overdue_submissions` in [worker.py](backend/app/services/worker.py) — flips `not_started`/`in_progress` past `due_at` to `late` |

Permissions: instructors get full CRUD scoped to courses they own. Students get read access to the calendar, list-published-assignments, and write access to their own submissions only. Cross-course access is blocked by ownership checks at the dependency layer (`get_owned_course` in [deps.py](backend/app/api/deps.py)).

The syllabus parser is rate-limited (per-user hourly cap) to protect against unbounded LLM spend. Truncation beyond 40 000 characters is logged. Failed imports surface a "Re-trigger" affordance in the UI.

### Live Quiz (Kahoot-style)

Real-time multiplayer quizzes with WebSocket communication.

| Feature | Details |
|---------|---------|
| **Join codes** | 6-character alphanumeric codes for easy session joining |
| **State machine** | WAITING -> ACTIVE -> QUESTION -> ANSWER_REVEAL -> FINISHED |
| **Scoring** | Points = base * (1 - elapsed/time_limit) — faster answers earn more |
| **Real-time** | WebSocket broadcasts questions, answers, and leaderboard updates |
| **REST fallback** | Polling endpoints for clients that can't use WebSockets |
| **In-memory state** | No Redis required — `SessionState` lives in the FastAPI process |

### Pronunciation Grading

Dual-provider speech assessment with per-word accuracy.

| Provider | Language | Method |
|----------|----------|--------|
| **Azure Speech SDK** | English | Pronunciation Assessment API |
| **iFlytek** | Chinese | REST API with HMAC-SHA256 auth |

Returns normalized scores: overall, accuracy, fluency, completeness, prosody, plus word-level detail. History tracked per user per course.

### Gamification

| Feature | Details |
|---------|---------|
| **XP** | Quiz: score * 10, Flashcard review: 50, Pronunciation: 30 |
| **Streaks** | Consecutive days with any activity |
| **Badges** | `first_quiz`, `perfect_score`, `streak_7`, `streak_30`, `flashcard_master`, `speed_learner` |
| **Leaderboard** | Per-course XP ranking, paginated |
| **Progress card** | Dashboard widget showing XP, streak, and recent badges |

### Instructor Analytics

- **Course overview** - aggregate stats across all students
- **Quiz analytics** - attempt count, average score per quiz
- **Student stats** - per-student XP, quizzes completed, average score

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
| Auth | **Better Auth** JWT verification via PyJWKClient |
| Storage | **Cloudflare R2** (S3-compatible, boto3) |
| Vectors | **pgvector** HNSW cosine similarity |
| Full-text | **PostgreSQL** tsvector + GIN index |
| Parsing | **Docling** 2.31 (PDF/DOCX/PPTX) + **Whisper** (audio) |
| LLM | **OpenRouter** (OpenAI-compatible SDK) |
| Embeddings | **OpenAI** text-embedding-3-large |
| Speech | **Azure Speech SDK** + **iFlytek** |
| ML | **PyTorch** + **NumPy** (REINFORCE bandit policy) |
| Testing | **pytest** + pytest-asyncio |

### Frontend

| Layer | Technology |
|-------|-----------|
| Framework | **Next.js** 16 (App Router, Turbopack) |
| UI | **React** 19 + **TypeScript** strict |
| Components | **shadcn/ui** + **Tailwind CSS** 4 |
| Data fetching | **TanStack Query** v5 |
| Auth | **better-auth** 1.6 (self-hosted) |
| Icons | **Lucide React** |
| E2E testing | **Playwright** |

### Infrastructure

| Service | Provider |
|---------|----------|
| Database | **PostgreSQL 17 + pgvector** on Railway |
| Backend | **Railway** (Docker) |
| Frontend | **Vercel** |
| File storage | **Cloudflare R2** |
| Auth | **Better Auth** (self-hosted; tables in `auth` schema) |
| Email | **Resend** (verification + password reset) |

<br/>

---

<br/>

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker (for PostgreSQL)
- Resend account (for transactional email — verification, password reset)
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

### 5. Browse the database (DBeaver / TablePlus / any SQL client)

The Docker Postgres from step 2 is reachable from any SQL client on your laptop. Use this when you want to inspect the schema, query data directly, or debug migrations.

| Field    | Value           |
|----------|-----------------|
| Host     | `localhost`     |
| Port     | `5432`          |
| Database | `langassistant` |
| Username | `postgres`      |
| Password | `postgres`      |

No SSL needed (local). If the connection is empty, you haven't run `alembic upgrade head` yet — repeat step 3. If you want demo data, run `python seed.py`.

> Each teammate runs their own Docker instance — databases are isolated per laptop. To share data across the team, use the Railway-hosted Postgres below.

#### Browsing the shared Railway database (read-only)

For inspecting live production data without risk. Use the `meli_readonly` role — it can `SELECT` but not `INSERT`/`UPDATE`/`DELETE`/`ALTER`.

| Field    | Value                          |
|----------|--------------------------------|
| Host     | `hopper.proxy.rlwy.net`        |
| Port     | `21531`                        |
| Database | `railway`                      |
| Username | `meli_readonly`                |
| Password | `fYGwrSYxmhnTdC8r2YleWKdd`      |
| SSL      | `require`                      |

Or as a JDBC URL for DBeaver's "URL" mode:
```
jdbc:postgresql://hopper.proxy.rlwy.net:21531/railway?sslmode=require
```

#### Full-access role (read/write + DDL)

For migrations, schema tweaks, or data edits. Use `meli_admin` — full privileges on the `railway` database, bypasses RLS. **Not** a cluster superuser.

| Field    | Value                          |
|----------|--------------------------------|
| Host     | `hopper.proxy.rlwy.net`        |
| Port     | `21531`                        |
| Database | `railway`                      |
| Username | `meli_admin`                   |
| Password | `lycVPYQNDYQJCGLGvAZfAAky`      |
| SSL      | `require`                      |

> ⚠️ **Never share the `postgres` superuser password.** The backend connects as `meli_app` (NOBYPASSRLS, CRUD-only). Default to `meli_readonly`; use `meli_admin` only when you need to write or alter schema.

### 6. Testing

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
| `AZURE_SPEECH_KEY` | Azure Speech Services key (pronunciation grading) |
| `AZURE_SPEECH_REGION` | Azure Speech region |
| `IFLYTEK_APP_ID` | iFlytek app ID (Chinese pronunciation) |
| `IFLYTEK_API_KEY` | iFlytek API key |
| `IFLYTEK_API_SECRET` | iFlytek API secret |

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
| `POST` | `/api/rag/query` | Enrolled | Semantic search (vector, fulltext, or hybrid mode) |
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
| `GET` | `/api/quizzes/:id/preview` | Instructor | Preview quiz with answers |
| `PUT` | `/api/quizzes/:id` | Instructor | Update quiz metadata |
| `DELETE` | `/api/quizzes/:id` | Instructor | Soft delete |
| `POST` | `/api/quizzes/:id/publish` | Instructor | Toggle publish status |
| `POST` | `/api/quizzes/:id/questions` | Instructor | Add question to quiz |
| `DELETE` | `/api/questions/:id` | Instructor | Delete question and reindex |
| `POST` | `/api/questions/:id/regenerate` | Instructor | Regenerate single question via RAG |
| `POST` | `/api/quizzes/:id/attempt` | Enrolled | Submit answers, get graded results |

</details>

<details>
<summary><strong>Flashcards</strong></summary>

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/courses/:id/flashcard-sets` | Enrolled | List flashcard sets (students see published only) |
| `GET` | `/api/flashcard-sets/:id` | Enrolled | Set with all cards |
| `POST` | `/api/flashcard-sets/:id/publish` | Instructor | Toggle publish status |
| `DELETE` | `/api/flashcard-sets/:id` | Instructor | Soft delete set |
| `PUT` | `/api/flashcard-sets/:id/progress` | Enrolled | Update SM-2 spaced repetition progress |

</details>

<details>
<summary><strong>Revision Mode</strong></summary>

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/courses/:id/revision/start` | Student | Start adaptive revision session |
| `POST` | `/api/revision/sessions/:id/answer` | Student | Submit answer (triggers bandit update) |
| `POST` | `/api/revision/sessions/:id/next` | Student | Get next item at adapted difficulty |
| `GET` | `/api/revision/sessions/:id` | Student | Get session stats |
| `POST` | `/api/revision/sessions/:id/end` | Student | End session, return summary |

</details>

<details>
<summary><strong>Live Quiz</strong></summary>

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/courses/:id/live-sessions` | Instructor | Create live session from a quiz |
| `GET` | `/api/courses/:id/live-sessions` | Enrolled | List active sessions |
| `GET` | `/api/live-sessions/:id` | Enrolled | Get session detail |
| `GET` | `/api/live-sessions/:id/state` | Enrolled | Poll in-memory session state |
| `POST` | `/api/live-sessions/:id/next-question` | Instructor | Advance to next question |
| `POST` | `/api/live-sessions/:id/answer` | Student | Submit answer |
| `POST` | `/api/live-sessions/:id/end` | Instructor | End session |
| `WS` | `/api/live/:id` | Enrolled | WebSocket for real-time play |

</details>

<details>
<summary><strong>Pronunciation</strong></summary>

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/speech/grade` | Enrolled | Grade pronunciation (upload audio + reference text) |
| `GET` | `/api/courses/:id/pronunciation-history` | Enrolled | Past pronunciation scores |

</details>

<details>
<summary><strong>Progress & Gamification</strong></summary>

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/courses/:id/progress` | Enrolled | User's XP, streak, badges, activity counts |
| `GET` | `/api/courses/:id/leaderboard` | Enrolled | Paginated course leaderboard by XP |

</details>

<details>
<summary><strong>Analytics (Instructor)</strong></summary>

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/analytics/courses/:id/overview` | Instructor | Course-level aggregate stats |
| `GET` | `/api/analytics/courses/:id/quizzes` | Instructor | Per-quiz attempt count and average score |
| `GET` | `/api/analytics/courses/:id/students` | Instructor | Per-student XP, quizzes completed, avg score |

</details>

<details>
<summary><strong>Curriculum (Modules / Meetings / Objectives / Assignments)</strong></summary>

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` `GET` `PUT` `DELETE` | `/api/courses/:id/modules[/:moduleId]` | Instructor | Course module CRUD (flat list; soft delete) |
| `POST` `GET` `PUT` `DELETE` | `/api/courses/:id/meetings[/:meetingId]` | Instructor | Course meetings CRUD; unique `meeting_index` per course |
| `GET` | `/api/courses/:id/calendar?from_date=&to_date=` | Enrolled | Combined feed: meetings + published assignments in time range (max 366 days) |
| `POST` `GET` `PUT` `DELETE` | `/api/courses/:id/objectives[/:objectiveId]` | Instructor | Learning objectives with Bloom levels; mutually-exclusive module/meeting scope |
| `POST` `GET` `PUT` `DELETE` | `/api/courses/:id/assignments[/:assignmentId]` | Instructor (write) / Enrolled (read) | Assignments CRUD; students see only published |
| `POST` | `/api/courses/:id/assignments/:aid/submission` | Student | Upsert own submission (in_progress → submitted) |
| `GET` | `/api/courses/:id/assignments/:aid/submissions` | Instructor | Roster of all submissions for an assignment |
| `POST` | `/api/courses/:id/assignments/:aid/submissions/:sid/grade` | Instructor | Grade submission (score 0–9999.99, feedback, status) |

</details>

<details>
<summary><strong>Syllabus Parser</strong></summary>

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/courses/:id/syllabus/imports` | Instructor | Trigger LLM parse of a `kind=syllabus` document (rate-limited) |
| `GET` | `/api/courses/:id/syllabus/imports` | Instructor | List imports (statuses: pending → parsed → applied / failed / superseded) |
| `POST` | `/api/courses/:id/syllabus/imports/:iid/apply` | Instructor | Apply (possibly edited) parsed payload — creates modules/meetings/objectives/assignments transactionally |

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
│   │   │   ├── revision.py      #   Adaptive revision sessions
│   │   │   ├── live.py          #   Live quiz (WebSocket + REST)
│   │   │   ├── speech.py        #   Pronunciation grading
│   │   │   ├── analytics.py     #   Instructor analytics
│   │   │   ├── progress.py      #   Gamification (XP, badges, leaderboard)
│   │   │   └── canvas.py        #   Canvas LMS integration
│   │   ├── models/              # SQLAlchemy 2.0 models
│   │   │   ├── base.py          #   UUID PK, timestamps, soft delete mixins
│   │   │   ├── user.py          #   User, Course, Enrollment
│   │   │   ├── document.py      #   Document, Chunk (+ tsvector)
│   │   │   ├── quiz.py          #   Quiz, Question, QuizAttempt, QuizDocument
│   │   │   ├── flashcard.py     #   FlashcardSet, FlashcardCard, FlashcardProgress
│   │   │   ├── revision.py      #   RevisionSession, RevisionPoolItem, RevisionAttempt, BanditModel
│   │   │   ├── live.py          #   LiveSession, LiveAnswer
│   │   │   ├── gamification.py  #   StudentProgress, PronunciationScore
│   │   │   └── task.py          #   Task, ApiUsage, CanvasIntegration
│   │   ├── schemas/             # Pydantic v2 request/response models
│   │   ├── services/            # Business logic
│   │   │   ├── pipeline.py      #   Orchestrates download → parse → chunk → embed → store
│   │   │   ├── worker.py        #   PostgreSQL task queue consumer
│   │   │   ├── parser.py        #   Docling + Whisper dispatch
│   │   │   ├── chunker.py       #   Sentence-aligned ~500-token chunks
│   │   │   ├── embedder.py      #   OpenAI text-embedding-3-large
│   │   │   ├── retriever.py     #   Hybrid search (vector + fulltext + RRF)
│   │   │   ├── generator.py     #   OpenRouter LLM with fallback strategy
│   │   │   ├── bandit.py        #   REINFORCE contextual bandit for difficulty adaptation
│   │   │   ├── live_quiz.py     #   WebSocket manager + session state machine
│   │   │   ├── gamification.py  #   XP awards, streaks, badges, leaderboard
│   │   │   ├── speech.py        #   Azure Speech + iFlytek pronunciation grading
│   │   │   ├── storage.py       #   Cloudflare R2 via boto3
│   │   │   ├── auth.py          #   Clerk JWT verification + role detection
│   │   │   └── canvas.py        #   Canvas LMS client
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
│   │   │   ├── dashboard/       #   Authenticated views
│   │   │   │   ├── courses/     #     Course list + detail
│   │   │   │   │   └── [courseId]/
│   │   │   │   │       ├── quizzes/          # Quiz player
│   │   │   │   │       ├── flashcards/       # Flashcard player
│   │   │   │   │       ├── revision/         # Adaptive revision
│   │   │   │   │       ├── pronunciation/    # Speech grading
│   │   │   │   │       └── live/             # Live quiz host/join
│   │   │   ├── sign-in/         #   Clerk sign-in
│   │   │   └── sign-up/         #   Clerk sign-up
│   │   ├── components/          # Feature-organized
│   │   │   ├── course/          #   Create course dialog
│   │   │   ├── documents/       #   Upload zone, document selector
│   │   │   ├── quiz/            #   Player, list, preview, results, generate dialog
│   │   │   ├── flashcard/       #   Player, list, preview, generate dialog
│   │   │   ├── revision/        #   Player, quiz/flashcard items, stats bar, summary
│   │   │   ├── live-quiz/       #   Lobby, host panel, player view, podium
│   │   │   ├── pronunciation/   #   Recorder, score display, history chart
│   │   │   ├── gamification/    #   XP toast, badge display, leaderboard, progress card
│   │   │   ├── analytics/       #   Course analytics dashboard
│   │   │   ├── summary/         #   Generate summary dialog
│   │   │   ├── layout/          #   Navbar, sidebar, dashboard shell, language toggle
│   │   │   └── ui/              #   shadcn/ui primitives
│   │   ├── hooks/               # Custom hooks
│   │   │   ├── use-api-token.ts
│   │   │   ├── use-courses.ts
│   │   │   ├── use-quizzes.ts
│   │   │   ├── use-flashcard-sets.ts
│   │   │   ├── use-documents.ts
│   │   │   ├── use-revision.ts
│   │   │   ├── use-live-quiz.ts
│   │   │   ├── use-pronunciation.ts
│   │   │   ├── use-progress.ts
│   │   │   ├── use-analytics.ts
│   │   │   └── use-role.ts
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

PostgreSQL 17 with pgvector and tsvector extensions. Key design decisions:

- **UUID primary keys** on all tables via `UUIDPrimaryKeyMixin`
- **Soft deletes** on courses, documents, quizzes, flashcard sets (`deleted_at` timestamp)
- **Timestamps** on all records via `TimestampMixin` (`created_at`, `updated_at`)
- **Task queue** backed by the `tasks` table with `FOR UPDATE SKIP LOCKED` claiming
- **Vector storage** in `chunks.embedding` column (1536-dim vectors, HNSW index)
- **Full-text search** in `chunks.tsvector_content` column (GIN index, auto-populated trigger)
- **Junction tables** for quiz-document and flashcard-document relationships (not UUID arrays)
- **SM-2 + FSRS-5** spaced repetition state in `flashcard_progress`; per-user-per-course FSRS parameters in `scheduler_models`
- **Bandit models** serialized policy weights stored per (user, course, content_type)
- **Revision tracking** with session, pool, attempt, and served-item tables for adaptive difficulty
- **Difficulty recalibration** via `recalibration_stats` + `recalibration_models` (Dirichlet/HMM over LLM-labeled difficulty vs. observed outcomes)
- **Gamification** in `student_progress` (XP, streaks, badges JSONB, activity counts)
- **Live quiz** state in `live_sessions` and `live_answers` tables
- **Curriculum spine** in `course_modules`, `course_meetings`, `learning_objectives`, `assignments`, `assignment_submissions` (no soft-delete on submissions/imports — by design for audit trail)
- **Syllabus parser** state in `syllabus_imports` (pending → parsed → applied / failed / superseded); `documents.kind` column scopes uploads

### Schema Diagram

```
                                    +-------------+
                                    |    users    |
                                    |   (Clerk)   |
                                    +------+------+
                                           |
                    +----------------------+---------------------+
                    |                      |                     |
             +------v------+        +------v------+       +------v------+
             |   courses   |<-------+ enrollments |       | api_usage   |
             |  (soft del) |        +-------------+       +-------------+
             +--+---+---+--+
                |   |   |
      +---------+   |   +---------+------------+----------+---------+
      |             |             |            |          |         |
  +---v------+  +---v------+  +---v----+  +----v----+  +--v------+ +v----------+
  |documents |  |  quizzes |  |flashcrd|  |revision |  | live_   | |pronounc-  |
  |(soft del)|  |(soft del)|  |_sets   |  |_sessions|  |sessions | |iation_    |
  +--+-------+  +-+--------+  +--+-----+  +----+----+  +----+----+ |scores     |
     |            |              |             |            |      +-----------+
  +--v----+    +--v-------+   +--v------+  +---v-------+ +--v----+
  |chunks |    |questions |   |flashcrd |  |revision_  | |live_  |
  |pgvec+ |    +-+--------+   |_cards   |  |pool_items | |answers|
  |tsvect |    +-v--------+   +---+-----+  +----+------+ +-------+
  +-------+    |quiz_     |       |             |
               |documents |   +---v---------+   |
               +-+--------+   |flashcard_   |   +--->+-revision_attempts---+
               +-v--------+   |progress     |   +--->+-revision_item_served|
               |quiz_     |   |(SM-2+FSRS)  |   +--->+-bandit_models-------+
               |attempts  |   +-------------+   +--->+-recalibration_stats-+
               +----------+                     +--->+-recalibration_models+

              +---------+   +-------------+   +------------+   +------------------+
              |  tasks  |   |scheduler_   |   |canvas_     |   |session_summaries |
              |  queue  |   |models (FSRS)|   |integrations|   |(daily topics)    |
              +---------+   +-------------+   +------------+   +------------------+

              +------------------+
              |student_progress  |
              |(XP/streak/badges)|
              +------------------+
```

### Core Tables

<details>
<summary><strong>Identity & Enrollment</strong></summary>

| Table | Columns | Notes |
|-------|---------|-------|
| **users** | `id` (uuid PK), `clerk_id` (unique), `email` (unique), `full_name`, `role`, `avatar_url`, `created_at`, `updated_at` | Auto-created on first Clerk JWT. Role derived from email domain. |
| **courses** | `id`, `name`, `code`, `description`, `language`, `semester`, `instructor_id` (FK users), `settings` (JSON), timestamps, `deleted_at` | Soft delete. Settings stores per-course config. |
| **enrollments** | `id`, `course_id` (FK), `user_id` (FK), `role`, `enrolled_at` | Unique(`course_id`, `user_id`). Cascades on course/user delete. |

</details>

<details>
<summary><strong>Documents & RAG</strong></summary>

| Table | Columns | Notes |
|-------|---------|-------|
| **documents** | `id`, `course_id` (FK), `uploaded_by` (FK users), `filename`, `file_type`, `file_size` (bigint), `r2_key`, `r2_url`, `status`, `page_count`, `word_count`, `metadata` (JSON), timestamps, `deleted_at` | Status: `pending`, `processing`, `ready`, `failed`. |
| **chunks** | `id`, `document_id` (FK), `course_id` (FK), `content`, `chunk_index`, `page_number`, `token_count`, `embedding` (vector(1536)), `metadata` (JSON), `tsvector_content` (TSVECTOR), `created_at` | HNSW index on embedding, GIN index on tsvector (auto-populated via trigger). |

</details>

<details>
<summary><strong>Quizzes</strong></summary>

| Table | Columns | Notes |
|-------|---------|-------|
| **quizzes** | `id`, `course_id`, `created_by`, `title`, `description`, `quiz_type`, `settings` (JSON), `is_published`, timestamps, `deleted_at` | `is_published` gates student visibility. |
| **questions** | `id`, `quiz_id` (FK), `question_index`, `type`, `question_text`, `options` (JSON), `correct_answer`, `explanation`, `source_chunk_id` (FK chunks), `difficulty` (easy/medium/hard), `created_at` | Ordered by `question_index`. |
| **quiz_documents** | `quiz_id` (PK), `document_id` (PK) | Junction: source documents for generation. |
| **quiz_attempts** | `id`, `quiz_id`, `user_id`, `answers` (JSON), `score` (numeric(5,2)), `total_questions`, `correct_count`, `time_taken_seconds`, `completed_at`, `created_at` | One row per submitted attempt. |

</details>

<details>
<summary><strong>Flashcards + Spaced Repetition</strong></summary>

| Table | Columns | Notes |
|-------|---------|-------|
| **flashcard_sets** | `id`, `course_id`, `created_by`, `title`, `is_published`, timestamps, `deleted_at` | Mirrors quiz publish gating. |
| **flashcard_cards** | `id`, `flashcard_set_id` (FK), `card_index`, `front`, `back`, `source_chunk_id` (FK), `difficulty`, `created_at` | Ordered by `card_index`. |
| **flashcard_set_documents** | `flashcard_set_id` (PK), `document_id` (PK) | Source document junction. |
| **flashcard_progress** | `id`, `user_id`, `flashcard_card_id`, `ease_factor` (numeric(3,2)), `interval_days`, `repetitions`, `next_review`, `last_reviewed`, `stability` (float), `difficulty` (float), `last_grade`, `fsrs_review_count` (bigint) | Unique(`user_id`, `card_id`). SM-2 fields + FSRS-5 state columns. |
| **scheduler_models** | `id`, `user_id`, `course_id`, `parameters` (JSON, 19 FSRS-5 params), `strategy` (`sm2` / `fsrs`), `review_count` (bigint), timestamps | Unique(`user_id`, `course_id`). Transitions from SM-2 to FSRS-5 after threshold reviews. |

</details>

<details>
<summary><strong>Revision Mode + Contextual Bandit</strong></summary>

| Table | Columns | Notes |
|-------|---------|-------|
| **revision_sessions** | `id`, `user_id`, `course_id`, `content_type` (quiz/flashcard/speaking), `started_at`, `ended_at`, `items_answered`, `total_score` (numeric(7,2)) | Open session has `ended_at IS NULL`. |
| **revision_pool_items** | `id`, `course_id`, `content_type`, `difficulty`, quiz fields (`question_text`, `options`, `correct_answer`, `explanation`), flashcard fields (`front`, `back`), speaking fields (`target_text`, `language`), `source_chunk_id`, `recalibrated_difficulty`, `recalibration_confidence`, `instructor_override`, `created_at` | Unified pool table for all three content types with nullable type-specific columns. |
| **revision_attempts** | `id`, `user_id`, `course_id`, `session_id` (FK), `pool_item_id` (FK), `content_type`, `difficulty`, `score` (numeric(3,2)), `time_taken_ms`, `created_at`, `corrected_difficulty` | Training signal for bandit + recalibration. |
| **revision_item_served** | `user_id` (PK), `pool_item_id` (PK), `served_at` | Dedup: no student sees the same item twice. |
| **bandit_models** | `id`, `user_id`, `course_id`, `content_type`, `weights` (LargeBinary, torch.save blob), `strategy` (`rules`/`bandit`), `reward_mean`, `reward_var`, `attempt_count`, `updated_at` | Unique(`user_id`, `course_id`, `content_type`). Strategy auto-flips after cold-start. |
| **recalibration_stats** | `id`, `pool_item_id` (unique), `course_id`, `content_type`, `llm_difficulty`, `attempt_count`, `correct_count`, `hard_count`, `score_sum` (numeric(10,2)), `score_sq_sum` (numeric(12,4)) | Per-item observed-difficulty statistics. |
| **recalibration_models** | `id`, `course_id`, `content_type`, `dirichlet_params` (JSONB), `transition_matrix` (JSONB), `items_used`, `total_attempts_since_last_run`, `updated_at` | Unique(`course_id`, `content_type`). Bayesian model to correct LLM difficulty labels from real attempt data. |

</details>

<details>
<summary><strong>Live Quiz</strong></summary>

| Table | Columns | Notes |
|-------|---------|-------|
| **live_sessions** | `id`, `quiz_id`, `course_id`, `host_id`, `join_code` (6-char unique), `status` (waiting/active/question/reveal/finished), `current_question_index`, `participant_count`, `time_limit_seconds`, `settings` (JSONB), `started_at`, `ended_at`, `created_at` | In-memory state (WebSocket) is the source of truth during play; DB is snapshot. |
| **live_answers** | `id`, `session_id` (FK cascade), `user_id`, `question_index`, `answer`, `answered_at`, `points_earned` | Unique(`session_id`, `user_id`, `question_index`). |
| **session_summaries** | `id`, `course_id`, `generated_by`, `session_date`, `summary_text`, `key_topics` (JSON), `created_at` | Optional daily-session summary artifacts. |

</details>

<details>
<summary><strong>Gamification & Pronunciation</strong></summary>

| Table | Columns | Notes |
|-------|---------|-------|
| **student_progress** | `id`, `user_id`, `course_id`, `xp_points`, `streak_days`, `last_activity_date` (date), `quizzes_completed`, `flashcards_reviewed`, `speaking_sessions`, `badges` (JSON list) | Unique(`user_id`, `course_id`). Updated transactionally on every activity. |
| **pronunciation_scores** | `id`, `user_id`, `course_id`, `language`, `target_text`, `audio_r2_key`, `overall_score` (numeric(5,2)), `accuracy_score`, `fluency_score`, `completeness_score`, `prosody_score`, `detailed_result` (JSON), `grading_provider` (azure/iflytek), `created_at` | Full Azure/iFlytek JSON result retained for rendering word-level heatmaps. |

</details>

<details>
<summary><strong>Infrastructure</strong></summary>

| Table | Columns | Notes |
|-------|---------|-------|
| **tasks** | `id`, `task_type`, `payload` (JSON), `status` (pending/running/completed/failed), `attempts`, `max_attempts`, `error_message`, `started_at`, `completed_at`, `created_at` | Consumed by worker via `SELECT FOR UPDATE SKIP LOCKED`. Task types: `process_document`, `revision_pool_replenish`. |
| **api_usage** | `id`, `user_id`, `endpoint`, `tokens_used`, `model`, `created_at` | Backs per-user hourly rate limiting on `/api/rag/*`. |
| **canvas_integrations** | `id`, `course_id` (unique FK), `canvas_course_id`, `canvas_base_url`, `access_token_encrypted`, `last_sync_at`, `sync_status`, `sync_config` (JSON), timestamps | One connection per Meli course. |

</details>

### Indexes

| Index | Table | Type | Purpose |
|-------|-------|------|---------|
| `chunks_embedding_hnsw_idx` | `chunks.embedding` | HNSW (vector_cosine_ops) | Semantic search |
| `chunks_tsvector_gin_idx` | `chunks.tsvector_content` | GIN | Full-text search |
| `chunks_tsvector_trigger` | `chunks` | BEFORE INSERT/UPDATE | Auto-populate `tsvector_content` from `content` |
| Unique constraints | `enrollments`, `flashcard_progress`, `bandit_models`, `scheduler_models`, `recalibration_stats`, `recalibration_models`, `student_progress`, `live_answers` | BTREE | Enforce per-entity uniqueness |

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
| **1c** Frontend + Deploy | Done | Dashboard UI, quiz player, flashcard player, deploy to Railway + Vercel |
| **2a** Hybrid Search | Done | tsvector + GIN index, full-text retrieval, Reciprocal Rank Fusion |
| **2b** Gamification | Done | XP system, streaks, badges, course leaderboard, progress tracking |
| **2c** Pronunciation Grading | Done | Azure Speech (English), iFlytek (Chinese), per-word scoring, history |
| **2d** Live Quiz | Done | WebSocket real-time play, join codes, speed scoring, lobby + podium UI |
| **2e** Difficulty Adapter | Done | REINFORCE contextual bandit, adaptive revision sessions, pool management |
| **2f** Analytics | Done | Instructor dashboard: course overview, quiz stats, student stats |
| **2g** Flashcard Publishing | Done | Publish/unpublish control for flashcard sets (mirrors quizzes) |
| **3a** Adaptive Engine — Phase 1 | Done | Curriculum spine (modules / meetings / objectives / assignments), per-week calendar feed, scoped syllabus parser with LLM extraction + transactional applier, daily `mark_overdue_submissions` cron |
| **3b** Adaptive Engine — Phase 2 | Planned | Concepts knowledge graph + prerequisite DAG, Beta-Binomial mastery, HLR forgetting decay, syllabus-as-generation-context |
| **3c** Adaptive Engine — Phase 3 | Planned | KST outer-fringe `next_actions` ranking, instructor alerts, action-outcome telemetry, engine on/off A/B toggle |
| **4** Planned | Planned | i18n (Traditional Chinese), Canvas LMS deeper integration, advanced analytics |

<br/>

---

<br/>

## License

This project is developed for HKUST's Center for Language Education.

<br/>
