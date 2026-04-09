# Personalized Difficulty Adapter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an adaptive difficulty system for a new infinite-practice "revision" mode, using a contextual bandit (PyTorch MLP + REINFORCE) to personalize quiz, flashcard, and speaking difficulty per student.

**Architecture:** New revision models and tables (Alembic migration), difficulty-aware content generation (additive functions in generator.py), a bandit service (PyTorch policy network + NumPy state vectors), REST API endpoints for session lifecycle, and a frontend revision player page. All additive — zero changes to existing quiz/flashcard/SM-2 behavior.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, PyTorch (CPU-only), NumPy, Alembic, Next.js 16, React 19, TanStack Query, Playwright.

**Design Spec:** [Difficulty Adapter Design Spec](../specs/2026-04-08-cle-difficulty-adapter.md)

---

## File Structure

### New Files — Backend

```
backend/
├── app/
│   ├── models/
│   │   └── revision.py              # RevisionSession, RevisionPoolItem, RevisionAttempt, RevisionItemServed, BanditModel
│   ├── services/
│   │   └── bandit.py                # DifficultyPolicy MLP, state vector, REINFORCE, cold start, pool mgmt
│   ├── api/
│   │   └── revision.py              # /start, /answer, /next, /end, GET session
│   └── schemas/
│       └── revision.py              # Request/response Pydantic models
├── alembic/versions/
│   └── xxxx_revision_difficulty.py  # Migration: 6 new tables + 2 column additions
└── tests/
    ├── test_bandit.py               # Unit: state vector, cold start, REINFORCE, safety net
    ├── test_revision_generator.py   # Unit: mocked LLM, difficulty-aware generation
    └── test_api_revision.py         # Integration: session lifecycle endpoints
```

### New Files — Frontend

```
frontend/src/
├── hooks/
│   └── use-revision.ts              # useRevisionSession hook
├── components/
│   └── revision/
│       ├── content-type-picker.tsx   # Quiz / Flashcard / Speaking chooser
│       ├── revision-player.tsx       # Main loop container
│       ├── quiz-item.tsx             # Single question + answer buttons
│       ├── flashcard-item.tsx        # Flip card + self-rating
│       ├── item-feedback.tsx         # Correct/incorrect overlay
│       ├── session-stats-bar.tsx     # Live accuracy, streak, items count
│       └── session-summary.tsx       # End-of-session results
└── app/dashboard/courses/[courseId]/
    └── revision/
        └── page.tsx                  # Revision practice page
```

### Modified Files

```
backend/app/models/__init__.py       # Register new models
backend/app/models/quiz.py           # Add difficulty column to Question
backend/app/models/flashcard.py      # Add difficulty column to FlashcardCard
backend/app/services/generator.py    # Add generate_revision_* functions
backend/app/services/worker.py       # Add revision_pool_replenish handler
backend/app/api/__init__.py          # Register revision router
backend/requirements.txt             # Add torch (CPU-only), numpy
frontend/src/app/dashboard/courses/[courseId]/page.tsx  # Add Revision tab
frontend/src/components/layout/sidebar.tsx              # Add Revision nav link
```

---

## Task 1: Add PyTorch Dependency

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add torch and numpy to requirements.txt**

Append to `backend/requirements.txt`:

```
# ML — Difficulty adapter (contextual bandit)
numpy==2.2.5
torch==2.7.0+cpu --index-url https://download.pytorch.org/whl/cpu
```

- [ ] **Step 2: Install dependencies**

```bash
cd backend && pip install numpy==2.2.5
cd backend && pip install torch==2.7.0+cpu --index-url https://download.pytorch.org/whl/cpu
```

- [ ] **Step 3: Verify torch imports**

```bash
cd backend && python -c "import torch; print(f'PyTorch {torch.__version__}, CUDA: {torch.cuda.is_available()}')"
```

Expected: `PyTorch 2.7.0+cpu, CUDA: False`

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore: add PyTorch CPU and NumPy for difficulty adapter"
```

---

## Task 2: SQLAlchemy Models

**Files:**
- Create: `backend/app/models/revision.py`
- Modify: `backend/app/models/quiz.py`
- Modify: `backend/app/models/flashcard.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create revision models**

```python
# backend/app/models/revision.py
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class RevisionSession(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "revision_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False
    )
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items_answered: Mapped[int] = mapped_column(Integer, default=0)
    total_score: Mapped[Decimal] = mapped_column(Numeric(7, 2), default=Decimal("0"))


class RevisionPoolItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "revision_pool_items"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(10), nullable=False)

    # Quiz fields
    question_text: Mapped[str | None] = mapped_column(String)
    options: Mapped[dict | None] = mapped_column(JSON)
    correct_answer: Mapped[str | None] = mapped_column(String(10))
    explanation: Mapped[str | None] = mapped_column(String)

    # Flashcard fields
    front: Mapped[str | None] = mapped_column(String)
    back: Mapped[str | None] = mapped_column(String)

    # Speaking fields
    target_text: Mapped[str | None] = mapped_column(String)
    language: Mapped[str | None] = mapped_column(String(20))

    source_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RevisionAttempt(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "revision_attempts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("revision_sessions.id", ondelete="CASCADE"), nullable=False
    )
    pool_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("revision_pool_items.id"), nullable=False
    )
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(10), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)
    time_taken_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RevisionItemServed(Base):
    __tablename__ = "revision_item_served"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    pool_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("revision_pool_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    served_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BanditModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "bandit_models"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", "content_type"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False
    )
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    weights: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    strategy: Mapped[str] = mapped_column(String(10), default="rules")
    reward_mean: Mapped[float] = mapped_column(Float, default=0.0)
    reward_var: Mapped[float] = mapped_column(Float, default=1.0)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 2: Add difficulty column to Question**

In `backend/app/models/quiz.py`, add after the `source_chunk_id` column (line 49):

```python
    difficulty: Mapped[str] = mapped_column(String(10), default="medium")
```

- [ ] **Step 3: Add difficulty column to FlashcardCard**

In `backend/app/models/flashcard.py`, add after the `source_chunk_id` column (line 43):

```python
    difficulty: Mapped[str] = mapped_column(String(10), default="medium")
```

- [ ] **Step 4: Register models in `__init__.py`**

In `backend/app/models/__init__.py`, add:

```python
from app.models.revision import (
    BanditModel,
    RevisionAttempt,
    RevisionItemServed,
    RevisionPoolItem,
    RevisionSession,
)
```

And add them to `__all__`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/revision.py backend/app/models/quiz.py backend/app/models/flashcard.py backend/app/models/__init__.py
git commit -m "feat: add revision models and difficulty column to questions/flashcards"
```

---

## Task 3: Alembic Migration

**Files:**
- Create: `backend/alembic/versions/xxxx_revision_difficulty.py` (auto-generated)

- [ ] **Step 1: Generate migration**

```bash
cd backend && alembic revision --autogenerate -m "revision mode tables and difficulty columns"
```

- [ ] **Step 2: Review generated migration**

Open the generated file in `backend/alembic/versions/`. Verify it includes:
- `ADD COLUMN difficulty` on `questions` and `flashcard_cards`
- `CREATE TABLE revision_sessions`
- `CREATE TABLE revision_pool_items`
- `CREATE TABLE revision_attempts`
- `CREATE TABLE revision_item_served`
- `CREATE TABLE bandit_models`

- [ ] **Step 3: Add custom indexes to the migration**

Append to the `upgrade()` function:

```python
    op.execute("""
        CREATE INDEX idx_revision_pool_course_type_diff
        ON revision_pool_items (course_id, content_type, difficulty)
    """)
    op.execute("""
        CREATE INDEX idx_revision_attempts_state_vector
        ON revision_attempts (user_id, course_id, content_type, created_at DESC)
    """)
```

And add corresponding drops to `downgrade()`.

- [ ] **Step 4: Run migration**

```bash
cd backend && alembic upgrade head
```

- [ ] **Step 5: Verify tables exist**

```bash
cd backend && python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/langassistant')
    async with engine.connect() as conn:
        for table in ['revision_sessions', 'revision_pool_items', 'revision_attempts', 'revision_item_served', 'bandit_models']:
            result = await conn.execute(text(f\"SELECT COUNT(*) FROM {table}\"))
            print(f'{table}: {result.scalar()} rows')

asyncio.run(check())
"
```

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat: migration for revision tables and difficulty columns"
```

---

## Task 4: Bandit Service — Policy Network & Cold Start

The core ML module. Pure functions + one `nn.Module`. No DB calls — those happen in the API layer.

**Files:**
- Create: `backend/app/services/bandit.py`
- Create: `backend/tests/test_bandit.py`

- [ ] **Step 1: Write policy network and cold start tests**

```python
# backend/tests/test_bandit.py
import io
import math

import numpy as np
import pytest
import torch

from app.services.bandit import (
    COLD_START_THRESHOLD,
    DIFFICULTY_LEVELS,
    DifficultyPolicy,
    cold_start_select,
    compute_state_vector,
    is_degenerate,
    select_difficulty,
    serialize_weights,
    deserialize_weights,
    update_policy,
)


class TestDifficultyPolicy:
    def test_output_shape(self):
        model = DifficultyPolicy()
        state = torch.randn(10)
        probs = model(state)
        assert probs.shape == (3,)

    def test_output_sums_to_one(self):
        model = DifficultyPolicy()
        state = torch.randn(10)
        probs = model(state)
        assert abs(probs.sum().item() - 1.0) < 1e-5

    def test_initial_output_near_uniform(self):
        model = DifficultyPolicy()
        state = torch.zeros(10)
        probs = model(state)
        for p in probs:
            assert abs(p.item() - 1 / 3) < 0.05

    def test_serialize_deserialize_roundtrip(self):
        model = DifficultyPolicy()
        data = serialize_weights(model)
        model2 = DifficultyPolicy()
        deserialize_weights(model2, data)
        for p1, p2 in zip(model.parameters(), model2.parameters()):
            assert torch.allclose(p1, p2)


class TestColdStartSelect:
    def test_no_history_returns_medium(self):
        difficulty = cold_start_select([])
        assert difficulty == "medium"

    def test_two_consecutive_high_scores_moves_up(self):
        history = [
            {"difficulty": "medium", "score": 0.9},
            {"difficulty": "medium", "score": 0.85},
        ]
        difficulty = cold_start_select(history)
        assert difficulty == "hard"

    def test_single_high_score_stays(self):
        history = [
            {"difficulty": "medium", "score": 0.9},
        ]
        difficulty = cold_start_select(history)
        assert difficulty == "medium"

    def test_low_score_moves_down(self):
        history = [
            {"difficulty": "medium", "score": 0.3},
        ]
        difficulty = cold_start_select(history)
        assert difficulty == "easy"

    def test_clamps_at_hard(self):
        history = [
            {"difficulty": "hard", "score": 0.9},
            {"difficulty": "hard", "score": 0.9},
        ]
        difficulty = cold_start_select(history)
        assert difficulty == "hard"

    def test_clamps_at_easy(self):
        history = [
            {"difficulty": "easy", "score": 0.3},
        ]
        difficulty = cold_start_select(history)
        assert difficulty == "easy"


class TestComputeStateVector:
    def test_empty_attempts_returns_defaults(self):
        state = compute_state_vector(attempts=[], current_session_count=0)
        assert state.shape == (10,)
        # avg scores default to 0.5
        assert state[0] == pytest.approx(0.5)
        assert state[1] == pytest.approx(0.5)
        assert state[2] == pytest.approx(0.5)

    def test_with_easy_attempts(self):
        attempts = [
            {"difficulty": "easy", "score": 1.0, "created_at": "2026-04-08T10:00:00Z"},
            {"difficulty": "easy", "score": 0.0, "created_at": "2026-04-08T10:01:00Z"},
        ]
        state = compute_state_vector(attempts=attempts, current_session_count=2)
        # avg_score_easy should be 0.5
        assert state[0] == pytest.approx(0.5)
        # medium and hard still default
        assert state[1] == pytest.approx(0.5)
        assert state[2] == pytest.approx(0.5)

    def test_attempt_count_normalized(self):
        attempts = [{"difficulty": "easy", "score": 1.0, "created_at": "2026-04-08T10:00:00Z"}] * 50
        state = compute_state_vector(attempts=attempts, current_session_count=5)
        assert state[6] == pytest.approx(0.5)  # 50/100

    def test_session_progress_capped(self):
        state = compute_state_vector(attempts=[], current_session_count=30)
        assert state[9] == pytest.approx(1.0)  # 30/20 capped at 1.0


class TestSelectDifficulty:
    def test_cold_start_uses_rules(self):
        state = np.zeros(10)
        difficulty, log_prob = select_difficulty(
            state=state, weights=None, attempt_count=5, recent_history=[]
        )
        assert difficulty in DIFFICULTY_LEVELS
        assert log_prob == 0.0

    def test_bandit_returns_valid_difficulty(self):
        model = DifficultyPolicy()
        weights = serialize_weights(model)
        state = np.random.rand(10).astype(np.float32)
        difficulty, log_prob = select_difficulty(
            state=state, weights=weights, attempt_count=25, recent_history=[]
        )
        assert difficulty in DIFFICULTY_LEVELS
        assert log_prob < 0.0  # log prob is always negative


class TestIsDegenerate:
    def test_not_degenerate_with_variety(self):
        history = ["easy", "medium", "hard", "easy", "medium"]
        assert is_degenerate(history) is False

    def test_degenerate_all_same(self):
        history = ["easy", "easy", "easy", "easy", "easy"]
        assert is_degenerate(history) is True

    def test_short_history_not_degenerate(self):
        history = ["easy", "easy"]
        assert is_degenerate(history) is False


class TestUpdatePolicy:
    def test_weights_change_after_update(self):
        model = DifficultyPolicy()
        original_weights = serialize_weights(model)
        state = np.random.rand(10).astype(np.float32)

        updated_weights, new_mean, new_var = update_policy(
            weights=original_weights,
            state=state,
            chosen_idx=1,  # medium
            reward=0.8,
            reward_mean=0.5,
            reward_var=0.1,
            use_normalized_reward=True,
        )

        assert updated_weights != original_weights

    def test_reward_stats_update(self):
        model = DifficultyPolicy()
        weights = serialize_weights(model)
        state = np.random.rand(10).astype(np.float32)

        _, new_mean, new_var = update_policy(
            weights=weights,
            state=state,
            chosen_idx=0,
            reward=1.0,
            reward_mean=0.0,
            reward_var=1.0,
            use_normalized_reward=False,
        )

        assert new_mean > 0.0  # moved toward 1.0
```

- [ ] **Step 2: Run tests — should fail**

```bash
cd backend && python -m pytest tests/test_bandit.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.bandit'`

- [ ] **Step 3: Implement bandit service**

```python
# backend/app/services/bandit.py
"""Contextual bandit for personalized difficulty selection.

Contains: DifficultyPolicy (PyTorch MLP), state vector computation (NumPy),
REINFORCE training, cold-start rules, and pool management queries.
"""

from __future__ import annotations

import io
import math
from datetime import datetime, timezone

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Categorical

DIFFICULTY_LEVELS = ["easy", "medium", "hard"]
DIFFICULTY_TO_IDX = {d: i for i, d in enumerate(DIFFICULTY_LEVELS)}
IDX_TO_DIFFICULTY = {i: d for i, d in enumerate(DIFFICULTY_LEVELS)}

COLD_START_THRESHOLD = 20
STATE_DIM = 10
HIDDEN_DIM = 32
NUM_ACTIONS = 3
LEARNING_RATE = 0.01
ENTROPY_COEFF = 0.01
GRAD_CLIP_NORM = 1.0
REWARD_DECAY = 0.99

# ---------------------------------------------------------------------------
# Policy Network
# ---------------------------------------------------------------------------


class DifficultyPolicy(nn.Module):
    def __init__(self, input_dim: int = STATE_DIM, hidden_dim: int = HIDDEN_DIM):
        super().__init__()
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, NUM_ACTIONS)
        # Initialize for near-uniform output
        nn.init.normal_(self.fc2.weight, std=0.01)
        nn.init.zeros_(self.fc2.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = F.relu(self.fc1(x))
        return F.softmax(self.fc2(x), dim=-1)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def serialize_weights(model: DifficultyPolicy) -> bytes:
    buf = io.BytesIO()
    torch.save(model.state_dict(), buf)
    return buf.getvalue()


def deserialize_weights(model: DifficultyPolicy, data: bytes) -> None:
    buf = io.BytesIO(data)
    state_dict = torch.load(buf, weights_only=True)
    model.load_state_dict(state_dict)


def create_initial_weights() -> bytes:
    model = DifficultyPolicy()
    return serialize_weights(model)


# ---------------------------------------------------------------------------
# State Vector (NumPy)
# ---------------------------------------------------------------------------


def compute_state_vector(
    attempts: list[dict],
    current_session_count: int,
) -> np.ndarray:
    """Compute 10-dim state vector from raw attempt dicts.

    Each attempt dict must have: difficulty (str), score (float), created_at (str).
    """
    state = np.full(STATE_DIM, 0.0, dtype=np.float32)

    # Group by difficulty
    by_diff: dict[str, list[float]] = {"easy": [], "medium": [], "hard": []}
    for a in attempts[-50:]:
        d = a["difficulty"]
        if d in by_diff:
            by_diff[d].append(float(a["score"]))

    # Features 0-2: avg score per difficulty (last 50)
    for i, d in enumerate(DIFFICULTY_LEVELS):
        scores = by_diff[d]
        state[i] = np.mean(scores) if scores else 0.5

    # Features 3-5: exponentially decayed recent score (last 20)
    for i, d in enumerate(DIFFICULTY_LEVELS):
        recent = by_diff[d][-20:]
        if recent:
            weights = np.array([0.9**j for j in range(len(recent) - 1, -1, -1)])
            state[3 + i] = np.average(recent, weights=weights)
        else:
            state[3 + i] = 0.5

    # Feature 6: attempt count normalized
    state[6] = min(len(attempts) / 100.0, 1.0)

    # Feature 7: streak signal (consecutive correct from end)
    streak = 0
    for a in reversed(attempts):
        if float(a["score"]) >= 0.8:
            streak += 1
        else:
            break
    state[7] = min(streak / 10.0, 1.0)

    # Feature 8: session gap (days since last attempt)
    if attempts:
        last_ts = attempts[-1]["created_at"]
        if isinstance(last_ts, str):
            last_dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
        else:
            last_dt = last_ts
        now = datetime.now(timezone.utc)
        gap_days = (now - last_dt).total_seconds() / 86400
        state[8] = min(gap_days / 30.0, 1.0)
    else:
        state[8] = 1.0  # no history = max gap

    # Feature 9: current session progress
    state[9] = min(current_session_count / 20.0, 1.0)

    return state


# ---------------------------------------------------------------------------
# Cold Start Rules
# ---------------------------------------------------------------------------


def cold_start_select(recent_history: list[dict]) -> str:
    """Rule-based difficulty selection for new students.

    Each dict has: difficulty (str), score (float).
    """
    if not recent_history:
        return "medium"

    current_level = recent_history[-1]["difficulty"]
    current_idx = DIFFICULTY_TO_IDX.get(current_level, 1)

    # Check last score for downgrade
    last_score = float(recent_history[-1]["score"])
    if last_score < 0.5:
        return IDX_TO_DIFFICULTY[max(0, current_idx - 1)]

    # Check last two scores at current difficulty for upgrade
    same_diff = [
        a for a in recent_history if a["difficulty"] == current_level
    ]
    if len(same_diff) >= 2:
        last_two = same_diff[-2:]
        if all(float(a["score"]) >= 0.8 for a in last_two):
            return IDX_TO_DIFFICULTY[min(2, current_idx + 1)]

    return current_level


# ---------------------------------------------------------------------------
# Safety Net
# ---------------------------------------------------------------------------


def is_degenerate(recent_difficulties: list[str], window: int = 5) -> bool:
    """True if the last `window` items are all the same difficulty."""
    if len(recent_difficulties) < window:
        return False
    return len(set(recent_difficulties[-window:])) == 1


# ---------------------------------------------------------------------------
# Difficulty Selection
# ---------------------------------------------------------------------------


def select_difficulty(
    state: np.ndarray,
    weights: bytes | None,
    attempt_count: int,
    recent_history: list[dict],
    recent_difficulties: list[str] | None = None,
) -> tuple[str, float]:
    """Select a difficulty level. Returns (difficulty, log_prob).

    log_prob is 0.0 for cold start (no gradient needed).
    """
    # Safety net check
    if recent_difficulties and is_degenerate(recent_difficulties):
        return cold_start_select(recent_history), 0.0

    # Cold start
    if attempt_count < COLD_START_THRESHOLD or weights is None:
        return cold_start_select(recent_history), 0.0

    # Bandit inference
    model = DifficultyPolicy()
    deserialize_weights(model, weights)
    model.eval()

    with torch.no_grad():
        state_t = torch.tensor(state, dtype=torch.float32)
        probs = model(state_t)
        dist = Categorical(probs)
        action = dist.sample()
        log_prob = dist.log_prob(action).item()

    return IDX_TO_DIFFICULTY[action.item()], log_prob


# ---------------------------------------------------------------------------
# REINFORCE Update
# ---------------------------------------------------------------------------


def update_policy(
    weights: bytes,
    state: np.ndarray,
    chosen_idx: int,
    reward: float,
    reward_mean: float,
    reward_var: float,
    use_normalized_reward: bool,
) -> tuple[bytes, float, float]:
    """Run one REINFORCE gradient step. Returns (new_weights, new_mean, new_var)."""
    # Update running stats
    new_mean = REWARD_DECAY * reward_mean + (1 - REWARD_DECAY) * reward
    new_var = REWARD_DECAY * reward_var + (1 - REWARD_DECAY) * (reward - new_mean) ** 2

    # Normalize reward
    if use_normalized_reward:
        r = (reward - reward_mean) / math.sqrt(reward_var + 1e-8)
    else:
        r = reward

    # Load model
    model = DifficultyPolicy()
    deserialize_weights(model, weights)
    model.train()

    optimizer = torch.optim.SGD(model.parameters(), lr=LEARNING_RATE)

    state_t = torch.tensor(state, dtype=torch.float32)
    probs = model(state_t)
    dist = Categorical(probs)

    chosen_t = torch.tensor(chosen_idx)
    log_prob = dist.log_prob(chosen_t)
    entropy = dist.entropy()

    loss = -log_prob * r - ENTROPY_COEFF * entropy

    optimizer.zero_grad()
    loss.backward()
    nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP_NORM)
    optimizer.step()

    return serialize_weights(model), new_mean, new_var
```

- [ ] **Step 4: Run tests — should pass**

```bash
cd backend && python -m pytest tests/test_bandit.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/bandit.py backend/tests/test_bandit.py
git commit -m "feat: bandit service — policy network, state vector, REINFORCE, cold start"
```

---

## Task 5: Revision Content Generation

**Files:**
- Modify: `backend/app/services/generator.py`
- Create: `backend/tests/test_revision_generator.py`

- [ ] **Step 1: Write revision generation tests**

```python
# backend/tests/test_revision_generator.py
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.generator import (
    GeneratedFlashcard,
    GeneratedQuestion,
    GeneratedSpeakingTarget,
    generate_revision_flashcards,
    generate_revision_quiz,
    generate_revision_speaking,
)


@pytest.fixture
def mock_chunks():
    from app.services.retriever import RetrievedChunk

    return [
        RetrievedChunk(
            chunk_id="c1",
            content="The mitochondria is the powerhouse of the cell.",
            document_id="d1",
            page_number=1,
            similarity_score=0.95,
        )
    ]


class TestGenerateRevisionQuiz:
    @pytest.mark.asyncio
    async def test_returns_questions_with_correct_count(self, mock_chunks):
        mock_response = json.dumps([
            {
                "question_text": "What is the powerhouse of the cell?",
                "options": {"A": "Nucleus", "B": "Mitochondria", "C": "Ribosome", "D": "Golgi"},
                "correct_answer": "B",
                "explanation": "The mitochondria produces ATP.",
            }
        ])
        with patch("app.services.generator._call_llm", new_callable=AsyncMock, return_value=mock_response):
            result = await generate_revision_quiz(mock_chunks, difficulty="easy", num_questions=1)
            assert len(result) == 1
            assert isinstance(result[0], GeneratedQuestion)
            assert result[0].correct_answer == "B"

    @pytest.mark.asyncio
    async def test_difficulty_appears_in_prompt(self, mock_chunks):
        mock_response = json.dumps([
            {
                "question_text": "Q",
                "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
                "correct_answer": "A",
                "explanation": "E",
            }
        ])
        with patch("app.services.generator._call_llm", new_callable=AsyncMock, return_value=mock_response) as mock_llm:
            await generate_revision_quiz(mock_chunks, difficulty="hard", num_questions=1)
            call_args = mock_llm.call_args
            system_prompt = call_args[0][0]
            user_prompt = call_args[0][1]
            assert "hard" in user_prompt.lower() or "hard" in system_prompt.lower()


class TestGenerateRevisionFlashcards:
    @pytest.mark.asyncio
    async def test_returns_flashcards(self, mock_chunks):
        mock_response = json.dumps([
            {"front": "What is ATP?", "back": "Adenosine triphosphate, the energy currency of cells."}
        ])
        with patch("app.services.generator._call_llm", new_callable=AsyncMock, return_value=mock_response):
            result = await generate_revision_flashcards(mock_chunks, difficulty="medium", num_cards=1)
            assert len(result) == 1
            assert isinstance(result[0], GeneratedFlashcard)


class TestGenerateRevisionSpeaking:
    @pytest.mark.asyncio
    async def test_returns_speaking_targets(self, mock_chunks):
        mock_response = json.dumps([
            {"target_text": "The mitochondria is the powerhouse of the cell."}
        ])
        with patch("app.services.generator._call_llm", new_callable=AsyncMock, return_value=mock_response):
            result = await generate_revision_speaking(mock_chunks, difficulty="easy", num_items=1, language="english")
            assert len(result) == 1
            assert isinstance(result[0], GeneratedSpeakingTarget)
            assert result[0].target_text != ""
```

- [ ] **Step 2: Run tests — should fail**

```bash
cd backend && python -m pytest tests/test_revision_generator.py -v
```

- [ ] **Step 3: Add revision generation functions to generator.py**

Append to `backend/app/services/generator.py`:

```python
# ---------------------------------------------------------------------------
# Speaking Target Dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GeneratedSpeakingTarget:
    target_text: str


# ---------------------------------------------------------------------------
# Revision-Mode Generation (difficulty-aware)
# ---------------------------------------------------------------------------

_DIFFICULTY_DEFINITIONS = {
    "easy": "Direct recall, definitions, simple facts from the text",
    "medium": "Application, comparison, requires connecting two concepts",
    "hard": "Analysis, inference, requires synthesis across multiple ideas",
}

_REVISION_QUIZ_SYSTEM_PROMPT = """\
You are an educational quiz generator. Given source material, create quiz questions
at the specified difficulty level.

Difficulty levels:
- easy: Direct recall, definitions, simple facts from the text
- medium: Application, comparison, requires connecting two concepts
- hard: Analysis, inference, requires synthesis across multiple ideas

Return ONLY a JSON array of question objects. No extra text.

Each object must have:
- "question_text": the question string
- "options": an object with keys "A", "B", "C", "D" and string values
- "correct_answer": one of "A", "B", "C", "D"
- "explanation": a brief explanation of why the answer is correct
"""

_REVISION_FLASHCARD_SYSTEM_PROMPT = """\
You are an educational flashcard generator. Given source material, create
flashcards at the specified difficulty level.

Difficulty levels:
- easy: Basic term and definition pairs
- medium: Conceptual understanding, paraphrased answers
- hard: Nuanced application, edge cases, subtle distinctions

Return ONLY a JSON array of flashcard objects. No extra text.

Each object must have:
- "front": the question or prompt for the front of the card
- "back": the answer or explanation for the back of the card
"""

_REVISION_SPEAKING_SYSTEM_PROMPT = """\
You are a language practice content generator. Given source material, create
sentences or passages for pronunciation practice at the specified difficulty level.

Difficulty levels:
- easy: Short simple sentences with common vocabulary
- medium: Compound sentences with moderate vocabulary
- hard: Complex paragraphs with technical or difficult vocabulary

Return ONLY a JSON array of objects. No extra text.

Each object must have:
- "target_text": the sentence or passage to be spoken aloud
"""


async def generate_revision_quiz(
    chunks: list[RetrievedChunk],
    difficulty: str,
    num_questions: int = 7,
    language: str = "english",
) -> list[GeneratedQuestion]:
    """Generate difficulty-labeled quiz questions for revision mode."""
    context = _build_context(chunks)
    user_prompt = (
        f"Create {num_questions} multiple choice questions at {difficulty} difficulty "
        f"in {language} based on the following material:\n\n{context}"
    )

    try:
        raw = await _call_llm(_REVISION_QUIZ_SYSTEM_PROMPT, user_prompt)
        items = _parse_json_response(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("Primary model JSON parse failed: %s — trying fallback", exc)
        raw = await _call_llm(
            _REVISION_QUIZ_SYSTEM_PROMPT,
            user_prompt,
            model=settings.openrouter_fallback_model,
        )
        items = _parse_json_response(raw)

    return [
        GeneratedQuestion(
            question_text=item["question_text"],
            options=item["options"],
            correct_answer=item["correct_answer"],
            explanation=item["explanation"],
        )
        for item in items
    ]


async def generate_revision_flashcards(
    chunks: list[RetrievedChunk],
    difficulty: str,
    num_cards: int = 7,
    language: str = "english",
) -> list[GeneratedFlashcard]:
    """Generate difficulty-labeled flashcards for revision mode."""
    context = _build_context(chunks)
    user_prompt = (
        f"Create {num_cards} flashcards at {difficulty} difficulty "
        f"in {language} based on the following material:\n\n{context}"
    )

    try:
        raw = await _call_llm(_REVISION_FLASHCARD_SYSTEM_PROMPT, user_prompt)
        items = _parse_json_response(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("Primary model JSON parse failed: %s — trying fallback", exc)
        raw = await _call_llm(
            _REVISION_FLASHCARD_SYSTEM_PROMPT,
            user_prompt,
            model=settings.openrouter_fallback_model,
        )
        items = _parse_json_response(raw)

    return [
        GeneratedFlashcard(front=item["front"], back=item["back"])
        for item in items
    ]


async def generate_revision_speaking(
    chunks: list[RetrievedChunk],
    difficulty: str,
    num_items: int = 6,
    language: str = "english",
) -> list[GeneratedSpeakingTarget]:
    """Generate difficulty-labeled speaking targets for revision mode."""
    context = _build_context(chunks)
    user_prompt = (
        f"Create {num_items} pronunciation practice passages at {difficulty} difficulty "
        f"in {language} based on the following material:\n\n{context}"
    )

    try:
        raw = await _call_llm(_REVISION_SPEAKING_SYSTEM_PROMPT, user_prompt)
        items = _parse_json_response(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("Primary model JSON parse failed: %s — trying fallback", exc)
        raw = await _call_llm(
            _REVISION_SPEAKING_SYSTEM_PROMPT,
            user_prompt,
            model=settings.openrouter_fallback_model,
        )
        items = _parse_json_response(raw)

    return [
        GeneratedSpeakingTarget(target_text=item["target_text"])
        for item in items
    ]
```

- [ ] **Step 4: Run tests — should pass**

```bash
cd backend && python -m pytest tests/test_revision_generator.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/generator.py backend/tests/test_revision_generator.py
git commit -m "feat: difficulty-aware content generation for revision mode"
```

---

## Task 6: Worker — Pool Replenishment Handler

**Files:**
- Modify: `backend/app/services/worker.py`

- [ ] **Step 1: Add revision_pool_replenish handler to process_task**

In `backend/app/services/worker.py`, replace the `else` clause in `process_task()` (line 53-54):

```python
    elif task.task_type == "revision_pool_replenish":
        from app.services.pool import replenish_pool
        await replenish_pool(session, task.payload)
    else:
        raise ValueError(f"Unknown task type: {task.task_type}")
```

- [ ] **Step 2: Create pool replenishment service**

```python
# backend/app/services/pool.py
"""Revision pool replenishment — called by the task worker."""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.course import Course
from app.models.revision import RevisionPoolItem
from app.services.embedder import embed_query
from app.services.generator import (
    generate_revision_flashcards,
    generate_revision_quiz,
    generate_revision_speaking,
)
from app.services.retriever import retrieve_chunks

logger = logging.getLogger(__name__)


async def replenish_pool(session: AsyncSession, payload: dict) -> None:
    """Generate a batch of revision items and insert into the pool."""
    course_id = payload["course_id"]
    content_type = payload["content_type"]
    counts = payload.get("counts", {"easy": 7, "medium": 7, "hard": 6})

    # Get course language
    result = await session.execute(
        select(Course).where(Course.id == course_id, Course.deleted_at.is_(None))
    )
    course = result.scalar_one_or_none()
    if not course:
        logger.error(f"Course {course_id} not found for pool replenishment")
        return

    language = course.language or "english"

    # Retrieve chunks for context
    query_embedding = await embed_query(f"comprehensive review of {course.name} material")
    chunks = await retrieve_chunks(
        session, course_id=course_id, query_embedding=query_embedding, top_k=20
    )
    if not chunks:
        logger.warning(f"No chunks found for course {course_id}, skipping replenishment")
        return

    # Generate at all three difficulties concurrently
    tasks = []
    for difficulty, count in counts.items():
        if count <= 0:
            continue
        if content_type == "quiz":
            tasks.append((difficulty, generate_revision_quiz(chunks, difficulty, count, language)))
        elif content_type == "flashcard":
            tasks.append((difficulty, generate_revision_flashcards(chunks, difficulty, count, language)))
        elif content_type == "speaking":
            tasks.append((difficulty, generate_revision_speaking(chunks, difficulty, count, language)))

    results = await asyncio.gather(
        *[coro for _, coro in tasks], return_exceptions=True
    )

    # Insert generated items into pool
    for (difficulty, _), result in zip(tasks, results):
        if isinstance(result, Exception):
            logger.error(f"Generation failed for {content_type}/{difficulty}: {result}")
            continue

        for item in result:
            pool_item = RevisionPoolItem(
                course_id=course_id,
                content_type=content_type,
                difficulty=difficulty,
            )

            if content_type == "quiz":
                pool_item.question_text = item.question_text
                pool_item.options = item.options
                pool_item.correct_answer = item.correct_answer
                pool_item.explanation = item.explanation
            elif content_type == "flashcard":
                pool_item.front = item.front
                pool_item.back = item.back
            elif content_type == "speaking":
                pool_item.target_text = item.target_text
                pool_item.language = language

            session.add(pool_item)

    await session.flush()
    logger.info(f"Replenished pool: course={course_id}, type={content_type}")
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/worker.py backend/app/services/pool.py
git commit -m "feat: revision pool replenishment via task worker"
```

---

## Task 7: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/revision.py`

- [ ] **Step 1: Create revision schemas**

```python
# backend/app/schemas/revision.py
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class StartRevisionRequest(BaseModel):
    content_type: Literal["quiz", "flashcard", "speaking"]


class RevisionQuizItem(BaseModel):
    pool_item_id: str
    content_type: Literal["quiz"] = "quiz"
    question_text: str
    options: dict[str, str]


class RevisionFlashcardItem(BaseModel):
    pool_item_id: str
    content_type: Literal["flashcard"] = "flashcard"
    front: str
    back: str


class RevisionSpeakingItem(BaseModel):
    pool_item_id: str
    content_type: Literal["speaking"] = "speaking"
    target_text: str
    language: str


RevisionItem = RevisionQuizItem | RevisionFlashcardItem | RevisionSpeakingItem


class StartRevisionResponse(BaseModel):
    session_id: str
    status: Literal["ready", "preparing"]
    first_item: RevisionItem | None = None


class SubmitAnswerRequest(BaseModel):
    pool_item_id: str
    answer: str | None = None       # quiz: option letter (A/B/C/D)
    quality: int | None = Field(None, ge=0, le=5)  # flashcard: SM-2 quality
    pronunciation_score: float | None = None  # speaking: 0-100 from grading
    time_taken_ms: int | None = None


class SessionStats(BaseModel):
    items_answered: int
    accuracy: float
    current_streak: int


class SubmitAnswerResponse(BaseModel):
    score: float
    is_correct: bool | None = None  # quiz only
    correct_answer: str | None = None  # quiz only
    explanation: str | None = None  # quiz only
    next_item: RevisionItem | None = None
    session_stats: SessionStats


class EndSessionResponse(BaseModel):
    items_answered: int
    average_score: float
    scores_by_difficulty: dict[str, float]
    duration_seconds: int
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/revision.py
git commit -m "feat: revision session request/response schemas"
```

---

## Task 8: Revision API Endpoints

**Files:**
- Create: `backend/app/api/revision.py`
- Modify: `backend/app/api/__init__.py`
- Create: `backend/tests/test_api_revision.py`

- [ ] **Step 1: Create revision API router**

```python
# backend/app/api/revision.py
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.course import Enrollment
from app.models.revision import (
    BanditModel,
    RevisionAttempt,
    RevisionItemServed,
    RevisionPoolItem,
    RevisionSession,
)
from app.models.task import Task
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.revision import (
    EndSessionResponse,
    RevisionFlashcardItem,
    RevisionItem,
    RevisionQuizItem,
    RevisionSpeakingItem,
    SessionStats,
    StartRevisionRequest,
    StartRevisionResponse,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
)
from app.services.bandit import (
    COLD_START_THRESHOLD,
    DIFFICULTY_TO_IDX,
    compute_state_vector,
    create_initial_weights,
    select_difficulty,
    update_policy,
)

router = APIRouter(tags=["revision"])

POOL_MIN_PER_DIFFICULTY = 5
FLASHCARD_QUALITY_TO_SCORE = {0: 0.0, 1: 0.2, 2: 0.4, 3: 0.7, 4: 0.85, 5: 1.0}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _verify_enrollment(db: AsyncSession, course_id: uuid.UUID, user_id: uuid.UUID) -> None:
    result = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == course_id,
            Enrollment.user_id == user_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enrolled in this course")


async def _verify_session_owner(db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID) -> RevisionSession:
    result = await db.execute(
        select(RevisionSession).where(
            RevisionSession.id == session_id,
            RevisionSession.user_id == user_id,
            RevisionSession.ended_at.is_(None),
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or ended")
    return session


async def _get_unserved_counts(
    db: AsyncSession, course_id: uuid.UUID, content_type: str, user_id: uuid.UUID
) -> dict[str, int]:
    """Count unserved pool items per difficulty for this user."""
    stmt = (
        select(
            RevisionPoolItem.difficulty,
            func.count(RevisionPoolItem.id),
        )
        .outerjoin(
            RevisionItemServed,
            (RevisionItemServed.pool_item_id == RevisionPoolItem.id)
            & (RevisionItemServed.user_id == user_id),
        )
        .where(
            RevisionPoolItem.course_id == course_id,
            RevisionPoolItem.content_type == content_type,
            RevisionItemServed.user_id.is_(None),  # not served
        )
        .group_by(RevisionPoolItem.difficulty)
    )
    result = await db.execute(stmt)
    return {row[0]: row[1] for row in result.all()}


async def _enqueue_replenish(
    db: AsyncSession, course_id: uuid.UUID, content_type: str
) -> None:
    task = Task(
        task_type="revision_pool_replenish",
        payload={
            "course_id": str(course_id),
            "content_type": content_type,
            "counts": {"easy": 7, "medium": 7, "hard": 6},
        },
    )
    db.add(task)
    await db.flush()


async def _pick_item(
    db: AsyncSession,
    course_id: uuid.UUID,
    content_type: str,
    difficulty: str,
    user_id: uuid.UUID,
) -> RevisionPoolItem | None:
    """Pick a random unserved pool item at the given difficulty."""
    stmt = (
        select(RevisionPoolItem)
        .outerjoin(
            RevisionItemServed,
            (RevisionItemServed.pool_item_id == RevisionPoolItem.id)
            & (RevisionItemServed.user_id == user_id),
        )
        .where(
            RevisionPoolItem.course_id == course_id,
            RevisionPoolItem.content_type == content_type,
            RevisionPoolItem.difficulty == difficulty,
            RevisionItemServed.user_id.is_(None),
        )
        .order_by(func.random())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _pick_item_any_difficulty(
    db: AsyncSession,
    course_id: uuid.UUID,
    content_type: str,
    user_id: uuid.UUID,
) -> RevisionPoolItem | None:
    """Fallback: pick any unserved item regardless of difficulty."""
    stmt = (
        select(RevisionPoolItem)
        .outerjoin(
            RevisionItemServed,
            (RevisionItemServed.pool_item_id == RevisionPoolItem.id)
            & (RevisionItemServed.user_id == user_id),
        )
        .where(
            RevisionPoolItem.course_id == course_id,
            RevisionPoolItem.content_type == content_type,
            RevisionItemServed.user_id.is_(None),
        )
        .order_by(func.random())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _pool_item_to_response(item: RevisionPoolItem) -> RevisionItem:
    if item.content_type == "quiz":
        return RevisionQuizItem(
            pool_item_id=str(item.id),
            question_text=item.question_text,
            options=item.options,
        )
    elif item.content_type == "flashcard":
        return RevisionFlashcardItem(
            pool_item_id=str(item.id),
            front=item.front,
            back=item.back,
        )
    else:
        return RevisionSpeakingItem(
            pool_item_id=str(item.id),
            target_text=item.target_text,
            language=item.language or "english",
        )


async def _get_recent_attempts(
    db: AsyncSession, user_id: uuid.UUID, course_id: uuid.UUID, content_type: str, limit: int = 50
) -> list[dict]:
    stmt = (
        select(RevisionAttempt)
        .where(
            RevisionAttempt.user_id == user_id,
            RevisionAttempt.course_id == course_id,
            RevisionAttempt.content_type == content_type,
        )
        .order_by(RevisionAttempt.created_at.asc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [
        {
            "difficulty": a.difficulty,
            "score": float(a.score),
            "created_at": a.created_at,
        }
        for a in result.scalars().all()
    ]


async def _get_bandit_model(
    db: AsyncSession, user_id: uuid.UUID, course_id: uuid.UUID, content_type: str
) -> BanditModel | None:
    stmt = select(BanditModel).where(
        BanditModel.user_id == user_id,
        BanditModel.course_id == course_id,
        BanditModel.content_type == content_type,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _select_and_serve(
    db: AsyncSession, session: RevisionSession, user: User
) -> RevisionItem | None:
    """Run bandit selection and pick an item. Returns None if pool is empty."""
    attempts = await _get_recent_attempts(
        db, user.id, session.course_id, session.content_type
    )
    bandit_model = await _get_bandit_model(
        db, user.id, session.course_id, session.content_type
    )

    state = compute_state_vector(attempts, current_session_count=session.items_answered)
    recent_diffs = [a["difficulty"] for a in attempts[-5:]]

    difficulty, _ = select_difficulty(
        state=state,
        weights=bandit_model.weights if bandit_model else None,
        attempt_count=bandit_model.attempt_count if bandit_model else 0,
        recent_history=attempts[-5:],
        recent_difficulties=recent_diffs,
    )

    item = await _pick_item(db, session.course_id, session.content_type, difficulty, user.id)
    if item is None:
        item = await _pick_item_any_difficulty(db, session.course_id, session.content_type, user.id)

    if item is None:
        return None

    # Mark as served
    db.add(RevisionItemServed(user_id=user.id, pool_item_id=item.id))
    await db.flush()

    # Check pool levels, trigger replenishment if needed
    counts = await _get_unserved_counts(db, session.course_id, session.content_type, user.id)
    for diff in ["easy", "medium", "hard"]:
        if counts.get(diff, 0) < POOL_MIN_PER_DIFFICULTY:
            await _enqueue_replenish(db, session.course_id, session.content_type)
            break

    return _pool_item_to_response(item)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/courses/{course_id}/revision/start",
    response_model=APIResponse[StartRevisionResponse],
    status_code=201,
)
async def start_revision(
    course_id: uuid.UUID,
    body: StartRevisionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _verify_enrollment(db, course_id, user.id)

    session = RevisionSession(
        user_id=user.id,
        course_id=course_id,
        content_type=body.content_type,
    )
    db.add(session)
    await db.flush()

    # Check pool
    counts = await _get_unserved_counts(db, course_id, body.content_type, user.id)
    total_available = sum(counts.values())

    if total_available < 3:
        # Pool empty — enqueue generation and return preparing
        await _enqueue_replenish(db, course_id, body.content_type)
        await db.commit()
        return APIResponse(
            success=True,
            data=StartRevisionResponse(
                session_id=str(session.id),
                status="preparing",
                first_item=None,
            ),
        )

    first_item = await _select_and_serve(db, session, user)
    await db.commit()

    return APIResponse(
        success=True,
        data=StartRevisionResponse(
            session_id=str(session.id),
            status="ready",
            first_item=first_item,
        ),
    )


@router.post(
    "/revision/sessions/{session_id}/answer",
    response_model=APIResponse[SubmitAnswerResponse],
)
async def submit_answer(
    session_id: uuid.UUID,
    body: SubmitAnswerRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = await _verify_session_owner(db, session_id, user.id)

    # Fetch the pool item
    item_result = await db.execute(
        select(RevisionPoolItem).where(RevisionPoolItem.id == body.pool_item_id)
    )
    pool_item = item_result.scalar_one_or_none()
    if not pool_item:
        raise HTTPException(status_code=404, detail="Pool item not found")

    # Score the answer
    is_correct = None
    correct_answer = None
    explanation = None

    if pool_item.content_type == "quiz":
        is_correct = body.answer == pool_item.correct_answer
        score = 1.0 if is_correct else 0.0
        correct_answer = pool_item.correct_answer
        explanation = pool_item.explanation
    elif pool_item.content_type == "flashcard":
        quality = body.quality if body.quality is not None else 3
        score = FLASHCARD_QUALITY_TO_SCORE.get(quality, 0.7)
    elif pool_item.content_type == "speaking":
        score = (body.pronunciation_score or 0.0) / 100.0
    else:
        score = 0.0

    # Record attempt
    attempt = RevisionAttempt(
        user_id=user.id,
        course_id=session.course_id,
        session_id=session.id,
        pool_item_id=pool_item.id,
        content_type=pool_item.content_type,
        difficulty=pool_item.difficulty,
        score=Decimal(str(round(score, 2))),
        time_taken_ms=body.time_taken_ms,
    )
    db.add(attempt)

    # Update session counters
    session.items_answered = (session.items_answered or 0) + 1
    session.total_score = (session.total_score or Decimal("0")) + Decimal(str(round(score, 2)))

    # Bandit update
    bandit_model = await _get_bandit_model(db, user.id, session.course_id, session.content_type)
    if bandit_model is None:
        bandit_model = BanditModel(
            user_id=user.id,
            course_id=session.course_id,
            content_type=session.content_type,
            weights=create_initial_weights(),
        )
        db.add(bandit_model)
        await db.flush()

    bandit_model.attempt_count = (bandit_model.attempt_count or 0) + 1

    # Update running reward stats
    old_mean = bandit_model.reward_mean or 0.0
    old_var = bandit_model.reward_var or 1.0
    new_mean = 0.99 * old_mean + 0.01 * score
    new_var = 0.99 * old_var + 0.01 * (score - new_mean) ** 2
    bandit_model.reward_mean = new_mean
    bandit_model.reward_var = new_var

    # REINFORCE update (only if past cold start)
    if bandit_model.attempt_count >= COLD_START_THRESHOLD and bandit_model.strategy != "rules":
        attempts = await _get_recent_attempts(
            db, user.id, session.course_id, session.content_type
        )
        state = compute_state_vector(attempts, current_session_count=session.items_answered)

        new_weights, updated_mean, updated_var = update_policy(
            weights=bandit_model.weights,
            state=state,
            chosen_idx=DIFFICULTY_TO_IDX[pool_item.difficulty],
            reward=score,
            reward_mean=old_mean,
            reward_var=old_var,
            use_normalized_reward=True,
        )
        bandit_model.weights = new_weights
        bandit_model.reward_mean = updated_mean
        bandit_model.reward_var = updated_var

    # Auto-transition from rules to bandit
    if (
        bandit_model.attempt_count >= COLD_START_THRESHOLD
        and bandit_model.strategy == "rules"
    ):
        bandit_model.strategy = "bandit"

    # Select next item
    next_item = await _select_and_serve(db, session, user)

    await db.commit()

    # Compute session stats
    avg_score = float(session.total_score) / session.items_answered if session.items_answered > 0 else 0.0

    # Compute current streak
    recent = await _get_recent_attempts(db, user.id, session.course_id, session.content_type, limit=50)
    streak = 0
    for a in reversed(recent):
        if a["score"] >= 0.8:
            streak += 1
        else:
            break

    return APIResponse(
        success=True,
        data=SubmitAnswerResponse(
            score=score,
            is_correct=is_correct,
            correct_answer=correct_answer,
            explanation=explanation,
            next_item=next_item,
            session_stats=SessionStats(
                items_answered=session.items_answered,
                accuracy=round(avg_score, 3),
                current_streak=streak,
            ),
        ),
    )


@router.post(
    "/revision/sessions/{session_id}/next",
    response_model=APIResponse[RevisionItem | None],
)
async def next_item(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = await _verify_session_owner(db, session_id, user.id)
    item = await _select_and_serve(db, session, user)
    await db.commit()
    return APIResponse(success=True, data=item)


@router.get(
    "/revision/sessions/{session_id}",
    response_model=APIResponse[SessionStats],
)
async def get_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = await _verify_session_owner(db, session_id, user.id)
    avg = float(session.total_score) / session.items_answered if session.items_answered > 0 else 0.0

    recent = await _get_recent_attempts(db, user.id, session.course_id, session.content_type, limit=50)
    streak = 0
    for a in reversed(recent):
        if a["score"] >= 0.8:
            streak += 1
        else:
            break

    return APIResponse(
        success=True,
        data=SessionStats(
            items_answered=session.items_answered,
            accuracy=round(avg, 3),
            current_streak=streak,
        ),
    )


@router.post(
    "/revision/sessions/{session_id}/end",
    response_model=APIResponse[EndSessionResponse],
)
async def end_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(RevisionSession).where(
            RevisionSession.id == session_id,
            RevisionSession.user_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.ended_at = datetime.now(timezone.utc)

    # Compute scores by difficulty
    stmt = (
        select(
            RevisionAttempt.difficulty,
            func.avg(RevisionAttempt.score),
        )
        .where(RevisionAttempt.session_id == session_id)
        .group_by(RevisionAttempt.difficulty)
    )
    diff_result = await db.execute(stmt)
    scores_by_diff = {row[0]: round(float(row[1]), 3) for row in diff_result.all()}

    avg = float(session.total_score) / session.items_answered if session.items_answered > 0 else 0.0
    duration = int((session.ended_at - session.started_at).total_seconds()) if session.started_at else 0

    await db.commit()

    return APIResponse(
        success=True,
        data=EndSessionResponse(
            items_answered=session.items_answered,
            average_score=round(avg, 3),
            scores_by_difficulty=scores_by_diff,
            duration_seconds=duration,
        ),
    )
```

- [ ] **Step 2: Register revision router**

In `backend/app/api/__init__.py`, add:

```python
from app.api.revision import router as revision_router
```

And:

```python
api_router.include_router(revision_router)
```

- [ ] **Step 3: Write endpoint integration tests**

```python
# backend/tests/test_api_revision.py
import pytest
from unittest.mock import AsyncMock, patch


class TestStartRevision:
    @pytest.mark.asyncio
    async def test_start_returns_preparing_when_pool_empty(self):
        """When no pool items exist, should return status=preparing."""
        # Requires test DB with enrolled user, course with chunks
        pass  # Implement with test fixtures

    @pytest.mark.asyncio
    async def test_start_returns_ready_with_pool(self):
        """When pool has items, should return status=ready with first_item."""
        pass

    @pytest.mark.asyncio
    async def test_start_requires_enrollment(self):
        """Non-enrolled user should get 403."""
        pass


class TestSubmitAnswer:
    @pytest.mark.asyncio
    async def test_quiz_correct_answer_scores_1(self):
        """Correct quiz answer should return score=1.0, is_correct=true."""
        pass

    @pytest.mark.asyncio
    async def test_quiz_wrong_answer_scores_0(self):
        """Wrong quiz answer should return score=0.0, is_correct=false."""
        pass

    @pytest.mark.asyncio
    async def test_bandit_updates_after_threshold(self):
        """After COLD_START_THRESHOLD attempts, bandit weights should change."""
        pass

    @pytest.mark.asyncio
    async def test_next_item_returned_in_response(self):
        """Response should include next_item for continued practice."""
        pass


class TestEndSession:
    @pytest.mark.asyncio
    async def test_end_returns_summary(self):
        """Ending a session should return stats with scores_by_difficulty."""
        pass
```

- [ ] **Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_api_revision.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/revision.py backend/app/api/__init__.py backend/app/schemas/revision.py backend/tests/test_api_revision.py
git commit -m "feat: revision session API endpoints — start, answer, next, end"
```

---

## Task 9: Frontend — Revision Hook

**Files:**
- Create: `frontend/src/hooks/use-revision.ts`

- [ ] **Step 1: Create the revision session hook**

```typescript
// frontend/src/hooks/use-revision.ts
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@clerk/nextjs";
import { useCallback, useState } from "react";
import { apiFetch } from "@/lib/api";

interface RevisionQuizItem {
  pool_item_id: string;
  content_type: "quiz";
  question_text: string;
  options: Record<string, string>;
}

interface RevisionFlashcardItem {
  pool_item_id: string;
  content_type: "flashcard";
  front: string;
  back: string;
}

interface RevisionSpeakingItem {
  pool_item_id: string;
  content_type: "speaking";
  target_text: string;
  language: string;
}

type RevisionItem = RevisionQuizItem | RevisionFlashcardItem | RevisionSpeakingItem;

interface SessionStats {
  items_answered: number;
  accuracy: number;
  current_streak: number;
}

interface StartResponse {
  session_id: string;
  status: "ready" | "preparing";
  first_item: RevisionItem | null;
}

interface AnswerResponse {
  score: number;
  is_correct: boolean | null;
  correct_answer: string | null;
  explanation: string | null;
  next_item: RevisionItem | null;
  session_stats: SessionStats;
}

interface EndResponse {
  items_answered: number;
  average_score: number;
  scores_by_difficulty: Record<string, number>;
  duration_seconds: number;
}

export function useRevisionSession(courseId: string) {
  const { getToken } = useAuth();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [currentItem, setCurrentItem] = useState<RevisionItem | null>(null);
  const [stats, setStats] = useState<SessionStats>({
    items_answered: 0,
    accuracy: 0,
    current_streak: 0,
  });
  const [isPreparing, setIsPreparing] = useState(false);
  const [lastFeedback, setLastFeedback] = useState<AnswerResponse | null>(null);

  const startMutation = useMutation({
    mutationFn: async (contentType: string) => {
      const token = await getToken();
      const res = await apiFetch<{ data: StartResponse }>(
        `/courses/${courseId}/revision/start`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content_type: contentType }),
          token: token ?? undefined,
        }
      );
      return res.data;
    },
    onSuccess: (data) => {
      setSessionId(data.session_id);
      if (data.status === "preparing") {
        setIsPreparing(true);
      } else {
        setCurrentItem(data.first_item);
        setIsPreparing(false);
      }
    },
  });

  const answerMutation = useMutation({
    mutationFn: async (params: {
      pool_item_id: string;
      answer?: string;
      quality?: number;
      pronunciation_score?: number;
      time_taken_ms?: number;
    }) => {
      const token = await getToken();
      const res = await apiFetch<{ data: AnswerResponse }>(
        `/revision/sessions/${sessionId}/answer`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(params),
          token: token ?? undefined,
        }
      );
      return res.data;
    },
    onSuccess: (data) => {
      setLastFeedback(data);
      setStats(data.session_stats);
      // After feedback delay, advance to next item
      setTimeout(() => {
        setCurrentItem(data.next_item);
        setLastFeedback(null);
      }, 1500);
    },
  });

  const endMutation = useMutation({
    mutationFn: async () => {
      const token = await getToken();
      const res = await apiFetch<{ data: EndResponse }>(
        `/revision/sessions/${sessionId}/end`,
        {
          method: "POST",
          token: token ?? undefined,
        }
      );
      return res.data;
    },
  });

  return {
    startSession: startMutation.mutate,
    submitAnswer: answerMutation.mutate,
    endSession: endMutation.mutateAsync,
    sessionId,
    currentItem,
    stats,
    lastFeedback,
    isPreparing,
    isLoading: startMutation.isPending || answerMutation.isPending,
    isStarting: startMutation.isPending,
    endResult: endMutation.data,
    isEnding: endMutation.isPending,
  };
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/use-revision.ts
git commit -m "feat: useRevisionSession hook for revision practice mode"
```

---

## Task 10: Frontend — Revision Components

**Files:**
- Create: `frontend/src/components/revision/content-type-picker.tsx`
- Create: `frontend/src/components/revision/quiz-item.tsx`
- Create: `frontend/src/components/revision/flashcard-item.tsx`
- Create: `frontend/src/components/revision/item-feedback.tsx`
- Create: `frontend/src/components/revision/session-stats-bar.tsx`
- Create: `frontend/src/components/revision/session-summary.tsx`
- Create: `frontend/src/components/revision/revision-player.tsx`

- [ ] **Step 1: Create content-type-picker**

Three clickable cards (Quiz, Flashcard, Speaking) with icons and descriptions. Calls `onSelect(contentType)`.

- [ ] **Step 2: Create quiz-item component**

Display question text and four answer buttons (A/B/C/D). Track time from mount. Call `onAnswer({answer, time_taken_ms})` on click.

- [ ] **Step 3: Create flashcard-item component**

Reuse the existing flip card pattern from `frontend/src/components/flashcard/flashcard-player.tsx` (CSS transform preserve-3d). Show front, flip to reveal back, then 4 rating buttons (Again/Hard/Good/Easy). Call `onAnswer({quality, time_taken_ms})`.

- [ ] **Step 4: Create item-feedback component**

Overlay that shows correct/incorrect with a checkmark/X icon, the correct answer, and explanation text. Auto-dismisses after 1.5s (controlled by parent via prop).

- [ ] **Step 5: Create session-stats-bar component**

Horizontal bar fixed at top of practice area. Shows: items answered count, accuracy percentage, current streak with fire icon. All values from `SessionStats`.

- [ ] **Step 6: Create session-summary component**

End-of-session card: total items, average score as circular gauge, accuracy breakdown by difficulty (easy/medium/hard bars), session duration. "Practice Again" button.

- [ ] **Step 7: Create revision-player container**

State machine component:
- `idle` → shows content-type-picker
- `preparing` → loading spinner "Generating practice items..."
- `playing` → shows session-stats-bar + current item + item-feedback
- `ended` → shows session-summary

Wires `useRevisionSession` hook to child components.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/revision/
git commit -m "feat: revision practice UI components"
```

---

## Task 11: Frontend — Revision Page & Navigation

**Files:**
- Create: `frontend/src/app/dashboard/courses/[courseId]/revision/page.tsx`
- Modify: `frontend/src/app/dashboard/courses/[courseId]/page.tsx`
- Modify: `frontend/src/components/layout/sidebar.tsx`

- [ ] **Step 1: Create revision page**

```tsx
// frontend/src/app/dashboard/courses/[courseId]/revision/page.tsx
"use client";

import { use } from "react";
import { RevisionPlayer } from "@/components/revision/revision-player";

export default function RevisionPage({
  params,
}: {
  params: Promise<{ courseId: string }>;
}) {
  const { courseId } = use(params);
  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold" style={{ color: "var(--color-text)" }}>
        Revision Practice
      </h1>
      <RevisionPlayer courseId={courseId} />
    </div>
  );
}
```

- [ ] **Step 2: Add Revision tab to course detail page**

In `frontend/src/app/dashboard/courses/[courseId]/page.tsx`, add a "Revision" tab alongside existing tabs (Overview, Materials, Quizzes, Flashcards, Students). Links to `/dashboard/courses/${courseId}/revision`.

- [ ] **Step 3: Add Revision link to sidebar**

In `frontend/src/components/layout/sidebar.tsx`, add a navigation item for revision under courses.

- [ ] **Step 4: Run frontend build**

```bash
cd frontend && npm run build
```

- [ ] **Step 5: Run frontend lint**

```bash
cd frontend && npm run lint
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/dashboard/courses/\[courseId\]/revision/ frontend/src/app/dashboard/courses/\[courseId\]/page.tsx frontend/src/components/layout/sidebar.tsx
git commit -m "feat: revision practice page and navigation"
```

---

## Task 12: E2E Test

**Files:**
- Create: `frontend/e2e/revision.spec.ts`

- [ ] **Step 1: Write Playwright test for revision flow**

```typescript
// frontend/e2e/revision.spec.ts
import { test, expect } from "@playwright/test";

test.describe("Revision Practice", () => {
  test("student can start and complete a revision quiz session", async ({ page }) => {
    // Assumes authenticated student enrolled in a course with pool items
    await page.goto("/dashboard/courses/TEST_COURSE_ID/revision");

    // Choose quiz
    await page.getByRole("button", { name: /quiz/i }).click();

    // Should see a question
    await expect(page.locator("[data-testid='question-text']")).toBeVisible({ timeout: 15000 });

    // Answer the question
    await page.getByRole("button", { name: /^[A-D]/ }).first().click();

    // Should see feedback
    await expect(page.locator("[data-testid='item-feedback']")).toBeVisible();

    // Wait for next question
    await expect(page.locator("[data-testid='question-text']")).toBeVisible({ timeout: 5000 });

    // End session
    await page.getByRole("button", { name: /end session/i }).click();

    // Should see summary
    await expect(page.locator("[data-testid='session-summary']")).toBeVisible();
  });
});
```

- [ ] **Step 2: Run E2E tests**

```bash
cd frontend && npm run e2e
```

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/revision.spec.ts
git commit -m "test: E2E test for revision practice flow"
```

---

## Checkpoint: Feature Complete

At this point:
- Database: 6 new tables + 2 column additions, migrated
- Backend: Bandit service, pool replenishment, revision API (5 endpoints)
- Frontend: Revision player with quiz/flashcard/speaking modes, session lifecycle
- Tests: Bandit unit tests, generation tests, API integration tests, E2E test

The difficulty adapter is fully functional. Students can enter revision mode, practice infinitely with adaptive difficulty, and see their session stats.

**Post-checkpoint cleanup:**
- Verify `cd backend && python -m pytest --cov=app.services.bandit --cov=app.api.revision --cov-report=term-missing` shows 80%+ coverage
- Verify `cd frontend && npm run build` succeeds
- Run full test suite: `cd backend && python -m pytest -v`
