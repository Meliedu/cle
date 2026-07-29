<p align="center">
  <img src="https://img.shields.io/badge/-%F0%9F%8D%AF%20Meli-F5A623?style=for-the-badge&labelColor=1a1a2e" alt="Meli" />
</p>

<h1 align="center">Meli</h1>

<p align="center">
  <strong>A checkpoint-centred course operating loop for the HKUST Center for Language Education,<br/>
  built on an AI-powered adaptive learning engine.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-0.128-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Next.js-16-000000?style=flat-square&logo=next.js&logoColor=white" alt="Next.js" />
  <img src="https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black" alt="React" />
  <img src="https://img.shields.io/badge/PostgreSQL-17-4169E1?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/pgvector-0.3-4169E1?style=flat-square" alt="pgvector" />
  <img src="https://img.shields.io/badge/Better%20Auth-1.6-000000?style=flat-square" alt="Better Auth" />
  <img src="https://img.shields.io/badge/TypeScript-strict-3178C6?style=flat-square&logo=typescript&logoColor=white" alt="TypeScript" />
</p>

<br/>

---

<br/>

## Table of Contents

- [What is Meli?](#what-is-meli)
- [The Checkpoint Loop](#the-checkpoint-loop)
- [Feature Tour](#feature-tour)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Repository Structure](#repository-structure)
- [Data Model](#data-model)
- [API Reference](#api-reference)
- [Auth & Authorization](#auth--authorization)
- [Configuration](#configuration)
- [Local Development](#local-development)
- [Testing](#testing)
- [Deployment](#deployment)
- [Design System](#design-system)
- [Pilot Profiles](#pilot-profiles)
- [License](#license)

<br/>

---

<br/>

## What is Meli?

Meli (_honey_ in Greek) is a full-stack teaching platform for university language classrooms. It began as a RAG-powered study-tool generator — upload course materials, get quizzes, flashcards, and summaries grounded in the real content — and has since grown a **course operating loop** on top: a structured teacher/student workflow around **in-class checkpoints**, attendance, a per-student work-item checklist, activities, weekly reports, and a defensible score record.

The current product surface is built for a specific customer, the **HKUST Center for Language Education (CLE)**, and its LANG1511–1515 Chinese courses. Institution-specific behaviour is isolated behind a **pilot profile** (`PILOT_PROFILE=cle`), so the same codebase can be re-targeted.

Meli has **two distinct user lanes**, deliberately kept different rather than mirrored:

| Lane | Route tree | Shape |
|------|-----------|-------|
| **Teacher cockpit** | `/teacher/**` | Review-and-publish: set up a course, run checkpoints, review evidence, publish reports and scores. |
| **Student workspace** | `/student/**` | Action-first: "what should I do next", scan into a checkpoint, work the checklist, see your record. |

Underneath both lanes sits an **adaptive learning engine** (concepts, per-concept mastery, a contextual-bandit revision mode, live quizzes, pronunciation grading) whose services and tables are all present in this repository and power the insights, practice, and reporting surfaces.

<br/>

---

<br/>

## The Checkpoint Loop

The core teaching workflow the product automates:

```
  Setup ──▶ Session ──▶ Checkpoint ──▶ Attendance ──▶ Evidence ──▶ Report ──▶ Score
    │         │            │              │              │           │          │
 syllabus   release      author &       QR scan        checkpoint  weekly    grade
 → course   session      publish        binds the      responses   report    export
   map      to students  checkpoint     student to     + activity  drafted   (audited
 (LLM       (visibility  cards to a     the launch     responses   from the  CSV)
 analyze)   rules)       session        window         land on     evidence
                                                       the work-   → teacher
                                                       item spine  reviews &
                                                                   sends
```

1. **Setup** — a teacher creates a course, uploads the syllabus/materials, and the LLM drafts a **course map** (modules, sessions, objectives) they review and approve. The course is gated from publishing until context is approved.
2. **Session** — sessions (course meetings) are released to students according to visibility rules (students see only `released`/`completed` sessions).
3. **Checkpoint** — the teacher authors checkpoint cards for a session and publishes them. Checkpoints move through a lifecycle (`draft → scheduled → published → closed`) with typed gate codes when a transition isn't allowed.
4. **Attendance** — a checkpoint launch mints a **signed QR token** (PyJWT HS256, `exp = window end`, bound to the launch row). A student scans it at `/student/attend/{token}`; the scan is re-checked server-side and rate-limited.
5. **Evidence** — the student answers checkpoint cards and activities. Each answer's progress rides **the same database commit as the answer itself** (the "evidence seam") so participation is never lost; a best-effort side channel then feeds concept mastery. Activities and attendance are **participation-only** and never contribute to mastery.
6. **Report** — a weekly **report** is drafted from the accumulated evidence (`draft_report` worker job). The teacher reviews, edits, and sends it; sending is an append-only audited event.
7. **Score** — categories and per-student records roll up into a **grade export** (`GET …/grade-export.csv`) that is CSV-injection-safe and written to an append-only `grade_exports` audit table.

Two cross-cutting rules make the loop trustworthy:

- **Server-side gates with typed error codes** — e.g. `REVIEW_REQUIRED`, `QR_NOT_AVAILABLE`, `SCORE_POLICY_INCOMPLETE`, `REPORT_NOT_REVIEWED`, `ACTIVITY_NOT_OPEN` — so the UI can react precisely rather than parse prose.
- **Row-Level Security on student-owned tables** — checkpoint responses, attendance records, work-item progress, activity responses, readiness responses, and reports each carry an owner-isolation RLS policy (`user_id = current_setting('app.current_user_id')`).

<br/>

---

<br/>

## Feature Tour

### For instructors

- **Course setup wizard** — multi-step setup (`/teacher/courses/[id]/setup`); upload a syllabus, run `POST …/setup/analyze` for an LLM course-map draft, review the analysis, and `publish` (or `reopen`) the course.
- **Sessions & schedule** — create/edit course meetings, a schedule table, per-week calendar feed, and release-state control over what students can see.
- **Checkpoint studio** — author checkpoint cards for a session, generate cards from materials (`generate_checkpoints` worker job), publish, close, and watch a **live monitor** (WebSocket `…/checkpoints/{id}/monitor`) of who has responded.
- **QR attendance** — open a checkpoint to mint a scannable launch; roster and manual override endpoints for corrections.
- **Activities** — author in-class activities (swipe / vote / comment styles), publish them, and watch a live activity monitor (WebSocket). Activities are participation-only.
- **Reports** — a weekly report is auto-drafted from evidence; review, edit, and send. Reviewed/sent states are enforced server-side and audited.
- **Scores & grade export** — define weighted score categories, record per-student scores, and download an audited, injection-safe `grade-export.csv`.
- **Insights** — per-objective / per-skill cohort insights over reviewed evidence only (`/teacher/insights`, per-course `…/insights`).
- **Course memory** — carry-forward notes and a course-memory summary that persists teaching context across terms.
- **Practice & graded quizzes** — author practice quizzes and graded quizzes with a score policy; view per-quiz results.
- **Canvas LMS import** — connect Canvas via per-user OAuth and pull course files and rosters.

### For students

- **Action-first dashboard** — a "your next step" card driven by the work-item spine, plus this week's sessions and a personal to-do.
- **Join funnel** — enter a course code, answer a short readiness diagnostic (`POST …/readiness/{phase}`), and get an enrollment recommendation before joining.
- **Checkpoint flow** — scan a QR to attend, answer confidence + comprehension cards, and get an honest "you're in / missed / review required" state.
- **Checklist** — a per-course work-item checklist (`checkpoint | practice | quiz | activity | material | follow_up | report`) with monotonic progress (`to-do → in-progress → submitted → completed`, never regressing).
- **Materials, sessions, scores, reports** — read course materials, see released sessions, view your own score & participation record, and read weekly reports addressed to you.
- **Insights** — your objective strength and skill patterns, shown only where there is real reviewed evidence (honest empty states otherwise).
- **Practice / quiz** — take practice and graded quizzes with per-question feedback and a score-bearing disclosure before starting.

### The adaptive learning engine (underlying capability)

These subsystems are fully present in the codebase and back the practice, insights, and reporting surfaces:

- **RAG pipeline** — documents are downloaded → parsed → chunked → embedded → stored as `vector` + `tsvector`; hybrid vector + full-text retrieval with reranking.
- **Concepts & mastery** — an LLM extracts concept candidates, clusters them by embedding distance for instructor curation, and builds a prerequisite DAG (cycle-checked at write). Per-user **Beta-Binomial mastery** (`α/(α+β)`) with confidence and HLR-style forgetting decay.
- **Adaptive revision** — an infinite practice mode with a REINFORCE **contextual bandit** that adapts item difficulty in real time.
- **Live quiz** — Kahoot-style real-time sessions over WebSocket with join codes and speed scoring.
- **Pronunciation grading** — per-word accuracy via **Azure Speech** (English) and **iFlytek** (Chinese).
- **Flashcards** — SM-2 spaced repetition; an optional FSRS scheduler (`FSRS_ENABLED`).
- **Instructor alerts** — a rule evaluator that scans the cohort and raises dismissable/resolvable alerts.

> Note: the adaptive-engine study surfaces live under the legacy `/dashboard/**` route tree in the frontend; the CLE product surface (`/teacher/**`, `/student/**`) is the current entry point.

<br/>

---

<br/>

## Architecture

```
        Browser
           │  (HKUST OIDC SSO / email+password on dev)
           ▼
 ┌───────────────────────────────┐        JWT (EdDSA, JWKS-verified)
 │  Next.js 16  (Vercel)         │  ───────────────────────────────────┐
 │  App Router · React 19        │                                      │
 │  TanStack Query · next-intl   │   Better Auth runs *inside* Next.js  │
 │  Tailwind 4 · Base UI         │   • /api/auth/*  (sessions, JWKS,    │
 │  proxy.ts (session gate +CSP) │     OIDC callback, JWT plugin)       │
 └───────────────┬───────────────┘   • tables in Postgres `auth` schema │
                 │ apiFetch (Bearer JWT)                                 │
                 ▼                                                       ▼
 ┌───────────────────────────────┐                       ┌──────────────────────────┐
 │  FastAPI  (Railway)           │                       │  PostgreSQL 17 + pgvector │
 │  Python 3.12 · async SQLA 2.0 │──────────────────────▶│  • public schema (app)    │
 │                               │   asyncpg             │  • auth schema (BetterAuth)│
 │  Middleware:                  │                       │  • RLS on student tables  │
 │   Auth · RateLimit · CSP hdrs │                       └──────────────────────────┘
 │  ~40 routers → service layer  │
 │  DB-backed task queue         │──▶ background worker (separate Railway service in prod)
 └───────────────┬───────────────┘        • document pipeline · concept/mastery jobs
                 │                          • report drafting · checkpoint generation
                 ▼                          • Canvas daily sync · cron watermarks
        Cloudflare R2 (file storage, S3-compatible)
        OpenRouter (LLM + embeddings) · OpenAI (Whisper) · Azure/iFlytek (speech)
```

**Request path.** The browser holds a Better Auth session; `apiFetch` attaches a fresh JWT (`authClient.token()`) to every backend call. FastAPI's `AuthMiddleware` does a cheap Bearer presence check on `/api/*`, then `get_current_user` verifies the JWT against the Better Auth **JWKS** (`BETTER_AUTH_JWKS_URL`), checks issuer/audience, and upserts a `public.users` row keyed on `better_auth_id`.

**API envelope.** Every endpoint returns `APIResponse[T]` = `{ success, data, error }`; paginated endpoints add `meta: { total, page, limit, pages }`. Unhandled exceptions are logged server-side and returned as a generic `INTERNAL_ERROR` envelope.

**Task queue.** Background work is a DB-backed queue: the worker claims rows from `tasks` with `FOR UPDATE SKIP LOCKED`, runs the handler, and commits. It runs in-process in dev (`RUN_WORKER_IN_API=true`) and as a **separate Railway service** in production so a worker OOM can't take down the API. Retry-idempotency for user-facing state uses a `_task_created_at` watermark; a stuck-task reaper requeues rows running longer than 10 minutes.

**Monorepo.** `backend/` (FastAPI) and `frontend/` (Next.js) deploy independently but share one Postgres.

<br/>

---

<br/>

## Tech Stack

### Backend (`backend/requirements.txt`)

| Layer | Technology |
|-------|-----------|
| Framework | **FastAPI** 0.128.0 · **uvicorn** 0.34.2 (async, Python 3.12) |
| ORM / driver | **SQLAlchemy** 2.0.40 (async) + **asyncpg** 0.30.0 |
| Migrations | **Alembic** 1.15.2 (async engine) |
| Vectors | **pgvector** 0.3.6 (`vector` columns) |
| Validation | **Pydantic** 2.11.3 + pydantic-settings 2.9.1 |
| Auth | **PyJWT** 2.10.1 (JWKS verification) · cryptography 44.0.3 (Fernet) |
| Storage | **boto3** 1.38.12 → Cloudflare R2 (S3-compatible) |
| LLM + embeddings | **OpenRouter** via the **OpenAI SDK** 1.82.0 |
| Audio transcription | **OpenAI Whisper** (`audio.transcriptions`, mp3/mp4) |
| Doc parsing | **Docling** 2.89.0 · **pymupdf** 1.27.2 · python-docx 1.1.2 · python-pptx 1.0.2 |
| Chunking / rerank | **tiktoken** 0.9.0 · **flashrank** 0.2.9 |
| Speech | **Azure Cognitive Services Speech** 1.42.0 · iFlytek (HTTP) |
| ML (bandit) | **PyTorch** 2.7.0+cpu · **NumPy** 2.2.5 |
| HTTP | **httpx** 0.28.1 |
| Testing | **pytest** 8.3.5 + pytest-asyncio 0.26.0 |

### Frontend (`frontend/package.json`)

| Layer | Technology |
|-------|-----------|
| Framework | **Next.js** ^16.2.3 (App Router, Turbopack) |
| UI runtime | **React** 19.2.4 + **TypeScript** ^5 (strict) |
| Components | **Base UI** (`@base-ui/react` ^1.3.0) + shadcn ^4.1.2 primitives · **Tailwind CSS** ^4 |
| Data fetching | **TanStack Query** ^5.96.2 |
| Auth | **better-auth** ^1.6.9 + `@better-auth/infra` ^0.2.5 (self-hosted) |
| i18n | **next-intl** ^4.9.1 (en · zh-Hant) |
| Icons / toast | **lucide-react** ^1.7.0 · **sonner** ^2.0.7 |
| Markdown / dates / QR | react-markdown ^10 · date-fns ^4 · react-day-picker ^9 · qrcode.react ^4.2 |
| DB (Better Auth) | **pg** ^8.20 · **bcrypt** ^6 |
| Email | **resend** ^6.12 |
| Testing | **Playwright** ^1.59 · **Vitest** ^4.1 + Testing Library |

### Infrastructure

| Concern | Provider |
|---------|----------|
| Frontend | **Vercel** (project `meli`) — prod `cle-meli.hkust.edu.hk`, dev `cle-meli-dev.hkust.edu.hk` |
| Backend API + worker | **Railway** (Dockerfile; API + separate worker service) |
| Database | **PostgreSQL 17 + pgvector** (Railway) |
| File storage | **Cloudflare R2** |
| Auth | **Better Auth** (self-hosted in Next.js; `auth` schema) + HKUST OIDC |
| Email | **Resend** (verification + password reset) |
| CI | GitHub Actions — CodeQL SAST + dependency audit |

<br/>

---

<br/>

## Repository Structure

```
cle/
├── backend/                         # FastAPI service (Python 3.12)
│   ├── app/
│   │   ├── main.py                  # App + lifespan (worker + Canvas scheduler), middleware, /health
│   │   ├── config.py                # pydantic-settings; prod-required-var validation
│   │   ├── database.py              # Async engine + per-request RLS GUC (app.current_user_id)
│   │   ├── api/                     # ~40 routers (see API Reference)
│   │   │   ├── deps.py              #   get_current_user, require_instructor, get_db, ownership
│   │   │   ├── internal.py          #   Better Auth → backend user link/delete (X-Internal-Auth)
│   │   │   │  ── CLE checkpoint loop
│   │   │   ├── setup.py checkpoints.py attendance.py checklist.py activities.py
│   │   │   ├── meetings.py readiness.py reports.py scores.py memory.py insights.py review.py
│   │   │   │  ── Adaptive engine
│   │   │   ├── rag.py documents.py quizzes.py flashcards.py revision.py recalibration.py
│   │   │   ├── live.py speech.py pronunciation.py progress.py analytics.py
│   │   │   ├── concepts.py concept_prerequisites.py concept_clusters.py concept_tags.py mastery.py
│   │   │   ├── modules.py objectives.py assignments.py syllabus.py instructor_alerts.py
│   │   │   └── canvas.py canvas_oauth.py courses.py auth.py config.py
│   │   ├── models/                  # 38 SQLAlchemy 2.0 models (UUID PK, Timestamp/SoftDelete mixins)
│   │   ├── schemas/                 # Pydantic v2 request/response models
│   │   ├── services/                # ~55 service modules (business logic)
│   │   │   ├── worker.py jobs.py    #   DB task-queue consumer + cron blocks
│   │   │   ├── pipeline.py parser.py chunker.py embedder.py retriever.py generator.py vlm.py
│   │   │   ├── checkpoint_*.py       #   qr, attendance, monitor, responses, generation
│   │   │   ├── work_items.py activity_*.py score_policy.py scores.py audit.py
│   │   │   ├── readiness.py setup.py setup_analysis.py carry_forward_memory.py adaptive_jobs.py
│   │   │   ├── concept_*.py mastery.py bandit.py pool.py recalibrator.py scheduler.py
│   │   │   ├── live_quiz.py gamification.py speech.py question_grading.py
│   │   │   ├── auth.py crypto.py url_safety.py storage.py
│   │   │   └── canvas_*.py           #   client, oauth, files, roster, sync
│   │   ├── middleware/              # auth.py · rate_limit.py · security_headers.py
│   │   └── pilot/                   # Institution profiles (base.py, cle.py)
│   ├── alembic/versions/            # 57 migrations (head: e9a7c1f2b834)
│   ├── tests/                       # pytest + pytest-asyncio
│   ├── seed.py seed_demo.py seed_demo_content.py
│   ├── Dockerfile · railway.toml · railway.worker.toml
│   └── requirements.txt
│
├── frontend/                        # Next.js 16 App Router
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx                     # Landing (checkpoint-loop framing)
│   │   │   ├── sign-in/ sign-up/ forgot-password/ reset-password/ verify-email/
│   │   │   ├── (app)/teacher/**             # Teacher cockpit (dashboard, courses, setup,
│   │   │   │                                #   sessions, checkpoints, activities, quiz,
│   │   │   │                                #   reports, memory, insights, calendar)
│   │   │   ├── (app)/student/**             # Student workspace (dashboard, join, attend,
│   │   │   │                                #   checkpoints, checklist, materials, scores,
│   │   │   │                                #   reports, insights, follow-ups)
│   │   │   ├── dashboard/**                 # Legacy adaptive-engine study surfaces
│   │   │   └── api/auth/[...all]/route.ts   # Better Auth handler
│   │   ├── components/              # ~40 feature domains (checkpoint, course, setup,
│   │   │                            #   activities, materials, reports, calendar, quiz, …)
│   │   ├── hooks/                   # 39 TanStack Query hooks
│   │   ├── lib/                     # api.ts (apiFetch) · auth.ts · auth-client.ts · auth-flags.ts
│   │   ├── i18n/request.ts          # next-intl locale resolution (NEXT_LOCALE cookie)
│   │   ├── proxy.ts                 # Session gate + per-request nonce CSP (replaces middleware.ts)
│   │   └── styles/tokens.css        # "Honey & Salt" design tokens (oklch)
│   ├── messages/                    # en.json · zh-Hant.json
│   ├── e2e/                         # Playwright (auth, role-routing, demo-flow live-stack)
│   └── package.json
│
├── docker-compose.yml               # PostgreSQL 17 + pgvector (local dev)
├── .env.example                     # Backend env template
└── .github/workflows/               # CodeQL SAST · dependency audit
```

<br/>

---

<br/>

## Data Model

All app tables use **UUID primary keys**, `TimestampMixin` (created/updated), and (where applicable) `SoftDeleteMixin` (`deleted_at`). Better Auth's own tables (`user`, `session`, `account`, `verification`, `jwks`) live in the separate **`auth` schema** of the same database. **57 migrations** manage the schema (current head `e9a7c1f2b834`).

### CLE checkpoint-loop tables

| Table | Purpose |
|-------|---------|
| `course_meetings` | Sessions, with release state + topic/summary |
| `checkpoints`, `checkpoint_launches` | Checkpoint definitions + a launch (QR window, `jti`-bound token) |
| `checkpoint_responses` | Per-student card answers **(RLS owner-isolation)** |
| `attendance_records` | Scan-in / override records **(RLS)** |
| `work_items`, `work_item_progress` | Course-scoped checklist spine + per-student progress **(RLS)** |
| `activities`, `activity_responses` | In-class activities + participation responses **(RLS)** |
| `readiness_responses` | Join-funnel diagnostic answers **(RLS)** |
| `reports` | Weekly student reports (draft → reviewed → sent) **(RLS)** |
| `course_record_items` | Per-student record entries with a `decision` |
| `score_categories`, score records | Weighted grade categories + per-student scores |
| `grade_exports` | Append-only audit of every CSV grade export |
| `audit_events` | Append-only audit log (report sends, exports, …) |

RLS policies isolate rows by `user_id = current_setting('app.current_user_id', true)::uuid`. Tests run as a `BYPASSRLS` superuser; the production app connects `BYPASSRLS` and RLS is proven under a non-privileged `meli_app` role in the test suite.

### Adaptive-engine tables

| Domain | Tables |
|--------|--------|
| Content | `documents`, `chunks` (`vector` + `tsvector`), `summaries` |
| Assessment | `quizzes`, questions, `flashcard` sets/cards, `revision` sessions, `recalibration` |
| Live quiz | `sessions`, `live_answers` |
| Curriculum | `modules`, `objectives`, `assignments`, syllabus imports (`curriculum.py`) |
| Concepts | `concepts` (canonical + cluster ids), `concept_prerequisites` (DAG), `concept_tags` (polymorphic), `concept_mastery` (composite PK, `GENERATED` mastery_score), `concept_mastery_history` |
| Decision | next-action / outcome / instructor-alert tables (`decision.py`) |
| Platform | `users`, `courses`, enrollments, `tasks`, `api_usage`, `cron_run`, Canvas creds/nonce, scheduler state |

Concept embeddings are `vector(3072)` (native dim of `text-embedding-3-large`); clustering runs in-process (pgvector caps HNSW at 2000 dims for that type).

### Migrations

```bash
cd backend
alembic upgrade head                                   # apply all
alembic revision --autogenerate -m "description"       # create after model changes
alembic downgrade -1                                   # roll back one
```

<br/>

---

<br/>

## API Reference

All endpoints are under `/api` and require `Authorization: Bearer <jwt>` except `/health`. The frontend fetches the JWT via `authClient.token()` and the backend verifies it against the Better Auth JWKS. Response envelope: `{ success, data, error }`.

Routers are grouped by domain (prefix + OpenAPI tag). Representative endpoints are listed; browse the full, always-current surface at `GET /docs` (Swagger, non-production only).

<details>
<summary><strong>Courses, setup & sessions</strong></summary>

| Prefix | Notable endpoints |
|--------|-------------------|
| `/courses` | create / list / get / update / soft-delete a course; enroll |
| `/courses/{id}/setup` | `GET`/`PATCH` setup · `POST /analyze` (LLM course-map) · `GET /analysis` · `POST /publish` · `POST /reopen` |
| `/courses/{id}` (curriculum) | `POST`/`GET`/`PUT`/`DELETE /meetings` · `GET /calendar` |
| `/courses/{id}/modules`, `/objectives`, `/assignments`, `/syllabus` | curriculum spine + LLM syllabus parse/apply |
| `/config` | pilot + feature-flag config for the client |

</details>

<details>
<summary><strong>Checkpoints & attendance</strong></summary>

| Prefix | Notable endpoints |
|--------|-------------------|
| `/courses/{id}` / `/checkpoints` | author, list, get, `PATCH`, generate, `POST /{id}/approve`, `/schedule`, `/publish`, `/close`; results & responses; `WS /{id}/monitor` |
| `/checkpoints/{id}` (student) | student-facing checkpoint read + response submission |
| `/checkpoints` (attendance) | `POST` open a checkpoint launch (mint QR) |
| `/attendance` | `POST` scan-by-token (rate-limited, re-checked) |
| `/meetings` (attendance) | `GET` roster |
| `/attendance` (record) | `PATCH` manual override |

</details>

<details>
<summary><strong>Checklist, activities & readiness</strong></summary>

| Prefix | Notable endpoints |
|--------|-------------------|
| `/courses/{id}` | `GET /checklist` · `GET /next-action` · `GET /work-items` · upsert progress |
| `/work-items/{id}` | `PATCH` / `DELETE` a work item |
| `/activities` + `/courses/{id}` | create, list, get, `PATCH`, delete, publish; responses & results; `WS /{id}/monitor` |
| `/courses/{id}` (readiness) | `POST /readiness/{phase}` · `GET /readiness/summary` · `GET /preview` (join funnel) |

</details>

<details>
<summary><strong>Reports, scores, memory & insights</strong></summary>

| Prefix | Notable endpoints |
|--------|-------------------|
| `/courses/{id}/reports` + `/reports/{id}` | `POST /draft`, list, get, `PATCH`, review actions, send |
| `/users/me` (reports) | a student's own reports |
| `/courses/{id}` (scores) | score-category CRUD · records · `GET /grade-export.csv` (audited, injection-safe) |
| `/users/me/courses/{id}` (scores) | a student's own score record |
| `/courses/{id}/memory` + `/memory` | course-memory items + `GET /summary` |
| insights router | teacher/student objective & skill insights (reviewed evidence only) |
| review router | checkpoint-response review / grading |

</details>

<details>
<summary><strong>Adaptive engine</strong></summary>

| Prefix | Notable endpoints |
|--------|-------------------|
| `/rag` | `POST /query` (vector/fulltext/hybrid) · `generate-quiz` · `generate-summary` · `generate-flashcards` — rate-limited (students 10/hr, instructors 50/hr) |
| `/courses/{id}/documents` | upload (PDF/DOCX/PPTX/MP3/MP4) · list · delete |
| `/quizzes` | quiz + question CRUD · publish · `POST /{id}/attempt` |
| `/flashcards` | set list/get · publish · SM-2 progress |
| `/revision` | start session · answer (bandit update) · next · end |
| `/live` | live-quiz REST + `WS /live/{id}` |
| `/speech`, `/pronunciation` | grade pronunciation · history |
| `/courses/{id}/concepts`, `/concept-tags`, mastery | concept graph, curation, per-user & cohort mastery |
| `/analytics`, `/progress` | instructor analytics · gamification/progress |
| `/courses/{id}/canvas`, `/canvas` | Canvas import + per-user OAuth |

</details>

### Background jobs (task queue)

The worker dispatches these `task_type`s (`app/services/worker.py`): `process_document`, `revision_pool_replenish`, `recalibration`, generation jobs (quiz/flashcards/summary/pronunciation), `parse_syllabus`, `extract_concept_candidates`, `tag_artifact_concepts`, `update_concept_mastery`, `replay_attempt_history`, `evaluate_instructor_alerts`, `draft_learning_notes`, `draft_report`, `analyze_course_setup`, `generate_checkpoints`. Nightly cron blocks handle report drafting, alert evaluation, learning notes, and mastery decay.

<br/>

---

<br/>

## Auth & Authorization

Authentication is **self-hosted Better Auth** running inside the Next.js app; its tables live in the Postgres `auth` schema. The JWT plugin issues EdDSA (Ed25519) tokens and publishes a JWKS at `/api/auth/jwks`, which the FastAPI backend verifies with `PyJWKClient`.

**Providers.**

- **HKUST OIDC** (production sign-in) via `genericOAuth`: staff tenant (`providerId: "hkust"`) and student tenant (`providerId: "hkust-student"`). Each is mounted only when its `*_DISCOVERY_URL` + client id/secret are all present.
- **Microsoft** social provider — mounted only when `MICROSOFT_CLIENT_ID` + `MICROSOFT_CLIENT_SECRET` are set.
- **Email + password** — enabled in the Better Auth config, but **host-gated**: `isEmailPasswordHost()` (`src/lib/auth-flags.ts`) allows it only on `cle-meli-dev.hkust.edu.hk`, `localhost`, `127.0.0.1`, `::1` (fail-closed). A Better Auth `before` hook rejects the email/sign-in, sign-up, and password-reset routes with `403` unless **every** host signal (`Host` + `X-Forwarded-Host`) is an allowed host. Net effect: **production is SSO-only**; the dev domain and local dev keep email/password for demo accounts.

**Authorization.**

1. `AuthMiddleware` — cheap Bearer presence check on `/api/*`.
2. `get_current_user` (`api/deps.py`) — verifies JWT against JWKS, checks issuer/audience, upserts `public.users` on `better_auth_id`.
3. **Role by email domain** — `ust.hk` → instructor, `connect.ust.hk` → student (`ALLOWED_EMAIL_DOMAINS`). A `databaseHooks.user.create.before` domain gate rejects other domains even for SSO sign-ups.
4. **Internal link hook** — Better Auth's `user.create.after` POSTs `/api/internal/users/link` (guarded by `BETTER_AUTH_INTERNAL_SECRET`, `X-Internal-Auth` header) so the local row is created atomically.
5. `require_instructor` + ownership/enrollment checks gate teacher-only and cross-course access; RLS isolates student-owned rows.

`proxy.ts` gates every non-public route with `auth.api.getSession(...)` (redirecting to `/sign-in?redirect=…`) and emits a per-request nonce Content-Security-Policy.

<br/>

---

<br/>

## Configuration

### Backend (`backend/.env`)

| Variable | Purpose |
|----------|---------|
| `ENVIRONMENT` | `development` \| `production` (prod gates several required vars) |
| `DATABASE_URL` | Async Postgres DSN (`postgresql+asyncpg://…`); use `meli_app` in prod |
| `BETTER_AUTH_JWKS_URL` | JWKS endpoint (e.g. `https://…/api/auth/jwks`) — **required in prod** |
| `BETTER_AUTH_ISSUER` / `BETTER_AUTH_AUDIENCE` | Expected JWT `iss` / `aud` — **required in prod** |
| `BETTER_AUTH_INTERNAL_SECRET` | Shared secret for the Next.js → backend user-link hook — **required in prod** |
| `INTEGRATIONS_ENCRYPTION_KEY` | Fernet key encrypting third-party tokens (Canvas) — **required in prod** |
| `RESEND_API_KEY` / `RESEND_FROM_EMAIL` | Transactional email |
| `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET_NAME` / `R2_ENDPOINT_URL` | Cloudflare R2 file storage |
| `OPENAI_API_KEY` | Whisper audio transcription (mp3/mp4) |
| `OPENROUTER_API_KEY` / `OPENROUTER_BASE_URL` | LLM generation + embeddings (single key) |
| `OPENROUTER_PRIMARY_MODEL` / `OPENROUTER_FALLBACK_MODEL` | default `deepseek/deepseek-v3.2` / `google/gemini-2.5-flash-lite` |
| `VLM_MODEL` · `ENABLE_FIGURE_CAPTIONS` · `ENABLE_PAGE_RESCUE` · `PAGE_RESCUE_*` | Vision-LLM captions + low-text page rescue |
| `AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION` | English pronunciation grading |
| `IFLYTEK_APP_ID` / `IFLYTEK_API_KEY` / `IFLYTEK_API_SECRET` | Chinese pronunciation grading |
| `CHECKPOINT_TOKEN_SECRET` | HS256 signing key for the QR launch token (≥32 bytes; validated at launch time) |
| `CANVAS_CLIENT_ID` / `CANVAS_CLIENT_SECRET` / `CANVAS_BASE_URL` / `CANVAS_REDIRECT_URI` / `CANVAS_STATE_SECRET` / `CANVAS_ALLOWED_HOSTS` | Canvas OAuth + SSRF allowlist |
| `PILOT_PROFILE` | Institution profile (default `cle`) |
| `FSRS_ENABLED` | FSRS spaced-repetition scheduler (default `true`) |
| `BACKEND_URL` / `FRONTEND_URL` | Public origins (CORS + OAuth redirects) |
| `ALLOWED_EMAIL_DOMAINS` | default `connect.ust.hk,ust.hk` |
| `STUDENT_RATE_LIMIT` / `INSTRUCTOR_RATE_LIMIT` | `/api/rag/*` per-hour limits (10 / 50) |
| `MAX_UPLOAD_SIZE_MB` · `PARSER_TIMEOUT_SECONDS` | upload cap (100) · parse timeout (300s) |
| `RUN_WORKER_IN_API` | Run worker+scheduler in-process (`true` dev; `false` on the prod API container) |

### Frontend (`frontend/.env.local`)

| Variable | Purpose |
|----------|---------|
| `NEXT_PUBLIC_API_URL` | Backend base (default `http://localhost:8000/api`) |
| `NEXT_PUBLIC_HKUST_SSO` | `enabled` to show the HKUST SSO buttons |
| `NEXT_PUBLIC_MICROSOFT_SSO_ENABLED` | Show the Microsoft SSO button |
| `BETTER_AUTH_SECRET` / `BETTER_AUTH_URL` | Better Auth signing secret + public origin |
| `BETTER_AUTH_INTERNAL_SECRET` | Must match the backend value |
| `DATABASE_URL` | Same Postgres (Better Auth uses the `auth` schema) |
| `HKUST_STAFF_*` / `HKUST_STUDENT_*` | OIDC discovery URL + client id/secret per tenant |
| `MICROSOFT_CLIENT_ID` / `MICROSOFT_CLIENT_SECRET` | Microsoft OAuth (optional) |
| `RESEND_API_KEY` | Verification + password-reset email (dev/host-gated only) |

<br/>

---

<br/>

## Local Development

### Prerequisites

- Python 3.12+ · Node.js 20+ · Docker (for Postgres) · an OpenRouter API key

### 1 · Database

```bash
docker compose up -d       # PostgreSQL 17 + pgvector on 127.0.0.1:5432 (db: langassistant)
```

### 2 · Backend

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env         # then fill in your keys
alembic upgrade head
uvicorn app.main:app --reload   # http://localhost:8000  (docs at /docs)
```

### 3 · Frontend

```bash
cd frontend
npm install
npm run dev                     # http://localhost:3000
```

### 4 · Demo data (optional)

The demo seed is **two scripts** that share deterministic ids (so a Better Auth JWT `sub` equals `public.users.better_auth_id`):

```bash
# public schema: users + a published LANG1511 course + sessions + enrollments
python backend/seed_demo.py
# P3–P7 content: checkpoints, a practice + graded quiz, an activity, checklist items, reports
python backend/seed_demo_content.py
# auth schema: email/password credentials for the demo accounts
node frontend/scripts/seed-auth.mjs
```

Demo logins (password `MeliDemo2026!`, **local/dev only** — email login is host-gated): `meli.teacher@ust.hk` (instructor), `meli.student@connect.ust.hk` (enrolled), `meli.pending@connect.ust.hk` (join-request pending).

### Inspecting the database

Connect any SQL client to `localhost:5432`, db `langassistant`, `postgres`/`postgres` (local only). For the shared Railway database, use the **read-only** or **admin** role — credentials are in the team's secret manager (they are intentionally not committed here). The production app connects as `meli_app`; never use the cluster superuser for app traffic.

<br/>

---

<br/>

## Testing

```bash
# Backend — requires a langassistant_test database (same creds)
cd backend && pytest
pytest tests/test_checkpoints_api.py            # one file
pytest tests/test_auth_service.py -k "test_name"  # one test

# Frontend — unit/component (Vitest) + i18n audit + E2E (Playwright)
cd frontend
npm test
npm run i18n:audit
npm run e2e            # infra-free specs; the demo-flow spec needs MELI_LIVE_STACK=1
```

The E2E suite splits into infra-free specs (`auth`, `role-routing`) and a live-stack `demo-flow` spec (gated on `MELI_LIVE_STACK=1`) that walks the full teacher + student flow against a running backend + seeded Postgres.

<br/>

---

<br/>

## Deployment

**Frontend → Vercel** (project `meli`). Both the production domain `cle-meli.hkust.edu.hk` and the dev domain `cle-meli-dev.hkust.edu.hk` are served by the **same** deployment; they are told apart at request time by `Host` (that is why the email/password gate is per-request, not a build flag). Production is **SSO-only**; dev keeps email/password.

**Backend → Railway** (Dockerfile). `railway.toml` runs `alembic upgrade head` as a pre-deploy step, starts `uvicorn`, and health-checks `/health`. The document worker + Canvas scheduler run as a **separate** Railway service (`railway.worker.toml`) with `RUN_WORKER_IN_API=false` on the API container.

**CI** — every push to `main` runs CodeQL SAST and a dependency audit (`.github/workflows/`).

Operate infra directly via the Railway and Vercel CLIs / APIs rather than the web dashboards.

<br/>

---

<br/>

## Design System

Meli uses the **"Honey & Salt"** system defined in [`frontend/src/styles/tokens.css`](frontend/src/styles/tokens.css), entirely in the **oklch** color space: a warm honey primary (`oklch(70% 0.16 80)`) with a cool "salt" blue accent, coral/cream/sand/olive/gold supporting hues, and a deep-bronze navigation rail. Type pairs **Hanken Grotesk** (body/UI, `--font-sans`) with **Fraunces** (editorial variable serif display, `.font-display`) — both loaded via `next/font`. Motion and atmosphere utilities are reduced-motion-guarded.

<br/>

---

<br/>

## Pilot Profiles

Institution-specific configuration is isolated in `backend/app/pilot/` (`base.py`, `cle.py`) and selected by `PILOT_PROFILE` (default `cle`). The app fails fast at startup on an unknown profile. This keeps HKUST-CLE specifics (email domains, course conventions, copy) out of the core so the platform can be re-targeted to another institution.

<br/>

---

<br/>

## License

Developed for the HKUST Center for Language Education. All rights reserved unless a separate license is added to this repository.

<br/>
