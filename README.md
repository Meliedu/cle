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
- **Concept curation** - the LLM extracts candidate concepts from chunks, clusters them by embedding distance, and surfaces a review queue where you approve, rename, merge, or reject each cluster. Build a prerequisite DAG with cycle detection at write-time.
- **Cohort mastery view** - per-concept Beta-Binomial mastery across every enrolled student, so "who is weak at *inference*?" is a real query rather than a guess.
- **Instructor alerts** - an evaluator runs a 7-rule scan (cohort-wide weakness, missed deadlines, falling-behind students, content with no engagement, etc.) and surfaces dismissable / resolvable alerts in a centre.
- **Engine settings + A/B** - flip the adaptive engine on, off, or run `random_50` (deterministic per-(user, course) hash) to A/B-test the engine against a control arm. Per-user overrides for edge cases.
- **Assignment grading** - per-student submission roster, score and feedback entry, automatic late-flagging for overdue submissions.
- **Generate quizzes** from uploaded materials with one click. Edit, publish, and track student attempts.
- **Generate flashcard sets** tied to specific documents or entire courses.
- **Host live quizzes** - Kahoot-style real-time sessions with join codes, speed-based scoring, and live leaderboards.
- **Analytics dashboard** - course overview, per-quiz performance, and per-student stats (XP, scores, activity).
- **Canvas LMS integration** - import files directly from connected Canvas courses.
- **Usage analytics** - per-student rate limiting protects against API cost overruns.

### For Students

- **Course calendar** - per-week view across all enrolled courses showing scheduled meetings and published assignment deadlines, sorted by time.
- **Today page** - the engine ranks the top-10 things you should do next by combining your concept mastery, upcoming deadlines, and meeting prep. Click-throughs are recorded so the engine learns which actions actually move the needle.
- **Personal mastery panel** - per-concept Beta-Binomial mastery (`α/(α+β)`) and confidence (`1 − √var`), with HLR-style forgetting decay so untouched concepts drift back toward the prior over a 14-day half-life.
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
                                                 |   |  progress,       |   |
                                                 |   |  curriculum,     |   |
                                                 |   |  syllabus,       |   |
                                                 |   |  concepts,       |   |
                                                 |   |  mastery,        |   |
                                                 |   |  next_actions,   |   |
                                                 |   |  alerts, engine  |   |
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
                                              |  modules, meetings,         |
                                              |  assignments, syllabus,     |
                                              |  concepts (+ prereqs/tags), |
                                              |  concept_mastery,           |
                                              |  next_actions, alerts,      |
                                              |  action_outcomes,           |
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
| File | ----------> |Docling| ----------> |Chunker| ----------> |OpenRtr| ---------> |pgvec |
|      |             |Whisper|             |       |  overlap     | text- |  1536 dim   | tor  |
|      |             |       |             |       |              |  3-lg |             |      |
+------+             +------+             +------+              +------+             +------+
                         |                     |
                    PDF/DOCX/PPTX        Sentence-aligned
                    MP3/MP4              50-token overlap
```

| Stage | Service | Details |
|-------|---------|---------|
| **Parse** | [parser.py](backend/app/services/parser.py) | Docling for PDF/DOCX/PPTX with page-level extraction. Whisper for MP3/MP4. |
| **Chunk** | [chunker.py](backend/app/services/chunker.py) | Sentence-aligned splitting at ~500 tokens with 50-token overlap. Page numbers preserved. |
| **Embed** | [embedder.py](backend/app/services/embedder.py) | `openai/text-embedding-3-large` via OpenRouter, reduced to 1536 dims for chunk vectors. Batched in groups of 100. (Concept embeddings in Phase 2 use the native 3072 dim.) |
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

### Concepts & Mastery (Adaptive Engine — Phase 2)

The concept layer adds the *meaning* axis on top of the existing evidence layer. Five new tables (`concepts`, `concept_prerequisites`, `concept_tags`, `concept_mastery`, `concept_mastery_history`) plus a `primary_concept_id` column on `revision_attempts`. Concept embeddings are `vector(3072)` matching the native dim of `text-embedding-3-large`; chunk embeddings stay at 1536 — tagging happens via LLM at write-time, not vector crosswalk.

```
                    +--------------+   extract (LLM)   +-------------+
                    |   chunks     +------------------>|  candidate  |
                    | (per course) |                   |  concepts   |
                    +------+-------+                   +------+------+
                           |                                  | embed (3072d)
                           | tag                              | greedy
                           | (LLM,                     +------v------+
                           |  inheritance)             |  clusters   |
                           v                           +------+------+
                  +-----------------+                         | curate
                  |  concept_tags   |  polymorphic            v
                  |  target_kind in |  ────────────────  +---------+
                  |  chunk |        |                    | concepts|
                  |  question |     |                    | (course |
                  |  flashcard_card |                    |  scope) |
                  |  pool_item |    |                    +----+----+
                  |  pronunciation_ |                         |
                  |    item |       |                         | DAG (cycle-
                  |  objective |    |                         | guarded at
                  |  meeting |      |                         | write)
                  |  assignment     |                    +----v----+
                  +--------+--------+                    |concept_ |
                           |                             |prereqs  |
            quiz/flash/    |                             +---------+
            revision/      | apply attempt evidence
            pronunciation  |
            attempts ----->|         +-----------------+
                           +-------->| concept_mastery |  α, β counts
                                     |    + history    |  mastery_score = α/(α+β)
                                     +--------+--------+  confidence  = 1 − √var
                                              |
                                       nightly HLR decay
                                       (2^(−days/τ), τ=14d)
```

| Capability | Service / Endpoint |
|------------|-------------------|
| Concept CRUD + cohort | `/api/courses/{id}/concepts` ([concepts.py](backend/app/api/concepts.py)) |
| Prerequisite DAG (cycle check via `WITH RECURSIVE` at write) | `/api/courses/{id}/concept-prerequisites` ([concept_prerequisites.py](backend/app/api/concept_prerequisites.py)) |
| Cluster curation queue (LLM extract → greedy cosine cluster → instructor decide) | `/api/courses/{id}/concept-clusters` ([concept_clusters.py](backend/app/api/concept_clusters.py)) |
| Tag inspection (read-only, polymorphic) | `/api/concept-tags/{target_kind}/{target_id}` ([concept_tags.py](backend/app/api/concept_tags.py)) |
| Personal mastery + cohort view | `/api/users/me/courses/{id}/mastery`, `/api/courses/{id}/mastery` ([mastery.py](backend/app/api/mastery.py)) |
| LLM extraction + 90-day replay | `POST /concepts/extract`, `POST /concepts/replay` (instructor-triggered, 409 if in-flight) |
| Background jobs | `extract_concept_candidates` (clustering runs inline within this handler), `tag_artifact_concepts`, `update_concept_mastery`, `replay_attempt_history`. Mastery decay runs as an in-worker cron block invoking `decay_due_mastery_rows` (gated by a `last_decay_run` watermark) — not a separate Task row. |

**Mastery math.** Each attempt-recording endpoint enqueues `update_concept_mastery` after committing the user's attempt (try/except so attempt durability survives an enqueue failure). The handler joins `concept_tags` for the target, runs `α += w·outcome, β += w·(1−outcome)` for every tagged concept (chunk-inherited tags carry `weight × 0.7`), recomputes confidence, and appends a history row. A nightly cron applies HLR-style forgetting decay. Concept embeddings are stored on `concepts.embedding` for similarity search; HNSW is intentionally absent — pgvector caps HNSW at 2000 dims for `vector` and clustering runs in-process.

**Race + retry safety.** First-attempt rows use `INSERT … ON CONFLICT DO NOTHING RETURNING` then re-fetch on conflict — see `services/mastery.py::_get_or_create_mastery`. Tasks that mutate user-facing state carry a `_task_created_at` watermark; the handler checks `concept_mastery_history` for `recorded_at >= watermark` and skips if already-applied. Closes the seam between handler-commit and `complete_task`-commit when `_reset_stuck_tasks` requeues.

**Generation grounding.** Quiz / flashcard / summary generators load the latest applied `SyllabusImport` payload as additional context, and tag artifact outputs with concepts inherited from the source chunk. The pronunciation grade endpoint accepts a `pronunciation_item_id` form field and feeds those attempts into mastery the same way (free-form practice keeps working — the FK is nullable).

### Decision Layer (Adaptive Engine — Phase 3)

The decision layer reads from `concept_mastery` + curriculum and produces ranked actions and instructor alerts. Four new tables (`next_actions`, `action_outcomes`, `instructor_alerts`, `engine_overrides`) plus a `courses.adaptive_engine_mode` column.

```
                     concept_mastery + curriculum + deadlines
                                       |
                                       v
              +---------- KST outer-fringe candidate filter -----------+
              |  concepts whose every prerequisite has                 |
              |  mastery_score >= 0.7 AND confidence >= 0.5            |
              |  but the concept itself does not                       |
              +---------------------+----------------------------------+
                                    |
                                    v
                         +-----------------------+
                         |  scoring (weighted)   |   prep_meeting     3.0
                         |  one fn per           |   complete_assign  5.0
                         |  action_type          |   practice_weak    2.0
                         +----------+------------+   flashcard_review 1.5
                                    |                catch_up_reading 1.0
                                    v
                            top-10 next_actions
                            (TTL 1h, 30-min lazy
                             recompute on read)
                                    |
                       served / clicked / observed
                                    |
                                    v
                         +-----------------------+
                         |    action_outcomes    |   engine_variant ∈ {on, off}
                         |  (per impression)     |   tracks A/B telemetry
                         +-----------+-----------+
                                     |
                                     | quarterly retune
                                     v
                            tune_action_coefficients
                            (currently propose-only)
```

| Capability | Service / Endpoint |
|------------|-------------------|
| Student "Today" — top-10 ranked actions | `GET /api/users/me/courses/{id}/next-actions` ([next_actions.py](backend/app/api/next_actions.py)) — lazy 30-min recompute on read |
| Click-through telemetry | `POST /api/next-actions/{id}/click` (records impression + click for the served `engine_variant`) |
| Instructor alerts centre | `GET /api/courses/{id}/alerts`, `PATCH /api/courses/{id}/alerts/{aid}` ([instructor_alerts.py](backend/app/api/instructor_alerts.py)) — dismiss / resolve |
| Engine settings + per-user overrides | `GET / PATCH /api/courses/{id}/engine`, `PUT / DELETE /api/courses/{id}/engine/overrides/{uid}` ([engine_settings.py](backend/app/api/engine_settings.py)) |
| Background jobs | `materialize_next_actions`, `evaluate_instructor_alerts`, `tune_action_coefficients`, `record_action_outcome`; daily horizon-scan cron enqueues recompute for upcoming deadlines/meetings |

**Engine modes.** Per-course `adaptive_engine_mode ∈ {on, off, random_50}`, per-user override (`on` / `off` only) wins over course mode. `random_50` deterministically splits students using `blake2b(user_id || course_id) % 2`, so the same student stays in the same arm across sessions and per-student outcome curves stay clean. When the resolved mode is `off`, the API returns an empty list **but still writes** `action_outcomes` rows with `engine_variant='off'` for the artifact the student touched anyway — that's what produces the off-arm outcome curve for retroactive A/B.

**Scoring as tie-breaker.** KST outer-fringe is the *candidate selector*; scoring orders candidates within it. Coefficients are initial defaults; `tune_action_coefficients` runs quarterly and proposes deltas to `Task.payload['result']` without applying them — manual review until enough outcome data accumulates to trust auto-apply.

**What the engine does not touch.** The bandit / FSRS / recalibration tables are read-only neighbours; the concept layer filters the candidate pool *before* the bandit picks difficulty within an item set. The two systems compose vertically.

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
| `DATABASE_URL` | PostgreSQL async connection string (use the `meli_app` role in prod so RLS is enforced) |
| `ENVIRONMENT` | `development` or `production` — production gates several required vars |
| `BETTER_AUTH_JWKS_URL` | Better Auth JWKS endpoint (e.g. `http://localhost:3000/api/auth/jwks`) |
| `BETTER_AUTH_ISSUER` | Expected JWT `iss` claim (e.g. `http://localhost:3000`) |
| `BETTER_AUTH_AUDIENCE` | Expected JWT `aud` claim (e.g. `meli-backend`) |
| `BETTER_AUTH_INTERNAL_SECRET` | Shared secret for Next.js signup hook → `POST /api/internal/users/link` |
| `RESEND_API_KEY` | Resend API key (verification + password-reset email) |
| `RESEND_FROM_EMAIL` | From-address for transactional email (default: `Meli <noreply@meli.app>`) |
| `R2_ACCOUNT_ID` | Cloudflare account ID |
| `R2_ACCESS_KEY_ID` | R2 access key |
| `R2_SECRET_ACCESS_KEY` | R2 secret key |
| `R2_BUCKET_NAME` | R2 bucket name |
| `R2_ENDPOINT_URL` | R2 S3-compatible endpoint |
| `OPENAI_API_KEY` | Whisper transcription (audio/video). Embeddings now route via OpenRouter — this stays optional unless you upload media. |
| `OPENROUTER_API_KEY` | LLM generation + embeddings + VLM (single key for everything) |
| `OPENROUTER_PRIMARY_MODEL` | Primary LLM (default: `deepseek/deepseek-v3.2`) |
| `OPENROUTER_FALLBACK_MODEL` | Fallback LLM on JSON-parse failure (default: `google/gemini-2.5-flash-lite`) |
| `VLM_MODEL` | Vision-LLM for figure captions / low-text page rescue (default: `google/gemini-2.5-flash`) |
| `ENABLE_FIGURE_CAPTIONS` | Toggle Docling+VLM caption pass (default: `true`; turn `false` in dev to save spend) |
| `ENABLE_PAGE_RESCUE` | Toggle VLM transcription for scan/image-only PDF pages (default: `true`) |
| `ALLOWED_EMAIL_DOMAINS` | Comma-separated (e.g., `connect.ust.hk,ust.hk`) |
| `STUDENT_RATE_LIMIT` | AI requests per hour for students (default: 10) |
| `INSTRUCTOR_RATE_LIMIT` | AI requests per hour for instructors (default: 50) |
| `MAX_UPLOAD_SIZE_MB` | Hard upload cap (default: 100) |
| `RUN_WORKER_IN_API` | Run document worker + Canvas scheduler in-process (default: `true`; set `false` on prod API container if running a separate worker service) |
| `AZURE_SPEECH_KEY` | Azure Speech Services key (English pronunciation grading) |
| `AZURE_SPEECH_REGION` | Azure Speech region (default: `eastasia`) |
| `IFLYTEK_APP_ID` | iFlytek app ID (Chinese pronunciation) |
| `IFLYTEK_API_KEY` | iFlytek API key |
| `IFLYTEK_API_SECRET` | iFlytek API secret |
| `INTEGRATIONS_ENCRYPTION_KEY` | Fernet key for encrypting third-party tokens at rest (Canvas, etc.). Required in prod. |
| `CANVAS_ALLOWED_HOSTS` | Comma-separated allowlist of Canvas hostnames (SSRF defense) |
| `CANVAS_CLIENT_ID` / `CANVAS_CLIENT_SECRET` | HKUST Canvas Developer Key (OAuth 2.0) |
| `CANVAS_BASE_URL` | Canvas tenant base URL (default: `https://canvas.ust.hk`) |
| `CANVAS_REDIRECT_URI` | OAuth callback (default: `http://localhost:8000/api/canvas/oauth/callback`) |
| `CANVAS_STATE_SECRET` | Signing key for OAuth state JWT (32+ random bytes) |

</details>

<details>
<summary><strong>Frontend</strong> (<code>frontend/.env.local</code>)</summary>

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_API_URL` | Backend API URL (default: `http://localhost:8000/api`) |
| `NEXT_PUBLIC_CANVAS_ENABLED` | Show the Canvas LMS connect UI in the dashboard |
| `NEXT_PUBLIC_MICROSOFT_SSO_ENABLED` | Show the Microsoft SSO option on the sign-in page |
| `BETTER_AUTH_SECRET` | Better Auth signing secret (used by the Next.js `auth` handler) |
| `BETTER_AUTH_URL` | Public origin for Better Auth (e.g. `http://localhost:3000`) |
| `BETTER_AUTH_INTERNAL_SECRET` | Must match the backend value — used by the signup hook posting to the backend |
| `DATABASE_URL` | Same Postgres as the backend — Better Auth tables live in the `auth` schema |
| `RESEND_API_KEY` | Resend key for verification + password-reset email |

</details>

<br/>

---

<br/>

## API Reference

All endpoints are prefixed with `/api` and require `Authorization: Bearer <better_auth_jwt>` except `/health`. The token is fetched by the frontend `useApiToken` hook via `authClient.token()` and verified server-side against the Better Auth JWKS (`BETTER_AUTH_JWKS_URL`).

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
| `POST` | `/api/speech/grade` | Enrolled | Grade pronunciation (upload audio + reference text + optional `pronunciation_item_id` to feed concept mastery) |
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

<details>
<summary><strong>Concepts & Mastery (Adaptive Engine — Phase 2)</strong></summary>

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` `GET` `PUT` `DELETE` | `/api/courses/:id/concepts[/:cid]` | Instructor | Concept CRUD (course-scoped, soft-merge via `canonical_id`) |
| `POST` | `/api/courses/:id/concepts/extract` | Instructor | Enqueue LLM extraction across course chunks |
| `POST` | `/api/courses/:id/concepts/replay` | Instructor | Trigger 90-day attempt-history replay (409 if in-flight) |
| `POST` `GET` `DELETE` | `/api/courses/:id/concept-prerequisites[/:p/:d]` | Instructor | Prerequisite DAG with cycle detection at write |
| `GET` `POST` | `/api/courses/:id/concept-clusters[/:cluster_id/decide]` | Instructor | Cluster review queue: approve / rename / merge / reject |
| `GET` | `/api/concept-tags/:target_kind/:target_id` | Enrolled | Read concept tags for any tagged artifact |
| `GET` | `/api/users/me/courses/:id/mastery` | Enrolled | Personal per-concept mastery (α, β, mastery_score, confidence) |
| `GET` | `/api/courses/:id/mastery` | Instructor | Cohort mastery view across all enrolled students |

</details>

<details>
<summary><strong>Decision Layer (Adaptive Engine — Phase 3)</strong></summary>

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/users/me/courses/:id/next-actions` | Enrolled | Top-10 ranked actions (lazy 30-min recompute) |
| `POST` | `/api/next-actions/:id/click` | Enrolled | Record a click — produces `action_outcomes` row tagged with the served `engine_variant` |
| `GET` | `/api/courses/:id/alerts` | Instructor | List active instructor alerts |
| `PATCH` | `/api/courses/:id/alerts/:aid` | Instructor | Dismiss / resolve an alert |
| `GET` `PATCH` | `/api/courses/:id/engine` | Instructor | Read / set course engine mode (`on` / `off` / `random_50`) |
| `PUT` `DELETE` | `/api/courses/:id/engine/overrides/:user_id` | Instructor | Per-user override (`on` / `off` only) |

</details>

<br/>

---

<br/>

## Project Structure

```
meli/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app + lifespan (worker + Canvas scheduler)
│   │   ├── config.py            # pydantic-settings from .env
│   │   ├── database.py          # SQLAlchemy async engine
│   │   ├── api/                 # Route handlers
│   │   │   ├── deps.py          #   get_current_user, require_instructor, get_owned_course
│   │   │   ├── internal.py      #   Better Auth signup hook → users link/delete
│   │   │   ├── rag.py           #   RAG query + generation endpoints
│   │   │   ├── courses.py, documents.py, quizzes.py, flashcards.py
│   │   │   ├── revision.py      #   Adaptive revision sessions (bandit)
│   │   │   ├── recalibration.py #   Difficulty recalibration (Dirichlet/HMM)
│   │   │   ├── live.py          #   Live quiz (WebSocket + REST)
│   │   │   ├── speech.py, pronunciation.py   # Pronunciation grading + sets
│   │   │   ├── analytics.py, progress.py     # Instructor analytics + gamification
│   │   │   ├── canvas.py, canvas_oauth.py    # Canvas LMS + per-user OAuth
│   │   │   │
│   │   │   │ ── Adaptive Engine — Phase 1 (curriculum spine)
│   │   │   ├── modules.py, meetings.py, objectives.py, assignments.py
│   │   │   ├── syllabus.py      #   LLM parse → review → transactional apply
│   │   │   │
│   │   │   │ ── Adaptive Engine — Phase 2 (concepts + mastery)
│   │   │   ├── concepts.py, concept_prerequisites.py
│   │   │   ├── concept_clusters.py, concept_tags.py
│   │   │   ├── mastery.py       #   Personal + cohort mastery views
│   │   │   │
│   │   │   │ ── Adaptive Engine — Phase 3 (decision layer)
│   │   │   ├── next_actions.py        # Today: top-10 ranked actions + clicks
│   │   │   ├── instructor_alerts.py   # Alerts centre (dismiss / resolve)
│   │   │   └── engine_settings.py     # Mode + per-user overrides (A/B)
│   │   ├── models/              # SQLAlchemy 2.0 models
│   │   │   ├── base.py          #   UUID PK, timestamps, soft delete mixins
│   │   │   ├── user.py          #   User, Course, Enrollment
│   │   │   ├── document.py, chunk.py    #   Document + Chunk (vector + tsvector)
│   │   │   ├── quiz.py, flashcard.py, revision.py, recalibration.py
│   │   │   ├── live_answer.py, session.py, summary.py
│   │   │   ├── score.py, pronunciation.py   # Gamification + pronunciation
│   │   │   ├── task.py, cron_run.py, api_usage.py, oauth_nonce.py
│   │   │   ├── integration.py, canvas.py    # Canvas integration + creds
│   │   │   ├── scheduler.py     #   FSRS scheduler state
│   │   │   ├── curriculum.py    #   Phase 1: modules, meetings, objectives, assignments, syllabus_imports
│   │   │   ├── concept.py       #   Phase 2: concepts, prereqs, tags, mastery (+history)
│   │   │   └── decision.py      #   Phase 3: next_actions, action_outcomes, instructor_alerts, engine_overrides
│   │   ├── schemas/             # Pydantic v2 request/response models
│   │   ├── services/            # Business logic
│   │   │   ├── pipeline.py      #   download → parse → chunk → embed → store
│   │   │   ├── worker.py        #   PostgreSQL task-queue consumer + cron blocks
│   │   │   ├── jobs.py          #   Task dispatch + watermarks
│   │   │   ├── parser.py        #   Docling + Whisper dispatch
│   │   │   ├── vlm.py           #   Vision-LLM captions + low-text page rescue
│   │   │   ├── chunker.py, embedder.py, retriever.py, generator.py
│   │   │   ├── bandit.py        #   REINFORCE contextual bandit
│   │   │   ├── pool.py, recalibrator.py     # Revision pool + Dirichlet recalibrator
│   │   │   ├── live_quiz.py, gamification.py, speech.py
│   │   │   ├── storage.py       #   Cloudflare R2 via boto3
│   │   │   ├── auth.py          #   Better Auth JWT verification + role detection
│   │   │   ├── crypto.py, url_safety.py     # Fernet token encryption + SSRF guard
│   │   │   ├── canvas_client.py, canvas_oauth.py, canvas_files.py
│   │   │   ├── canvas_roster.py, canvas_sync.py    # Daily scheduler + roster diff
│   │   │   ├── scheduler.py     #   FSRS-5 scheduler
│   │   │   │
│   │   │   │ ── Adaptive Engine — Phase 1
│   │   │   ├── syllabus.py, syllabus_grounding.py
│   │   │   │
│   │   │   │ ── Adaptive Engine — Phase 2
│   │   │   ├── concept_extraction.py, concept_clustering.py, concept_tagger.py
│   │   │   ├── mastery.py       #   Beta-Binomial update + HLR decay
│   │   │   │
│   │   │   │ ── Adaptive Engine — Phase 3
│   │   │   ├── outer_fringe.py  #   KST candidate filter (CTE)
│   │   │   ├── scoring.py, action_coeffs.py    # Per-action-type scoring + tunable coeffs
│   │   │   ├── next_actions.py  #   Materialiser + lazy/event-driven recompute
│   │   │   ├── alerts.py        #   7-rule evaluator
│   │   │   ├── engine_mode.py   #   on/off/random_50 resolver (blake2b A/B)
│   │   │   └── adaptive_jobs.py #   Phase 3 task handlers
│   │   └── middleware/          # ASGI middleware
│   │       ├── auth.py          #   Bearer token gate on /api/*
│   │       ├── rate_limit.py    #   Per-user hourly limits on /api/rag/*
│   │       └── security_headers.py
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
│   │   │   ├── dashboard/courses/[courseId]/
│   │   │   │   ├── quizzes/, flashcards/, revision/, pronunciation/, live/
│   │   │   │   ├── modules/, meetings/, objectives/, assignments/, syllabus/   # Phase 1
│   │   │   │   ├── concepts/, concept-curation/, prerequisites/, mastery/       # Phase 2
│   │   │   │   └── today/, alerts/, engine/                                     # Phase 3
│   │   │   ├── sign-in/, sign-up/   # Better Auth screens (custom components)
│   │   │   └── api/auth/[...all]/   # Better Auth handler (JWKS, sessions, hooks)
│   │   ├── components/          # Feature-organized
│   │   │   ├── auth/            #   Sign-in / sign-up forms
│   │   │   ├── course/, documents/, quiz/, flashcard/, folders/, generation/
│   │   │   ├── revision/, live-quiz/, pronunciation/, summary/
│   │   │   ├── analytics/, gamification/, recalibration/
│   │   │   ├── curriculum/      #   Phase 1: modules/meetings/objectives/assignments/syllabus
│   │   │   ├── concepts/        #   Phase 2: concept CRUD, clusters, prereq DAG, mastery
│   │   │   ├── decision/        #   Phase 3: today, alerts centre, engine settings
│   │   │   ├── canvas/, dashboard/, providers/, layout/, ui/
│   │   ├── hooks/               # Custom hooks (TanStack Query wrappers)
│   │   │   ├── use-api-token.ts, use-auth.ts, use-role.ts
│   │   │   ├── use-courses.ts, use-documents.ts, use-quizzes.ts, use-flashcard-sets.ts
│   │   │   ├── use-revision.ts, use-recalibration.ts, use-live-quiz.ts
│   │   │   ├── use-pronunciation*.ts, use-canvas.ts, use-progress.ts, use-analytics.ts
│   │   │   ├── use-modules.ts, use-meetings.ts, use-objectives.ts, use-assignments.ts
│   │   │   ├── use-assignment-submissions.ts, use-calendar-events.ts, use-syllabus.ts
│   │   │   ├── use-concepts.ts, use-concept-prerequisites.ts, use-concept-clusters.ts
│   │   │   ├── use-concept-tags.ts, use-mastery.ts
│   │   │   └── use-next-actions.ts, use-todos.ts, use-instructor-alerts.ts, use-engine-settings.ts
│   │   ├── lib/api.ts           # Typed fetch wrapper with Better Auth Bearer token
│   │   ├── lib/auth-client.ts   # Better Auth client (token, session, sign-in/out)
│   │   ├── proxy.ts             # Next.js 16 proxy (replaces middleware.ts)
│   │   └── styles/tokens.css    # Design tokens (oklch, "Honey & Salt" palette)
│   ├── e2e/                     # Playwright tests
│   └── package.json
│
├── docs/
│   ├── superpowers/             # Design specs + implementation plans (Phase 1/2/3)
│   ├── migrations/              # Migration playbooks (Clerk → Better Auth)
│   └── compliance/
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
- **Concept ontology** per-course in `concepts` with `canonical_id` soft-merge + `cluster_id` for curation; `vector(3072)` embedding column matches `text-embedding-3-large` native dim
- **Prerequisite DAG** in `concept_prerequisites` with cycle detection enforced at write via `WITH RECURSIVE`
- **Polymorphic concept tags** in `concept_tags(target_kind, target_id, concept_id, weight)` with partial indexes per kind; `target_kind` covers `chunk | question | flashcard_card | pool_item | pronunciation_item | objective | meeting | assignment`
- **Beta-Binomial mastery** in `concept_mastery (user_id, concept_id)` with `α`, `β` pseudo-counts and a `GENERATED ALWAYS AS (α/(α+β)) STORED` `mastery_score` column; full audit trail in `concept_mastery_history`
- **Decision layer** in `next_actions` (materialised, TTL 1h, polymorphic `target_id`), `action_outcomes` (per-impression telemetry with `engine_variant`, `next_action_id` `ON DELETE SET NULL`), `instructor_alerts` (rule + severity + status), `engine_overrides` (per-user) and `courses.adaptive_engine_mode ∈ {on, off, random_50}`
- **Pronunciation → mastery FK** in `pronunciation_scores.pronunciation_item_id` (nullable, `ON DELETE SET NULL`) so set-based pronunciation attempts feed `update_concept_mastery` while free-form practice still works

### Schema Diagram

```
                                    +---------------+
                                    |     users     |
                                    | (Better Auth) |
                                    +-------+-------+
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

              +------------- Adaptive Engine — Phase 1/2/3 -----------------+
              |                                                             |
              |  course_modules ── course_meetings ── learning_objectives   |
              |       │                                                     |
              |  assignments ── assignment_submissions   syllabus_imports   |
              |                                                             |
              |  concepts ── concept_prerequisites (DAG)                    |
              |     │                                                       |
              |  concept_tags (polymorphic: chunk | question | flashcard_   |
              |     │         card | pool_item | pronunciation_item |       |
              |     │         objective | meeting | assignment)             |
              |     │                                                       |
              |  concept_mastery (α, β, mastery_score GENERATED) ─          |
              |     │   concept_mastery_history (append-only audit)         |
              |     │                                                       |
              |  next_actions (materialised cache, TTL 1h)                  |
              |     │                                                       |
              |  action_outcomes (engine_variant: on | off, A/B telemetry)  |
              |                                                             |
              |  instructor_alerts ── engine_overrides                      |
              +-------------------------------------------------------------+
```

### Core Tables

<details>
<summary><strong>Identity & Enrollment</strong></summary>

| Table | Columns | Notes |
|-------|---------|-------|
| **users** | `id` (uuid PK), `better_auth_id` (unique), `email` (unique), `full_name`, `role`, `avatar_url`, `created_at`, `updated_at` | Auto-created on first Better Auth JWT (or via the `POST /api/internal/users/link` signup hook). Role derived from email domain. |
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

Authentication is handled by **self-hosted Better Auth** running inside the Next.js app. Better Auth's tables (`user`, `session`, `account`, `verification`, `jwks`) live in the `auth` schema of the same Postgres as the backend; the JWT plugin issues EdDSA (Ed25519) tokens signed by keys it rotates itself and publishes a JWKS at `/api/auth/jwks`.

1. **Frontend session + token fetch** — `frontend/src/lib/auth-client.ts` wraps the Better Auth client; the `useApiToken` hook calls `authClient.token()` to mint a fresh JWT for each backend request. Route protection lives in `frontend/src/proxy.ts` (Next.js 16's replacement for `middleware.ts`).
2. **Middleware** ([`middleware/auth.py`](backend/app/middleware/auth.py)) — cheap Bearer-token presence check on `/api/*` paths.
3. **Dependency** ([`api/deps.py`](backend/app/api/deps.py)) — `get_current_user` verifies the JWT against `BETTER_AUTH_JWKS_URL` via `PyJWKClient`, checks issuer / audience, then upserts a row in `public.users` keyed on `better_auth_id`.
4. **Signup hook** — Better Auth's `databaseHooks.user.create.after` fires `POST /api/internal/users/link` (guarded by `BETTER_AUTH_INTERNAL_SECRET`) so the local `users` row is created atomically with the auth-schema row.
5. **Role detection** — email domain determines role: `ust.hk` = instructor, `connect.ust.hk` = student (configurable via `ALLOWED_EMAIL_DOMAINS`).
6. **Enforcement** — `require_instructor` dependency blocks students from admin endpoints; per-course ownership checks (`get_owned_course`) gate cross-course access.

The full migration history (Clerk → Better Auth) lives at [`docs/migrations/clerk-to-better-auth.md`](docs/migrations/clerk-to-better-auth.md).

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
| **3b** Adaptive Engine — Phase 2 | Done | Concepts knowledge graph + prerequisite DAG with cycle check, Beta-Binomial mastery + HLR forgetting decay, polymorphic concept tags, LLM extract → cluster → instructor curation, syllabus-as-generation-context, 90-day attempt replay, pronunciation→mastery FK |
| **3c** Adaptive Engine — Phase 3 | Done | KST outer-fringe `next_actions` ranking + scoring, lazy 30-min recompute + event-driven rebuild, daily horizon-scan cron, 7-rule instructor alerts, `action_outcomes` telemetry with `engine_variant`, course mode (`on`/`off`/`random_50`) + per-user overrides, quarterly coefficient retune (propose-only) |
| **4** Planned | Planned | i18n (Traditional Chinese), Canvas LMS deeper integration, pre-class meeting briefings (cohort-weakness → upcoming session), `student_daily_briefings` rich-card variant of Today |

<br/>

---

<br/>

## License

This project is developed for HKUST's Center for Language Education.

<br/>
