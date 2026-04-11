# Meli — Difficulty Recalibration Design Specification

**Date:** 2026-04-11
**Status:** Draft
**Parent Spec:** [Difficulty Adapter](2026-04-08-cle-difficulty-adapter.md) (Feature 15a)

---

## 1. Overview

A hierarchical Bayesian classifier that recalibrates LLM-assigned difficulty labels on revision pool items using actual student performance data. The LLM generates content with consistent prompts — the classifier observes how students perform and re-tags items to their true difficulty.

Two layers:
- **Course-level Dirichlet prior:** Learns systematic LLM bias per (course, content_type) as a 3x3 transition matrix
- **Item-level Beta posterior:** Each pool item refines its label using the course prior + its own attempt stats

Runs as a batch job on the existing worker queue, triggered every ~50 attempts per (course, content_type). Pure NumPy — no additional ML training infrastructure.

### What it is NOT

- Not a change to LLM generation prompts — the LLM always generates with the same difficulty definitions
- Not real-time — stat accumulation is online, but relabeling decisions are batched
- Not irreversible — labels revert when evidence no longer supports the change

## 2. Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Scope | Per-item relabeling + course-level bias matrix | Immediate corrections on existing items + informed priors for new items |
| Triggering | Online stat accumulation, batch decision every ~50 attempts | Data-driven timing adapts to usage patterns; no wasted compute during idle periods |
| Evidence model | Hierarchical Bayesian (Dirichlet-Multinomial + Beta-Binomial) | Solves cold-start via course prior; pure NumPy; explainable to instructors |
| Relabeling direction | Bidirectional, asymmetric thresholds (90% downgrade, 95% upgrade) | False upgrades are more harmful to student experience than false downgrades |
| Bias model output | Label remapping via transition matrix only | Prompt calibration rejected — causes temporal inconsistency in generated content |
| Bandit interaction | `corrected_difficulty` column on `revision_attempts` | Preserves audit trail; bandit state vector uses corrected labels for cleaner signal |
| Instructor visibility | Read-only dashboard with manual override | Transparency for domain experts; catches confounds like recency effects |
| Batch trigger | Attempt-count threshold → existing worker queue | Zero new infrastructure; idempotent; adapts to burst usage |

## 3. Database Schema

### 3a. New Table: `recalibration_stats`

Per-item attempt statistics, accumulated online via upsert. The batch job reads from this table.

```sql
CREATE TABLE recalibration_stats (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pool_item_id    UUID NOT NULL REFERENCES revision_pool_items(id) ON DELETE CASCADE,
    course_id       UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    content_type    VARCHAR(20) NOT NULL,
    llm_difficulty  VARCHAR(10) NOT NULL,
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    correct_count   INTEGER NOT NULL DEFAULT 0,  -- score >= 0.8 (easy signal)
    hard_count      INTEGER NOT NULL DEFAULT 0,  -- score < 0.4 (hard signal)
    score_sum       NUMERIC(10,2) NOT NULL DEFAULT 0,
    score_sq_sum    NUMERIC(12,4) NOT NULL DEFAULT 0,

    UNIQUE (pool_item_id)
);

CREATE INDEX idx_recal_stats_course
    ON recalibration_stats (course_id, content_type, llm_difficulty);
```

### 3b. New Table: `recalibration_models`

Course-level Dirichlet parameters and cached transition matrix.

```sql
CREATE TABLE recalibration_models (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id         UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    content_type      VARCHAR(20) NOT NULL,
    dirichlet_params  JSONB NOT NULL,
    transition_matrix JSONB NOT NULL,
    items_used        INTEGER NOT NULL DEFAULT 0,
    total_attempts_since_last_run INTEGER NOT NULL DEFAULT 0,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (course_id, content_type)
);
```

**`dirichlet_params` structure:**

```json
{
  "easy":   {"easy": 10, "medium": 1, "hard": 1},
  "medium": {"easy": 1,  "medium": 10, "hard": 1},
  "hard":   {"easy": 1,  "medium": 1,  "hard": 10}
}
```

Initial values: 10 on the diagonal (trust LLM), 1 off-diagonal. Each row is a Dirichlet distribution.

**`transition_matrix` structure:**

```json
{
  "easy":   {"easy": 0.83, "medium": 0.08, "hard": 0.08},
  "medium": {"easy": 0.08, "medium": 0.83, "hard": 0.08},
  "hard":   {"easy": 0.08, "medium": 0.08, "hard": 0.83}
}
```

Derived by normalizing each row of `dirichlet_params`. Cached for fast lookup during item-level posterior computation and new item prior assignment.

### 3c. New Columns on `revision_pool_items`

```sql
ALTER TABLE revision_pool_items
    ADD COLUMN recalibrated_difficulty VARCHAR(10),
    ADD COLUMN recalibration_confidence NUMERIC(4,3),
    ADD COLUMN instructor_override BOOLEAN NOT NULL DEFAULT FALSE;
```

- `recalibrated_difficulty`: NULL until the classifier has sufficient evidence to relabel. The bandit serves from `COALESCE(recalibrated_difficulty, difficulty)`.
- `recalibration_confidence`: Posterior probability of the recalibrated label (0.000–1.000).
- `instructor_override`: When TRUE, the batch job skips this item. Set by instructor via dashboard override action.

### 3d. New Column on `revision_attempts`

```sql
ALTER TABLE revision_attempts
    ADD COLUMN corrected_difficulty VARCHAR(10);
```

Populated by the batch job when the linked pool item is relabeled. Historical `difficulty` column is preserved as-served. The bandit's state vector computation uses `COALESCE(corrected_difficulty, difficulty)` for features 0–5 (avg_score_easy/medium/hard and recency-weighted variants).

## 4. Bayesian Classifier

### 4a. Layer 1 — Course-Level Dirichlet-Multinomial

One Dirichlet distribution per (course, content_type, llm_difficulty). Represents the probability distribution over true difficulty given the LLM's label.

**Initialization:**

```python
# Strong prior trusting LLM label
DIRICHLET_INIT = {
    "easy":   {"easy": 10, "medium": 1, "hard": 1},
    "medium": {"easy": 1,  "medium": 10, "hard": 1},
    "hard":   {"easy": 1,  "medium": 1,  "hard": 10},
}
```

**Update rule:** When an item has enough attempts to determine its observed difficulty, increment the corresponding Dirichlet concentration parameter:

```python
# Item labeled "medium" by LLM, observed as "easy" from student data
dirichlet_params["medium"]["easy"] += 1
```

**Observed difficulty classification:**

| Mean Score | Observed Difficulty |
|-----------|-------------------|
| >= 0.85 | easy |
| < 0.45 | hard |
| 0.45 – 0.85 | medium |

**Transition matrix derivation:** Normalize each row of the Dirichlet parameters.

```python
# For LLM label "medium" with params {"easy": 12, "medium": 20, "hard": 4}
total = 12 + 20 + 4  # = 36
transition["medium"] = {"easy": 12/36, "medium": 20/36, "hard": 4/36}
# → {"easy": 0.33, "medium": 0.56, "hard": 0.11}
```

### 4b. Layer 2 — Item-Level Beta-Binomial

Each item starts with a prior derived from the course-level transition matrix, then updates with its own attempt data.

**Prior construction** using equivalent sample size `k=5`:

```python
# Item X labeled "medium", course transition matrix says:
#   P(true=easy|LLM=medium)   = 0.33
#   P(true=medium|LLM=medium) = 0.56
#   P(true=hard|LLM=medium)   = 0.11

k = 5  # equivalent sample size — prior is worth ~5 virtual attempts
prior_easy   = Beta(α=0.33*k, β=0.67*k)  # Beta(1.65, 3.35)
prior_medium = Beta(α=0.56*k, β=0.44*k)  # Beta(2.80, 2.20)
prior_hard   = Beta(α=0.11*k, β=0.89*k)  # Beta(0.55, 4.45)
```

**Update rule per attempt:**

| Score Range | Update |
|-------------|--------|
| >= 0.8 (correct/easy signal) | α_easy += 1, β_hard += 1 |
| < 0.4 (incorrect/hard signal) | α_hard += 1, β_easy += 1 |
| 0.4 – 0.8 (medium signal) | α_medium += 1 |

In practice, the batch job computes these from `recalibration_stats` aggregate counters, not individual attempts:

```python
# Derive Beta update counts from recalibration_stats
easy_signals   = stats.correct_count          # score >= 0.8
hard_signals   = stats.hard_count             # score < 0.4
medium_signals = stats.attempt_count - easy_signals - hard_signals  # 0.4–0.8

# Apply to priors
α_easy   += easy_signals;   β_easy   += hard_signals
α_medium += medium_signals
α_hard   += hard_signals;   β_hard   += easy_signals
```

**Relabeling decision:**

```python
posterior = {
    "easy":   α_easy / (α_easy + β_easy),
    "medium": α_medium / (α_medium + β_medium),
    "hard":   α_hard / (α_hard + β_hard),
}
best = max(posterior, key=posterior.get)

if best != llm_difficulty:
    is_downgrade = DIFFICULTY_ORDER[best] < DIFFICULTY_ORDER[llm_difficulty]
    threshold = 0.90 if is_downgrade else 0.95

    if posterior[best] >= threshold:
        relabel(item, new_difficulty=best, confidence=posterior[best])
    else:
        revert_if_previously_relabeled(item)
```

Where `DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2}`.

### 4c. Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `DIRICHLET_PRIOR_STRONG` | 10 | Diagonal (matching) prior weight |
| `DIRICHLET_PRIOR_WEAK` | 1 | Off-diagonal (non-matching) prior weight |
| `EQUIVALENT_SAMPLE_SIZE` | 5 | Course prior strength for item-level Beta |
| `MIN_ATTEMPTS_FOR_LAYER1` | 5 | Minimum attempts before item contributes to Dirichlet |
| `DOWNGRADE_THRESHOLD` | 0.90 | Posterior confidence to relabel easier |
| `UPGRADE_THRESHOLD` | 0.95 | Posterior confidence to relabel harder |
| `EASY_SCORE_THRESHOLD` | 0.85 | Mean score above which item is classified "easy" |
| `HARD_SCORE_THRESHOLD` | 0.45 | Mean score below which item is classified "hard" |
| `BATCH_TRIGGER_ATTEMPTS` | 50 | Attempts per (course, content_type) to trigger batch |

## 5. Online Stat Accumulation

Runs inside the existing `submit_answer()` endpoint in `api/revision.py`.

**After every attempt INSERT:**

```python
async def accumulate_recalibration_stats(
    db: AsyncSession,
    pool_item_id: UUID,
    course_id: UUID,
    content_type: str,
    llm_difficulty: str,
    score: float,
):
    await db.execute(
        insert(RecalibrationStats)
        .values(
            pool_item_id=pool_item_id,
            course_id=course_id,
            content_type=content_type,
            llm_difficulty=llm_difficulty,
            attempt_count=1,
            correct_count=1 if score >= 0.8 else 0,
            hard_count=1 if score < 0.4 else 0,
            score_sum=score,
            score_sq_sum=score * score,
        )
        .on_conflict_do_update(
            index_elements=["pool_item_id"],
            set_={
                "attempt_count": RecalibrationStats.attempt_count + 1,
                "correct_count": RecalibrationStats.correct_count + (1 if score >= 0.8 else 0),
                "hard_count": RecalibrationStats.hard_count + (1 if score < 0.4 else 0),
                "score_sum": RecalibrationStats.score_sum + score,
                "score_sq_sum": RecalibrationStats.score_sq_sum + score * score,
            },
        )
    )
```

**Batch trigger check:**

```python
async def maybe_trigger_recalibration(
    db: AsyncSession, course_id: UUID, content_type: str
):
    model = await db.get_recalibration_model(course_id, content_type)
    if model is None:
        count = await count_total_stats(db, course_id, content_type)
    else:
        count = model.total_attempts_since_last_run + 1
        model.total_attempts_since_last_run = count

    if count >= BATCH_TRIGGER_ATTEMPTS:
        await enqueue_task(db, "recalibration", {
            "course_id": str(course_id),
            "content_type": content_type,
        })
```

**Latency budget:** ~2ms added to the `/answer` endpoint (one upsert + one counter check). Total endpoint budget moves from ~10ms to ~12ms.

## 6. Batch Recalibration Job

New task type `recalibration` handled by `services/recalibrator.py`, executed by the existing `worker.py` polling loop.

### 6a. Job Flow

```
1. LOAD all recalibration_stats for (course_id, content_type)

2. PARTITION items:
   - Qualifying: attempt_count >= MIN_ATTEMPTS_FOR_LAYER1 (5)
   - Non-qualifying: fewer attempts, still get course prior applied

3. CLASSIFY qualifying items → observed difficulty
   - mean_score = score_sum / attempt_count
   - Apply EASY_SCORE_THRESHOLD (0.85) and HARD_SCORE_THRESHOLD (0.45)

4. UPDATE Layer 1 (Dirichlet)
   - Load or initialize recalibration_models row
   - Reset Dirichlet to initial priors
   - For each qualifying item: increment dirichlet_params[llm_difficulty][observed_difficulty]
   - Recompute transition matrix (normalize rows)
   - Upsert recalibration_models

5. UPDATE Layer 2 (item posteriors) for ALL items
   For each pool item in this (course, content_type):
     a. Build Beta priors from transition matrix (k=EQUIVALENT_SAMPLE_SIZE)
     b. Update with item's own stats from recalibration_stats
     c. Compute posterior means
     d. Apply asymmetric thresholds
     e. UPDATE revision_pool_items.recalibrated_difficulty and recalibration_confidence
     f. Revert label if posterior no longer meets threshold

6. BACKFILL corrected_difficulty on revision_attempts
   - Batch UPDATE for attempts linked to relabeled items

7. RESET counter
   - Set recalibration_models.total_attempts_since_last_run = 0
   - Update recalibration_models.updated_at
```

### 6b. Dirichlet Recomputation Strategy

The Dirichlet is recomputed from scratch each batch run (not incremented from the last run). This ensures idempotency — running the job twice produces identical results. The cost is negligible: one pass over qualifying items to count observed difficulty per LLM label.

### 6c. Relabeling Reversibility

Step 5f is critical: if an item was previously relabeled but the posterior no longer exceeds the threshold (e.g., new attempts shifted the evidence), the recalibrated label is set back to NULL and the original LLM label is restored. The `recalibration_confidence` is also cleared.

### 6d. Performance Budget

| Step | Estimated (200 pool items) |
|------|---------------------------|
| Load stats | ~5ms |
| Classify + Dirichlet update | ~1ms |
| Item posteriors (NumPy vectorized) | ~2ms |
| Pool item UPDATEs | ~5ms |
| Attempt backfill | ~10ms |
| **Total** | **~25ms** |

## 7. Bandit Integration

### 7a. Serving Difficulty

The bandit selects a difficulty level, then an item is served from the pool. The pool query changes from:

```sql
-- Before
WHERE difficulty = :selected_difficulty

-- After
WHERE COALESCE(recalibrated_difficulty, difficulty) = :selected_difficulty
```

This means a pool item originally labeled "medium" but recalibrated to "easy" will be served when the bandit selects "easy," not "medium."

### 7b. State Vector Correction

The `compute_state_vector()` function in `bandit.py` queries recent `revision_attempts` rows. Features 0–5 group scores by difficulty. The query changes to use corrected labels:

```sql
SELECT COALESCE(corrected_difficulty, difficulty) AS effective_difficulty,
       score, created_at
FROM revision_attempts
WHERE user_id = :uid AND course_id = :cid AND content_type = :ct
ORDER BY created_at DESC
LIMIT 50
```

This gives the bandit a cleaner signal: if an item was labeled "medium" but was actually "easy," the student's score on it contributes to `avg_score_easy` rather than `avg_score_medium`.

### 7c. No Retroactive Policy Retraining

The bandit's stored weights are NOT retrained when attempts are backfilled. The corrected difficulty only affects future state vector computations. The bandit naturally adapts over subsequent attempts as the state vector becomes more accurate.

## 8. Instructor Dashboard

### 8a. Recalibration Overview

New section on the course admin page showing recalibration status per content type:

| Content Type | Items Scanned | Items Relabeled | Last Run |
|-------------|--------------|----------------|----------|
| Quiz | 145 | 23 (15.9%) | 2 hours ago |
| Flashcard | 98 | 11 (11.2%) | 2 hours ago |
| Speaking | 62 | 5 (8.1%) | 5 hours ago |

### 8b. Transition Matrix Display

Visual representation of the course-level bias:

```
Quiz Difficulty Calibration (COMP3021):

LLM Label → Observed Reality
            Easy    Medium    Hard
Easy        85%     12%       3%
Medium      35%     55%       10%
Hard         5%     40%       55%
```

Color-coded: diagonal cells green (LLM correct), off-diagonal cells yellow/red (mislabeled).

### 8c. Item-Level Detail Table

Sortable, filterable table of pool items with recalibration data:

| Item Preview | LLM Label | Recalibrated | Confidence | Attempts | Correct Rate | Override |
|-------------|-----------|-------------|------------|----------|-------------|---------|
| "What is the time complexity of..." | Medium | Easy | 93.2% | 18 | 94.4% | [Reset] |
| "Compare the trade-offs between..." | Hard | Medium | 91.5% | 22 | 68.2% | [Reset] |
| "Define the term 'polymorphism'" | Easy | — | — | 8 | 87.5% | — |

**Override action:** "Reset" sets `recalibrated_difficulty = NULL` and `recalibration_confidence = NULL`, restoring the LLM label. An `instructor_override` boolean column on `revision_pool_items` prevents the batch job from relabeling the item again.

### 8d. Override Behavior

The `instructor_override` column (defined in Section 3c) controls recalibration eligibility. When an instructor clicks "Reset":

1. `recalibrated_difficulty` → NULL (LLM label restored)
2. `recalibration_confidence` → NULL
3. `instructor_override` → TRUE (batch job skips this item permanently)

To re-enable automatic recalibration, the instructor clicks "Reset" again to toggle `instructor_override` back to FALSE.

## 9. File Structure

### 9a. New Files

| File | Purpose |
|------|---------|
| `backend/app/services/recalibrator.py` | Bayesian classifier: Dirichlet + Beta-Binomial, batch job logic |
| `backend/app/models/recalibration.py` | RecalibrationStats, RecalibrationModel SQLAlchemy models |
| `backend/app/schemas/recalibration.py` | Response schemas for instructor dashboard API |
| `backend/app/api/recalibration.py` | Instructor-facing endpoints (GET overview, GET items, POST override) |
| `backend/alembic/versions/xxxx_recalibration.py` | Migration: new tables + new columns |
| `backend/tests/test_recalibrator.py` | Unit tests for Bayesian math, batch job logic |
| `backend/tests/test_api_recalibration.py` | Integration tests for instructor endpoints |
| `frontend/src/components/recalibration/overview.tsx` | Recalibration dashboard overview |
| `frontend/src/components/recalibration/transition-matrix.tsx` | Visual transition matrix |
| `frontend/src/components/recalibration/item-table.tsx` | Item-level detail table with override |
| `frontend/src/hooks/use-recalibration.ts` | Data fetching hook for dashboard |

### 9b. Modified Files

| File | Change | Risk |
|------|--------|------|
| `backend/app/api/revision.py` | Add `accumulate_recalibration_stats()` + `maybe_trigger_recalibration()` calls in `submit_answer()` | Low — two function calls appended |
| `backend/app/services/bandit.py` | `compute_state_vector()` uses `COALESCE(corrected_difficulty, difficulty)` | Low — query change only |
| `backend/app/services/pool.py` | Pool item query uses `COALESCE(recalibrated_difficulty, difficulty)` | Low — WHERE clause change |
| `backend/app/services/worker.py` | Add `recalibration` task handler | Low — one new elif branch |
| `backend/app/models/__init__.py` | Import new models | Trivial |
| `backend/app/api/__init__.py` | Register recalibration router | Trivial |
| `frontend/src/app/dashboard/courses/[courseId]/` | Add recalibration tab for instructors | Low — additive |

## 10. API Endpoints

New router: `backend/app/api/recalibration.py`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/courses/{id}/recalibration/overview` | instructor | Summary stats + transition matrices per content type |
| GET | `/api/courses/{id}/recalibration/items` | instructor | Paginated item list with recalibration details |
| POST | `/api/courses/{id}/recalibration/items/{itemId}/override` | instructor | Toggle instructor override (reset recalibrated label) |

All endpoints return the standard `APIResponse[T]` envelope. The items endpoint supports `PaginatedResponse[T]` with filtering by `content_type`, `llm_difficulty`, `recalibrated_difficulty`, and sorting by `confidence`, `attempt_count`, `correct_rate`.

## 11. Testing Strategy

| Area | Test Type | What |
|------|-----------|------|
| Dirichlet initialization | Unit | Verify initial params, transition matrix normalization |
| Dirichlet update | Unit | Increment params, verify matrix shifts correctly |
| Beta prior from transition matrix | Unit | Verify prior construction with k=5 |
| Beta posterior update | Unit | Known attempt data → expected posterior means |
| Relabeling decision | Unit | Asymmetric thresholds, downgrade vs upgrade, revert logic |
| End-to-end classifier | Unit | Full pipeline: stats → Dirichlet → Beta → label decision |
| Edge cases | Unit | Zero attempts, single attempt, all same score, ties |
| `accumulate_recalibration_stats` | Integration | Upsert correctness, counter arithmetic |
| Batch trigger | Integration | Counter reaches 50 → task enqueued |
| Batch job | Integration | Full run: load stats → classify → update models → relabel items → backfill attempts |
| Instructor override | Integration | Override prevents relabeling, reset clears override |
| Bandit state vector | Integration | `corrected_difficulty` used in feature computation |
| Pool serving | Integration | `COALESCE(recalibrated_difficulty, difficulty)` serves correctly |
| Instructor dashboard | E2E | Overview loads, item table filters/sorts, override button works |

Coverage target: 80%+ on `recalibrator.py`, `api/recalibration.py`, and all new models/schemas.

## 12. Implementation Order

```
1. Migration (new tables + columns)
2. RecalibrationStats + RecalibrationModel models
3. recalibrator.py (Bayesian classifier — Dirichlet + Beta math + batch job)
4. Online accumulation in submit_answer()
5. Worker integration (recalibration task type)
6. Bandit + pool query changes (COALESCE)
7. Instructor API endpoints + schemas
8. Frontend dashboard (overview, transition matrix, item table, override)
```

Each step is independently testable. Steps 1–3 are pure backend with no user-facing impact. Step 4 starts accumulating data silently. Steps 5–6 activate recalibration. Steps 7–8 add instructor visibility.

## 13. Dependencies

No new dependencies. NumPy is already present (used by bandit.py). The Dirichlet-Multinomial and Beta-Binomial computations use `numpy` only. No new frontend dependencies.
