# Neural Spaced Repetition (Feature 15b)

> Replaces fixed SM-2 constants with FSRS-5, a learned 19-parameter model that predicts personalized review intervals from flashcard + revision attempt data.

## Context

Meli's flashcard system currently uses the SM-2 algorithm with fixed constants (ease factor floor 1.3, fixed initial intervals 1/6 days, linear EF adjustment). SM-2 treats every student identically — the only personalization is through the ease factor, which adjusts slowly and has limited range.

The difficulty adapter (contextual bandit) already proves that per-student learned models work well in our infrastructure. This feature applies the same philosophy to review scheduling.

### Prior Art

| Algorithm | Parameters | Log Loss | AUC | Notes |
|-----------|-----------|----------|-----|-------|
| SM-2 | 0 (fixed) | baseline | ~0.5 | Current implementation |
| HLR (Duolingo, 2016) | ~20-50 | 0.469 | 0.637 | Linear half-life prediction |
| FSRS-5 (Anki) | 19 | 0.344 | 0.707 | Structured memory model |
| LSTM | thousands | 0.333 | 0.733 | Sequence model |
| RWKV-P | thousands | 0.277 | 0.833 | Best benchmark result |

**Choice: FSRS-5** — within striking distance of neural nets with 19 parameters. Battle-tested in Anki (millions of users), well-documented, fits our latency and infrastructure constraints.

**References:**
- Settles & Meeder, "A Trainable Spaced Repetition Model for Language Learning," ACL 2016
- FSRS-5 Algorithm: https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm
- SRS Benchmark: https://github.com/open-spaced-repetition/srs-benchmark

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Algorithm | FSRS-5 (19 params) | Best accuracy-to-complexity ratio; proven at scale |
| Goal | Predict recall probability, derive intervals | More principled than direct interval prediction |
| Bandit relationship | Fully separate | Different problems, different timescales; bandit works, don't entangle |
| Cold start | SM-2 fallback | Zero regression risk for new students |
| Training | Online SGD after each review | Mirrors bandit pattern; 19 params converge fast |
| Target retention | Fixed 0.9 (90%) | Research default; stored as constant for future exposure |
| Switchover threshold | 20 reviews per course | Consistent with bandit; sufficient for 19 params |
| Frontend changes | None | Scheduler is invisible behind existing API |

## Memory Model

### State Variables (per card per student)

- **Stability (S)** — interval in days at which recall probability = 90%
- **Difficulty (D)** — item difficulty, range [1, 10]
- **Retrievability (R)** — predicted recall probability at elapsed time t

### Core Formulas

**Retrievability (power-law decay):**

```
R(t, S) = (1 + t / (9 * S))^(-1)
```

R = 0.9 when t = S by construction.

**Interval from target retention (0.9):**

```
I(S) = 9 * S * (1/target - 1)
     = S   (when target = 0.9)
```

**Initial stability (first review, grade G in {1,2,3,4}):**

```
S_0(G) = w[G-1]
```

Parameters w_0 through w_3 map each grade to an initial stability.

**Initial difficulty:**

```
D_0(G) = w_4 - e^(w_5 * (G - 1)) + 1
```

**Difficulty update (with mean reversion):**

```
D' = w_7 * D_0(4) + (1 - w_7) * (D - w_6 * (G - 3))
D' = clamp(D', 1, 10)
```

**Stability after successful recall (G >= 2):**

```
S'_r = S * (e^(w_8) * (11 - D) * S^(-w_9) * (e^(w_10 * (1 - R)) - 1) * multiplier + 1)

where multiplier:
  G = 2 (Hard): w_15
  G = 3 (Good): 1.0
  G = 4 (Easy): w_16
```

**Stability after forgetting (G = 1, "Again"):**

```
S'_f = w_11 * D^(-w_12) * ((S + 1)^w_13 - 1) * e^(w_14 * (1 - R))
```

**Short-term stability (same-day reviews):**

```
S'_s = S * e^(w_17 * (G - 3 + w_18))
```

### 19 Parameters (w_0 through w_18)

Default initialization from FSRS-5 research:

```python
DEFAULT_PARAMS = [
    0.40255,   # w0:  S_0(Again)
    1.18385,   # w1:  S_0(Hard)
    3.173,     # w2:  S_0(Good)
    15.69105,  # w3:  S_0(Easy)
    7.1949,    # w4:  D_0 base
    0.5345,    # w5:  D_0 grade sensitivity
    1.4604,    # w6:  D update grade sensitivity
    0.0046,    # w7:  D mean reversion rate
    1.54575,   # w8:  S_r exponential base
    0.1192,    # w9:  S_r stability decay
    1.01925,   # w10: S_r retrievability bonus
    1.9395,    # w11: S_f base
    0.11,      # w12: S_f difficulty sensitivity
    0.29605,   # w13: S_f stability sensitivity
    2.2698,    # w14: S_f retrievability sensitivity
    0.2315,    # w15: Hard multiplier
    2.9898,    # w16: Easy multiplier
    0.51655,   # w17: Short-term grade sensitivity
    0.6621,    # w18: Short-term offset
]
```

### Grade Mapping

| UI Button | Current SM-2 quality | FSRS Grade |
|-----------|---------------------|------------|
| Again | 0 | 1 |
| Hard | 2 | 2 |
| Good | 4 | 3 |
| Easy | 5 | 4 |

## Data Model

### New Table: `scheduler_models`

```sql
CREATE TABLE scheduler_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    course_id UUID NOT NULL REFERENCES courses(id),
    parameters JSON NOT NULL,  -- 19 floats, w_0 through w_18
    strategy VARCHAR(10) NOT NULL DEFAULT 'sm2',  -- "sm2" or "fsrs"
    review_count INT NOT NULL DEFAULT 0,  -- total reviews across all cards in this course (switchover trigger)
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE(user_id, course_id)
);

CREATE INDEX idx_scheduler_models_lookup ON scheduler_models(user_id, course_id);
```

JSON instead of binary blob because 19 floats serialize trivially and JSON is debuggable/queryable. No PyTorch serialization needed.

### Altered Table: `flashcard_progress`

```sql
ALTER TABLE flashcard_progress
    ADD COLUMN stability NUMERIC,        -- S in days
    ADD COLUMN difficulty NUMERIC,        -- D, range 1-10
    ADD COLUMN last_grade SMALLINT,       -- last FSRS grade 1-4
    ADD COLUMN fsrs_review_count INT NOT NULL DEFAULT 0;  -- per-card review count
```

All new columns are nullable except `review_count` (defaults to 0). Existing SM-2 columns (`ease_factor`, `interval_days`, `repetitions`) remain untouched as the source of truth for students below the switchover threshold.

### Unchanged Tables

- `revision_attempts`, `revision_sessions` — bandit stays independent
- `bandit_models` — no coupling
- `flashcard_cards`, `flashcard_sets` — no schema changes

## Service Layer

### New File: `backend/app/services/scheduler.py`

```
FSRSScheduler
├── DEFAULT_PARAMS       19 FSRS-5 default values
├── TARGET_RETENTION     0.9
├── SWITCHOVER_THRESHOLD 20
├── MIN_INTERVAL         1 day
├── MAX_INTERVAL         180 days
│
├── get_next_interval(progress, model) → timedelta
│   If review_count < 20: delegate to sm2_interval()
│   Else: interval = 9 * S * (1/target - 1), clamped to [1, 180]
│
├── update_card_state(progress, grade, model) → FlashcardProgress
│   First review of card: S_0(G), D_0(G)
│   Subsequent: S'_r or S'_f depending on grade
│   Update D', set next_review = now + interval
│
├── update_parameters(model, predicted_r, actual_outcome) → SchedulerModel
│   Loss: binary cross-entropy -[y*log(R) + (1-y)*log(1-R)]
│   Gradient via PyTorch autograd on 19 params
│   SGD step, gradient clipping (norm=1.0)
│   Increment review_count
│
├── sm2_interval(progress, quality) → timedelta
│   Existing SM-2 logic extracted from flashcards.py (unchanged algorithm)
│
├── compute_retrievability(t, S) → float
│   R = (1 + t / (9 * S))^(-1)
│
└── initialize_from_sm2(progress) → (S, D)
    S = interval_days
    D = 11 - ease_factor * 4 (maps EF 1.3-2.5 → D roughly 1-6)
```

### Training Flow (per review)

```
Student rates card (Again/Hard/Good/Easy)
  → Map to FSRS grade (1/2/3/4)
  → Load scheduler_model for (user, course)
  → Load flashcard_progress for card
  → Check FSRS_ENABLED feature flag
  → If disabled OR review_count < 20:
      sm2_interval() — existing logic, unchanged
  → Else:
      1. Compute predicted R at current elapsed time
      2. Observe actual outcome: recall (grade >= 2) or forget (grade == 1)
      3. update_parameters() — SGD step on 19 params
      4. update_card_state() — compute new S, D, next_review
  → Increment scheduler_model.review_count
  → Save scheduler_model + flashcard_progress to DB
```

**Latency:** Forward pass + autograd backward on 19 scalar parameters is sub-millisecond. Well within the 10ms budget.

## API Changes

### Modified Endpoint: `PUT /api/flashcard-sets/{set_id}/progress`

The inline SM-2 logic (~30 lines in `api/flashcards.py:276-303`) is replaced with a call to `FSRSScheduler.update_card_state()`. The scheduler internally decides SM-2 vs FSRS based on the threshold.

**Response shape is unchanged.** The endpoint already returns `next_review`, `ease_factor`, `interval_days`. For FSRS students, `interval_days` is derived from stability instead of the fixed formula, but the field name and type remain identical.

### No New Endpoints

No new routes, no new response schemas. The neural scheduler is entirely behind the existing API surface.

### No Frontend Changes

The flashcard review UI already sends 4-button ratings and reads `next_review` from the API response. Zero changes to components, hooks, or data flow.

## Migration & Switchover

### Alembic Migration (single revision)

1. `CREATE TABLE scheduler_models` with unique constraint
2. `ALTER TABLE flashcard_progress` — add 4 nullable columns
3. Create index on `scheduler_models(user_id, course_id)`

No data backfill. Existing students start with null FSRS columns; SM-2 continues until they organically reach 20 reviews.

### Automatic Per-Student Switchover

```
New student → SM-2 from day one
  → Reviews accumulate, review_count increments on scheduler_model
  → At review 20: strategy flips "sm2" → "fsrs"
  → S initialized from interval_days
  → D initialized from ease_factor (mapped to 1-10 range)
  → All future reviews use FSRS
  → SM-2 columns go stale but remain in DB
```

### Rollback Strategy

| Level | Trigger | Action |
|-------|---------|--------|
| Per-student | Degenerate intervals (>365 or <0.1 days) | Clamp to [1, 180], log warning |
| Per-course | Instructor reports issues | Set strategy="sm2" on affected rows |
| Global | Systemic problem | `FSRS_ENABLED=false` in .env — all students fall back to SM-2 |

### Feature Flag

`FSRS_ENABLED` (default `true`) in `backend/app/config.py`. When `false`, `FSRSScheduler` always delegates to `sm2_interval()` regardless of review count.

## Testing

### Unit Tests (`tests/test_scheduler.py`)

| Test | Verifies |
|------|----------|
| `test_retrievability_at_stability` | R(t=S, S) = 0.9 exactly |
| `test_retrievability_decay` | R decreases monotonically with t |
| `test_initial_stability_by_grade` | S_0 increases with grade |
| `test_initial_difficulty_by_grade` | D_0 decreases with grade |
| `test_stability_after_recall` | S'_r > S |
| `test_stability_after_forget` | S'_f < S |
| `test_difficulty_mean_reversion` | D converges toward easy target |
| `test_difficulty_clamped` | D stays in [1, 10] |
| `test_interval_from_stability` | interval = S at 90% target |
| `test_interval_clamped` | interval in [1, 180] days |
| `test_sgd_step_reduces_loss` | Loss decreases after update_parameters() |
| `test_sm2_fallback_under_threshold` | review_count < 20 uses SM-2 |
| `test_switchover_at_threshold` | review_count = 20 initializes S/D from SM-2 |
| `test_feature_flag_disables_fsrs` | FSRS_ENABLED=false → always SM-2 |
| `test_grade_mapping` | Again→1, Hard→2, Good→3, Easy→4 |

### Integration Tests (`tests/test_scheduler_integration.py`)

| Test | Verifies |
|------|----------|
| `test_full_review_cycle` | Rate card → DB updated with S, D, next_review |
| `test_sm2_to_fsrs_transition` | 20 reviews → strategy flips, S/D initialized |
| `test_scheduler_model_persistence` | Parameters survive save/load via JSON |
| `test_concurrent_reviews` | Two cards reviewed simultaneously don't corrupt model |
| `test_api_response_shape_unchanged` | PUT /progress returns same schema for both paths |

### Not Tested

- Frontend — zero changes
- Bandit interaction — fully independent
- Long-term scheduling quality — research evaluation, not a unit test

**Coverage target:** 80%+ on `scheduler.py` and modified `flashcards.py`.

## Dependencies

No new dependencies. Uses existing `torch` (2.7.0+cpu) and `numpy` (2.2.5) already in `requirements.txt` for the bandit.

## Scope Boundaries

**In scope:**
- FSRS-5 algorithm implementation
- Per-user online parameter learning
- SM-2 cold start and automatic switchover
- Feature flag and rollback mechanisms
- Unit and integration tests

**Out of scope:**
- Population-level (global prior) model training
- Student-facing retention threshold tuning
- Instructor dashboard for scheduler stats
- Batch retraining from full history
- Frontend changes of any kind
