# Meli — Personalized Difficulty Adapter Design Specification

**Date:** 2026-04-08
**Status:** Draft
**Parent Spec:** [CLE Platform Design](2026-04-05-cle-platform-design.md)

---

## 1. Overview

A contextual bandit system that personalizes the difficulty level of quiz questions, flashcards, and speaking prompts served to each student during revision sessions. Instead of serving content at a fixed difficulty, it learns per-student which difficulty level to serve next to maximize learning outcomes over time. Runs entirely inside the FastAPI backend with zero LLM API calls for inference and training.

### What it is NOT

- Not a modification to existing quiz or flashcard flows — those remain unchanged
- Not an LLM feature — the bandit itself is pure PyTorch/NumPy
- Not a batch training system — updates happen online after every single attempt

## 2. Revision Session — New Third Practice Mode

Revision is a new infinite-practice mode alongside existing quizzes (instructor-curated, taken as a unit) and flashcards (SM-2 spaced repetition within a set). In revision mode:

- Students choose a content type (quiz, flashcard, or speaking) and practice indefinitely
- Items are generated fresh specifically for revision — never recycled from existing quizzes or flashcard sets
- The bandit selects difficulty for each item based on the student's history
- After each answer, the student sees immediate feedback, then the next item is served automatically
- When the pool of unserved items runs low, new items are generated asynchronously in the background
- Gamification (combos, lives, score attack, etc.) is deferred to a later phase — the current scope is functional infinite practice with adaptive difficulty

## 3. Critical Dependencies — Current State

### 3a. Difficulty Labels — Not Present

Neither the database schema nor the generation pipeline currently supports difficulty:

- `questions` table: no difficulty column (`models/quiz.py:35-54`)
- `flashcard_cards` table: no difficulty column (`models/flashcard.py:32-48`)
- `GeneratedQuestion` dataclass: no difficulty field (`services/generator.py:24-28`)
- LLM prompt: does not request difficulty classification (`services/generator.py:116-125`)

**Resolution:** Add a nullable `difficulty VARCHAR(10) DEFAULT 'medium'` column to both tables. Existing rows get `medium` (they aren't used by revision mode). New revision-specific generation functions produce difficulty-labeled content.

### 3b. Per-Item Attempt History — Wrong Granularity

- `QuizAttempt` logs per-quiz aggregate scores, not per-question performance with difficulty awareness (`models/quiz.py:68-85`)
- `FlashcardProgress` tracks SM-2 running state, not per-attempt history (`models/flashcard.py:64-81`)
- `StudentProgress` tracks course-level counts only (`models/score.py:36-54`)

**Resolution:** New `revision_attempts` table with one row per (student, item, timestamp, difficulty, score).

## 4. Database Schema

### 4a. Column Additions to Existing Tables

```sql
ALTER TABLE questions ADD COLUMN difficulty VARCHAR(10) NOT NULL DEFAULT 'medium';
ALTER TABLE flashcard_cards ADD COLUMN difficulty VARCHAR(10) NOT NULL DEFAULT 'medium';
```

Values: `easy`, `medium`, `hard`. Existing rows default to `medium`. Revision mode generates its own pool — these columns are for future use by regular quizzes.

### 4b. `revision_pool_items` — Content Pool

Dedicated pool for revision content, separate from instructor-curated quizzes and flashcard sets.

```sql
CREATE TABLE revision_pool_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id       UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    content_type    VARCHAR(20) NOT NULL,  -- 'quiz', 'flashcard', 'speaking'
    difficulty      VARCHAR(10) NOT NULL,  -- 'easy', 'medium', 'hard'

    -- Quiz fields (NULL when content_type != 'quiz')
    question_text   TEXT,
    options         JSONB,
    correct_answer  VARCHAR(10),
    explanation     TEXT,

    -- Flashcard fields (NULL when content_type != 'flashcard')
    front           TEXT,
    back            TEXT,

    -- Speaking fields (NULL when content_type != 'speaking')
    target_text     TEXT,
    language        VARCHAR(20),

    source_chunk_id UUID REFERENCES chunks(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_revision_pool_course_type_diff
    ON revision_pool_items (course_id, content_type, difficulty);
```

### 4c. `revision_attempts` — Per-Item Attempt History

One row per item answered. The bandit's training data.

```sql
CREATE TABLE revision_attempts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    course_id       UUID NOT NULL REFERENCES courses(id),
    session_id      UUID NOT NULL REFERENCES revision_sessions(id) ON DELETE CASCADE,
    pool_item_id    UUID NOT NULL REFERENCES revision_pool_items(id),
    content_type    VARCHAR(20) NOT NULL,
    difficulty      VARCHAR(10) NOT NULL,  -- denormalized for fast queries
    score           NUMERIC(3,2) NOT NULL, -- 0.00 to 1.00
    time_taken_ms   INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_revision_attempts_state_vector
    ON revision_attempts (user_id, course_id, content_type, created_at DESC);
```

### 4d. `bandit_models` — Per-Student Model Persistence

```sql
CREATE TABLE bandit_models (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    course_id       UUID NOT NULL REFERENCES courses(id),
    content_type    VARCHAR(20) NOT NULL,  -- 'quiz', 'flashcard', 'speaking'
    weights         BYTEA NOT NULL,        -- serialized PyTorch state_dict
    strategy        VARCHAR(10) NOT NULL DEFAULT 'rules',  -- 'rules' or 'bandit'
    reward_mean     FLOAT NOT NULL DEFAULT 0.0,
    reward_var      FLOAT NOT NULL DEFAULT 1.0,
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (user_id, course_id, content_type)
);
```

### 4e. `revision_item_served` — Deduplication Tracking

Prevents a student from seeing the same item twice.

```sql
CREATE TABLE revision_item_served (
    user_id         UUID NOT NULL REFERENCES users(id),
    pool_item_id    UUID NOT NULL REFERENCES revision_pool_items(id) ON DELETE CASCADE,
    served_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (user_id, pool_item_id)
);
```

### 4f. `revision_sessions` — Session Tracking

```sql
CREATE TABLE revision_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    course_id       UUID NOT NULL REFERENCES courses(id),
    content_type    VARCHAR(20) NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    items_answered  INTEGER NOT NULL DEFAULT 0,
    total_score     NUMERIC(7,2) NOT NULL DEFAULT 0
);
```

## 5. Generation Pipeline

### 5a. Difficulty-Aware Generation Functions

New functions in `services/generator.py`, alongside existing ones (existing functions are not modified):

```python
async def generate_revision_quiz(
    chunks: list[RetrievedChunk],
    difficulty: str,          # "easy" | "medium" | "hard"
    num_questions: int = 7,
    language: str = "english",
) -> list[GeneratedQuestion]

async def generate_revision_flashcards(
    chunks: list[RetrievedChunk],
    difficulty: str,
    num_cards: int = 7,
    language: str = "english",
) -> list[GeneratedFlashcard]

async def generate_revision_speaking(
    chunks: list[RetrievedChunk],
    difficulty: str,
    num_items: int = 6,
    language: str = "english",
) -> list[GeneratedSpeakingTarget]
```

### 5b. Difficulty Definitions in LLM Prompts

| Difficulty | Quiz | Flashcard | Speaking |
|-----------|------|-----------|---------|
| Easy | Direct recall, definitions, simple facts from the text | Basic term → definition | Short simple sentences, common vocabulary |
| Medium | Application, comparison, connecting two concepts | Conceptual understanding, paraphrased answers | Compound sentences, moderate vocabulary |
| Hard | Analysis, inference, synthesis across multiple ideas | Nuanced application, edge cases, subtle distinctions | Complex paragraphs, technical/difficult vocabulary |

### 5c. Batch Generation Strategy

When the pool needs replenishment, a single task generates a balanced batch per content type:

- `generate_revision_*(difficulty="easy", num=7)`
- `generate_revision_*(difficulty="medium", num=7)`
- `generate_revision_*(difficulty="hard", num=6)`

All three run concurrently via `asyncio.gather`. Total: 20 items per batch.

### 5d. Worker Integration

New task type `revision_pool_replenish` handled by the existing `worker.py` polling loop. Payload:

```json
{
    "course_id": "...",
    "content_type": "quiz",
    "counts": {"easy": 7, "medium": 7, "hard": 6}
}
```

## 6. Bandit Architecture

### 6a. Policy Network

Small PyTorch MLP. Per-student, per-course, per-content-type.

```
Input (state vector, dim 10) → Linear(10, 32) → ReLU → Linear(32, 3) → Softmax
                                                                         ↓
                                                        P(easy), P(medium), P(hard)
```

387 parameters. Serializes to ~2-3 KB.

Final layer initialized for near-uniform output:
- `nn.init.normal_(fc2.weight, std=0.01)`
- `nn.init.zeros_(fc2.bias)`

### 6b. State Vector

Computed fresh from `revision_attempts` rows in NumPy at every decision point. Never cached.

| Index | Feature | Description |
|-------|---------|-------------|
| 0 | avg_score_easy | Mean score on easy items (last 50 attempts) |
| 1 | avg_score_medium | Mean score on medium items (last 50 attempts) |
| 2 | avg_score_hard | Mean score on hard items (last 50 attempts) |
| 3 | recent_score_easy | Exponentially decayed mean, λ=0.9, last 20 attempts |
| 4 | recent_score_medium | Same for medium |
| 5 | recent_score_hard | Same for hard |
| 6 | attempt_count_norm | Total attempts / 100, capped at 1.0 |
| 7 | streak_signal | Consecutive correct / 10, capped at 1.0 |
| 8 | session_gap | Days since last attempt / 30, capped at 1.0 |
| 9 | current_session_progress | Items this session / 20, capped at 1.0 |

All features normalized to [0, 1]. Missing difficulty data defaults to 0.5 (neutral prior).

### 6c. Training — REINFORCE with Entropy Regularization

After each attempt:

1. Score the answer → reward `r` ∈ [0.0, 1.0]
2. Update running statistics (always, from attempt 1):
   - `mean ← 0.99 × mean + 0.01 × r`
   - `var ← 0.99 × var + 0.01 × (r − mean)²`
3. Normalize reward (only after cold start threshold):
   - `r_norm = (r − mean) / √(var + 1e-8)`
   - Before threshold: use raw `r`
4. Compute loss:
   - `loss = −log π(chosen | state) × r_norm − 0.01 × H(π(· | state))`
   - Where H is the entropy of the policy distribution
5. Single SGD step, lr=0.01
6. Gradient clipping: `clip_grad_norm_(params, max_norm=1.0)`
7. Serialize updated `state_dict` → write to `bandit_models.weights`

### 6d. Cold Start — Rule-Based Fallback

Active when `attempt_count < 20` (the cold start threshold).

Rules:
- Start at medium
- Two consecutive scores ≥ 0.8 at current difficulty → move up one level
- Any score < 0.5 → move down one level
- Clamp to [easy, hard]

Current rule-based difficulty is derived from the last few `revision_attempts` rows — no extra storage.

### 6e. Safety Net

The cold start rules also act as a permanent safety net. If the bandit outputs a degenerate distribution (>90% probability on one difficulty for 5+ consecutive items), override with the rule-based selection for the next item.

### 6f. Dual Strategy Design

Both rule-based and bandit systems are first-class strategies, not one as a fallback for the other. The `bandit_models.strategy` column (`'rules'` or `'bandit'`) explicitly tracks which strategy is active for each (user, course, content_type). Transitions from `'rules'` to `'bandit'` happen automatically when `attempt_count` crosses the cold start threshold (20). Manual override via admin is possible for A/B testing. This enables:

- Shipping the rule-based system first for immediate value
- Gradual bandit rollout as data accumulates
- A/B testing using the attempt data already being logged
- Clean fallback if the bandit underperforms

## 7. Reward Signals by Content Type

| Content Type | Score Derivation | Range |
|-------------|-----------------|-------|
| Quiz | 1.0 if correct, 0.0 if incorrect | Binary |
| Flashcard | Self-rated recall mapped: Again→0.0, Hard→0.4, Good→0.7, Easy→1.0 | [0.0, 1.0] |
| Speaking | Pronunciation grade overall_score / 100 | [0.0, 1.0] |

Each content type has independent model weights, state vectors, and attempt histories. A student's quiz difficulty and speaking difficulty evolve independently.

## 8. Pool Management

### 8a. Pre-warmed Pool (Approach C)

Content generation is fully decoupled from serving:

1. When a student starts a revision session, check pool levels via `ensure_pool()`
2. If the pool has sufficient unserved items across all difficulties: serve immediately
3. If the pool is empty (first-ever session): enqueue generation task, show "Preparing your session..." (~5-8s)
4. Pool items persist across sessions — the student never sees the same item twice (tracked via `revision_item_served`)
5. Pool grows over time, reducing generation frequency

### 8b. Replenishment Trigger

When unserved items at any difficulty drop below 5 for a (course, content_type), enqueue a `revision_pool_replenish` task. Checked after every `/answer` call.

### 8c. Pool Insufficiency at Selected Difficulty

If the bandit selects "hard" but no unserved hard items remain:
1. Redistribute probability across available difficulties and resample
2. Trigger async replenishment for the depleted difficulty
3. Never block the student

## 9. API Endpoints

New router: `backend/app/api/revision.py`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/courses/{id}/revision/start` | enrolled | Start revision session |
| POST | `/api/revision/sessions/{id}/next` | session owner | Get next item (skip) |
| POST | `/api/revision/sessions/{id}/answer` | session owner | Submit answer → feedback + next item |
| GET | `/api/revision/sessions/{id}` | session owner | Session state |
| POST | `/api/revision/sessions/{id}/end` | session owner | End session → summary |

### 9a. `POST /start` — Start Session

Request:
```json
{"content_type": "quiz"}
```

Response:
```json
{
    "session_id": "...",
    "status": "ready",      // or "preparing" if pool is generating
    "first_item": { ... }   // null if preparing
}
```

### 9b. `POST /answer` — Core Loop

This is the hot path. A single request performs: scoring → attempt logging → policy update → next item selection.

Request:
```json
{
    "pool_item_id": "...",
    "answer": "B",           // quiz: option letter
    "quality": 4,            // flashcard: SM-2 quality 0-5
    "time_taken_ms": 3200
}
```

Response:
```json
{
    "score": 1.0,
    "is_correct": true,
    "correct_answer": "B",
    "explanation": "...",
    "xp_earned": 100,
    "next_item": {
        "pool_item_id": "...",
        "content_type": "quiz",
        "question_text": "...",
        "options": {"A": "...", "B": "...", "C": "...", "D": "..."}
    },
    "session_stats": {
        "items_answered": 12,
        "accuracy": 0.75,
        "current_streak": 3
    }
}
```

### 9c. Latency Budget

| Step | Estimated Time |
|------|---------------|
| Score answer | ~0ms |
| INSERT attempt row | ~2ms |
| INSERT served row | ~1ms |
| SELECT last 50 attempts + compute state vector | ~3ms |
| PyTorch forward + backward + step (387 params) | ~0.1ms |
| UPDATE bandit_models weights | ~2ms |
| SELECT next pool item | ~2ms |
| **Total** | **~10ms** |

## 10. Frontend

### 10a. New Route

```
/dashboard/courses/[courseId]/revision
```

Accessed via a "Revision" tab on the course detail page.

### 10b. Page Flow

```
Choose content type (Quiz / Flashcard / Speaking)
  → POST /start
  → If "preparing": loading spinner
  → Practice loop:
      → Display item
      → Student answers
      → POST /answer
      → Show feedback (correct/incorrect, explanation, score)
      → Auto-advance to next item (~1.5s pause)
      → Repeat until student clicks "End Session"
  → POST /end → Session summary card
```

### 10c. Components

```
frontend/src/components/revision/
├── content-type-picker.tsx    -- Three cards: Quiz, Flashcard, Speaking
├── revision-player.tsx        -- Main loop container
├── quiz-item.tsx              -- Question + answer buttons
├── flashcard-item.tsx         -- Flip card with self-rating
├── speaking-item.tsx          -- Target text + recorder + score
├── item-feedback.tsx          -- Correct/incorrect overlay
├── session-stats-bar.tsx      -- Items answered, accuracy, streak
└── session-summary.tsx        -- End-of-session results
```

### 10d. Hook

```typescript
useRevisionSession(courseId, contentType)
  → { currentItem, submitAnswer, endSession, stats, isLoading, isPreparing }
```

### 10e. UX Decisions

- **No difficulty labels shown to students.** Difficulty is an internal signal. Showing it creates anxiety on "hard" items and gaming on "easy" items.
- **Immediate feedback** after each answer (correct/incorrect + explanation), then auto-advance.
- **Session stats bar** always visible: items answered, running accuracy %, current consecutive-correct streak.
- **Flashcard scoring** uses the same 4-button UI as existing flashcard player (Again/Hard/Good/Easy), mapped to reward values 0.0/0.4/0.7/1.0.
- **Speaking scoring** uses the pronunciation grade endpoint from Phase 2c.

## 11. Integration Points

### 11a. Purely Additive (New Files)

| File | Purpose |
|------|---------|
| `backend/app/services/bandit.py` | Policy network, state vector, training, pool management |
| `backend/app/api/revision.py` | All revision endpoints |
| `backend/app/schemas/revision.py` | Request/response schemas |
| `backend/app/models/revision.py` | RevisionSession, RevisionPoolItem, RevisionAttempt, RevisionItemServed, BanditModel |
| `backend/alembic/versions/xxxx_revision.py` | Migration for all new tables + difficulty columns |
| `backend/tests/test_bandit.py` | Bandit unit tests (state vector, REINFORCE, cold start) |
| `backend/tests/test_api_revision.py` | Endpoint integration tests |
| `frontend/src/hooks/use-revision.ts` | Session lifecycle hook |
| `frontend/src/components/revision/*.tsx` | All revision UI components |
| `frontend/src/app/dashboard/courses/[courseId]/revision/page.tsx` | Revision page |

### 11b. Modifications to Existing Code

| File | Change | Risk |
|------|--------|------|
| `backend/app/models/quiz.py` | Add `difficulty` column to `Question` | Low — nullable with default |
| `backend/app/models/flashcard.py` | Add `difficulty` column to `FlashcardCard` | Low — same |
| `backend/app/services/generator.py` | Add 3 new `generate_revision_*` functions | Low — additive, existing functions untouched |
| `backend/app/services/worker.py` | Add `revision_pool_replenish` task handler | Low — one new elif branch |
| `backend/app/api/__init__.py` | Register revision router | Trivial |
| `backend/requirements.txt` | Add `torch` (CPU-only) | Medium — large dependency |
| `frontend/src/app/dashboard/courses/[courseId]/page.tsx` | Add "Revision" tab | Low — additive |
| `frontend/src/components/layout/sidebar.tsx` | Add revision nav link | Trivial |

### 11c. Zero Impact on Existing Flows

The regular quiz flow, flashcard SM-2 flow, RAG generation, and all other existing functionality remain completely untouched. Revision is a parallel system sharing the same database and generation infrastructure.

## 12. Implementation Order

```
Migration (tables + columns)
  → generator.py (revision generation functions)
  → worker.py (pool replenishment handler)
  → bandit.py (policy + state vector + pool management)
  → revision.py API endpoints + schemas
  → Frontend (hook + components + page)
```

Each step is independently testable.

## 13. New Dependencies

```
# Backend (add to requirements.txt)
torch (CPU-only, installed via --index-url https://download.pytorch.org/whl/cpu)
# numpy — already present transitively
```

No new frontend dependencies.

## 14. Testing Strategy

| Area | Test Type | What |
|------|-----------|------|
| State vector | Unit | Verify 10-dim output from known attempt histories |
| Cold start rules | Unit | Threshold transitions, clamping, edge cases |
| REINFORCE update | Unit | Gradient direction, weight change, entropy bonus |
| Policy initialization | Unit | Verify near-uniform output on fresh model |
| Safety net | Unit | Degenerate distribution detection triggers fallback |
| Pool management | Integration | Replenishment trigger, deduplication, insufficiency handling |
| Revision generation | Integration | Difficulty-aware prompts produce labeled content |
| `/start` endpoint | Integration | Session creation, pool check, first item served |
| `/answer` endpoint | Integration | Full loop: score → train → next item |
| `/end` endpoint | Integration | Session summary, stats accuracy |
| Frontend flow | E2E (Playwright) | Start session → answer 3 items → end → summary |

Coverage target: 80%+ on all new services and endpoints.

## 15. Future Extensions (Post-Ship)

These features build on the infrastructure established here:

### 15a. Difficulty Recalibration

A supervised classifier trained on `revision_attempts` data that recalibrates LLM-assigned difficulty labels based on actual student performance. If 95% of students get a "medium" question right, it's actually "easy." Uses the same `bandit_models` persistence pattern.

### 15b. Neural Spaced Repetition (SM-2 Replacement)

A small network that learns personalized review intervals from `flashcard_progress` + `revision_attempts` data, replacing the fixed SM-2 constants. Predicts recall probability as a function of time since last review, repetition count, difficulty, and student state. Same model persistence infrastructure.

### 15c. Gamification Layer

Deferred game mechanics for the revision session: score attack with combo multipliers, timed challenge mode, progression/survival with lives, or a combination. The `revision_sessions` and `revision_attempts` tables already capture all data needed. Purely additive frontend + API work.
