# Difficulty Recalibration (15a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a hierarchical Bayesian classifier that recalibrates LLM-assigned difficulty labels on revision pool items using actual student performance data, with an instructor dashboard for visibility and manual override.

**Architecture:** Two-layer Bayesian model — course-level Dirichlet prior learns systematic LLM bias as a 3x3 transition matrix; item-level Beta posteriors refine individual labels. Stats accumulate online (in the `/answer` hot path), recalibration decisions run as batch jobs on the existing worker queue every ~50 attempts. Instructor-facing dashboard exposes the transition matrix and per-item details with override capability.

**Tech Stack:** Python 3, FastAPI, SQLAlchemy 2.0 async, Alembic, NumPy, PostgreSQL, Next.js 16, React 19, TanStack Query, shadcn/ui

**Spec:** [`docs/superpowers/specs/2026-04-11-difficulty-recalibration.md`](../specs/2026-04-11-difficulty-recalibration.md)

---

### Task 1: Database migration — new tables and columns

**Files:**
- Create: `backend/alembic/versions/xxxx_recalibration_tables.py` (hash auto-generated)
- Reference: `backend/app/models/revision.py` (existing schema)

- [ ] **Step 1: Generate empty migration**

```bash
cd backend
alembic revision --autogenerate -m "recalibration tables and columns"
```

- [ ] **Step 2: Edit migration with exact schema**

Replace the auto-generated `upgrade()` and `downgrade()` with:

```python
"""recalibration tables and columns"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON


def upgrade() -> None:
    # --- New table: recalibration_stats ---
    op.create_table(
        "recalibration_stats",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("pool_item_id", UUID(as_uuid=True), sa.ForeignKey("revision_pool_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_type", sa.String(20), nullable=False),
        sa.Column("llm_difficulty", sa.String(10), nullable=False),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("correct_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("hard_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("score_sum", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("score_sq_sum", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.UniqueConstraint("pool_item_id"),
    )
    op.create_index(
        "idx_recal_stats_course",
        "recalibration_stats",
        ["course_id", "content_type", "llm_difficulty"],
    )

    # --- New table: recalibration_models ---
    op.create_table(
        "recalibration_models",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("course_id", UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_type", sa.String(20), nullable=False),
        sa.Column("dirichlet_params", JSON, nullable=False),
        sa.Column("transition_matrix", JSON, nullable=False),
        sa.Column("items_used", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_attempts_since_last_run", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("course_id", "content_type"),
    )

    # --- New columns on revision_pool_items ---
    op.add_column("revision_pool_items", sa.Column("recalibrated_difficulty", sa.String(10), nullable=True))
    op.add_column("revision_pool_items", sa.Column("recalibration_confidence", sa.Numeric(4, 3), nullable=True))
    op.add_column("revision_pool_items", sa.Column("instructor_override", sa.Boolean, nullable=False, server_default="false"))

    # --- New column on revision_attempts ---
    op.add_column("revision_attempts", sa.Column("corrected_difficulty", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("revision_attempts", "corrected_difficulty")
    op.drop_column("revision_pool_items", "instructor_override")
    op.drop_column("revision_pool_items", "recalibration_confidence")
    op.drop_column("revision_pool_items", "recalibrated_difficulty")
    op.drop_index("idx_recal_stats_course", table_name="recalibration_stats")
    op.drop_table("recalibration_models")
    op.drop_table("recalibration_stats")
```

- [ ] **Step 3: Run migration**

```bash
cd backend
alembic upgrade head
```

Expected: migration applies cleanly, no errors.

- [ ] **Step 4: Verify tables exist**

```bash
cd backend
python -c "
import asyncio
from app.database import async_engine
from sqlalchemy import text

async def check():
    async with async_engine.connect() as conn:
        for table in ['recalibration_stats', 'recalibration_models']:
            result = await conn.execute(text(f\"SELECT COUNT(*) FROM {table}\"))
            print(f'{table}: {result.scalar()} rows')
        # Check new columns
        result = await conn.execute(text(\"SELECT column_name FROM information_schema.columns WHERE table_name='revision_pool_items' AND column_name IN ('recalibrated_difficulty','recalibration_confidence','instructor_override')\"))
        cols = [r[0] for r in result]
        print(f'revision_pool_items new columns: {cols}')
        result = await conn.execute(text(\"SELECT column_name FROM information_schema.columns WHERE table_name='revision_attempts' AND column_name='corrected_difficulty'\"))
        print(f'revision_attempts corrected_difficulty: {bool(result.fetchone())}')

asyncio.run(check())
"
```

Expected: all tables exist with 0 rows, all new columns present.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/*recalibration*
git commit -m "feat: add recalibration tables and columns migration"
```

---

### Task 2: SQLAlchemy models — RecalibrationStats and RecalibrationModel

**Files:**
- Create: `backend/app/models/recalibration.py`
- Modify: `backend/app/models/revision.py:40-68` (add new columns to RevisionPoolItem)
- Modify: `backend/app/models/revision.py:71-92` (add corrected_difficulty to RevisionAttempt)
- Modify: `backend/app/models/__init__.py:13-19,22-50` (add new imports/exports)

- [ ] **Step 1: Create `backend/app/models/recalibration.py`**

```python
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    ForeignKey,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class RecalibrationStats(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "recalibration_stats"
    __table_args__ = (UniqueConstraint("pool_item_id"),)

    pool_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("revision_pool_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    llm_difficulty: Mapped[str] = mapped_column(String(10), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    hard_count: Mapped[int] = mapped_column(Integer, default=0)
    score_sum: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    score_sq_sum: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))


class RecalibrationModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "recalibration_models"
    __table_args__ = (UniqueConstraint("course_id", "content_type"),)

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    dirichlet_params: Mapped[dict] = mapped_column(JSON, nullable=False)
    transition_matrix: Mapped[dict] = mapped_column(JSON, nullable=False)
    items_used: Mapped[int] = mapped_column(Integer, default=0)
    total_attempts_since_last_run: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 2: Add new columns to `RevisionPoolItem` in `backend/app/models/revision.py`**

After line 67 (`created_at` column), add:

```python
    # Recalibration columns
    recalibrated_difficulty: Mapped[str | None] = mapped_column(String(10))
    recalibration_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    instructor_override: Mapped[bool] = mapped_column(Boolean, default=False)
```

- [ ] **Step 3: Add `corrected_difficulty` to `RevisionAttempt` in `backend/app/models/revision.py`**

After line 91 (`created_at` column), add:

```python
    corrected_difficulty: Mapped[str | None] = mapped_column(String(10))
```

- [ ] **Step 4: Update `backend/app/models/__init__.py`**

Add to imports (after line 19):

```python
from app.models.recalibration import RecalibrationModel, RecalibrationStats
```

Add to `__all__` list (after `"BanditModel",` on line 49):

```python
    "RecalibrationStats",
    "RecalibrationModel",
```

- [ ] **Step 5: Verify models load**

```bash
cd backend
python -c "from app.models import RecalibrationStats, RecalibrationModel; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/recalibration.py backend/app/models/revision.py backend/app/models/__init__.py
git commit -m "feat: add RecalibrationStats and RecalibrationModel SQLAlchemy models"
```

---

### Task 3: Bayesian classifier core — `recalibrator.py`

**Files:**
- Create: `backend/app/services/recalibrator.py`
- Create: `backend/tests/test_recalibrator.py`

This is the pure-math core. No database calls — all functions take plain data and return results. Database integration comes in Task 5.

- [ ] **Step 1: Write failing tests for Dirichlet initialization and transition matrix**

Create `backend/tests/test_recalibrator.py`:

```python
"""Tests for the hierarchical Bayesian difficulty recalibrator."""

import numpy as np
import pytest

from app.services.recalibrator import (
    DIRICHLET_PRIOR_STRONG,
    DIRICHLET_PRIOR_WEAK,
    DOWNGRADE_THRESHOLD,
    EASY_SCORE_THRESHOLD,
    EQUIVALENT_SAMPLE_SIZE,
    HARD_SCORE_THRESHOLD,
    UPGRADE_THRESHOLD,
    build_initial_dirichlet,
    compute_transition_matrix,
    classify_observed_difficulty,
    update_dirichlet,
    compute_item_posterior,
    make_relabel_decision,
    DIFFICULTIES,
)


class TestDirichletInitialization:
    def test_initial_params_shape(self):
        params = build_initial_dirichlet()
        assert set(params.keys()) == {"easy", "medium", "hard"}
        for row in params.values():
            assert set(row.keys()) == {"easy", "medium", "hard"}

    def test_diagonal_is_strong_prior(self):
        params = build_initial_dirichlet()
        for diff in DIFFICULTIES:
            assert params[diff][diff] == DIRICHLET_PRIOR_STRONG

    def test_off_diagonal_is_weak_prior(self):
        params = build_initial_dirichlet()
        for row_diff in DIFFICULTIES:
            for col_diff in DIFFICULTIES:
                if row_diff != col_diff:
                    assert params[row_diff][col_diff] == DIRICHLET_PRIOR_WEAK

    def test_transition_matrix_rows_sum_to_one(self):
        params = build_initial_dirichlet()
        matrix = compute_transition_matrix(params)
        for row_diff in DIFFICULTIES:
            row_sum = sum(matrix[row_diff].values())
            assert abs(row_sum - 1.0) < 1e-9

    def test_initial_matrix_favors_diagonal(self):
        params = build_initial_dirichlet()
        matrix = compute_transition_matrix(params)
        for diff in DIFFICULTIES:
            assert matrix[diff][diff] > 0.8


class TestObservedDifficultyClassification:
    def test_high_score_is_easy(self):
        assert classify_observed_difficulty(0.90) == "easy"

    def test_low_score_is_hard(self):
        assert classify_observed_difficulty(0.30) == "hard"

    def test_mid_score_is_medium(self):
        assert classify_observed_difficulty(0.60) == "medium"

    def test_boundary_easy(self):
        assert classify_observed_difficulty(EASY_SCORE_THRESHOLD) == "easy"

    def test_boundary_hard(self):
        assert classify_observed_difficulty(HARD_SCORE_THRESHOLD - 0.01) == "hard"

    def test_boundary_medium_low(self):
        assert classify_observed_difficulty(HARD_SCORE_THRESHOLD) == "medium"

    def test_boundary_medium_high(self):
        assert classify_observed_difficulty(EASY_SCORE_THRESHOLD - 0.01) == "medium"


class TestDirichletUpdate:
    def test_update_shifts_probability(self):
        params = build_initial_dirichlet()
        # Simulate 10 "medium"-labeled items observed as "easy"
        for _ in range(10):
            params = update_dirichlet(params, llm_difficulty="medium", observed_difficulty="easy")
        matrix = compute_transition_matrix(params)
        # P(true=easy | LLM=medium) should increase significantly
        assert matrix["medium"]["easy"] > 0.4

    def test_update_preserves_other_rows(self):
        params = build_initial_dirichlet()
        original_easy_row = dict(params["easy"])
        params = update_dirichlet(params, llm_difficulty="medium", observed_difficulty="easy")
        # Easy row should be unchanged
        assert params["easy"] == original_easy_row

    def test_update_increments_by_one(self):
        params = build_initial_dirichlet()
        old_val = params["hard"]["medium"]
        params = update_dirichlet(params, llm_difficulty="hard", observed_difficulty="medium")
        assert params["hard"]["medium"] == old_val + 1


class TestItemPosterior:
    def test_no_data_returns_prior(self):
        matrix = compute_transition_matrix(build_initial_dirichlet())
        posterior = compute_item_posterior(
            llm_difficulty="medium",
            transition_matrix=matrix,
            correct_count=0,
            hard_count=0,
            attempt_count=0,
        )
        assert set(posterior.keys()) == {"easy", "medium", "hard"}
        # With no data, posterior should match the prior (transition matrix)
        assert posterior["medium"] > posterior["easy"]
        assert posterior["medium"] > posterior["hard"]

    def test_many_correct_shifts_to_easy(self):
        matrix = compute_transition_matrix(build_initial_dirichlet())
        posterior = compute_item_posterior(
            llm_difficulty="medium",
            transition_matrix=matrix,
            correct_count=18,
            hard_count=0,
            attempt_count=20,
        )
        assert posterior["easy"] > posterior["medium"]
        assert posterior["easy"] > 0.85

    def test_many_wrong_shifts_to_hard(self):
        matrix = compute_transition_matrix(build_initial_dirichlet())
        posterior = compute_item_posterior(
            llm_difficulty="easy",
            transition_matrix=matrix,
            correct_count=1,
            hard_count=15,
            attempt_count=20,
        )
        assert posterior["hard"] > posterior["easy"]

    def test_biased_prior_accelerates_relabeling(self):
        """Items converge faster when course prior already suspects mislabeling."""
        # Simulate a course where medium items are often actually easy
        params = build_initial_dirichlet()
        for _ in range(20):
            params = update_dirichlet(params, "medium", "easy")
        biased_matrix = compute_transition_matrix(params)

        neutral_matrix = compute_transition_matrix(build_initial_dirichlet())

        # Same item data: 8/10 correct
        biased_posterior = compute_item_posterior("medium", biased_matrix, 8, 0, 10)
        neutral_posterior = compute_item_posterior("medium", neutral_matrix, 8, 0, 10)

        # Biased prior should make easy posterior higher
        assert biased_posterior["easy"] > neutral_posterior["easy"]


class TestRelabelDecision:
    def test_no_relabel_when_matches_llm(self):
        posterior = {"easy": 0.1, "medium": 0.8, "hard": 0.1}
        result = make_relabel_decision("medium", posterior)
        assert result is None

    def test_downgrade_at_lower_threshold(self):
        posterior = {"easy": 0.91, "medium": 0.05, "hard": 0.04}
        result = make_relabel_decision("medium", posterior)
        assert result == ("easy", 0.91)

    def test_upgrade_needs_higher_threshold(self):
        # 0.92 exceeds downgrade threshold (0.90) but not upgrade threshold (0.95)
        posterior = {"easy": 0.04, "medium": 0.04, "hard": 0.92}
        result = make_relabel_decision("medium", posterior)
        assert result is None  # 0.92 < 0.95 upgrade threshold

    def test_upgrade_at_high_confidence(self):
        posterior = {"easy": 0.02, "medium": 0.02, "hard": 0.96}
        result = make_relabel_decision("medium", posterior)
        assert result == ("hard", 0.96)

    def test_downgrade_two_levels(self):
        posterior = {"easy": 0.92, "medium": 0.05, "hard": 0.03}
        result = make_relabel_decision("hard", posterior)
        assert result == ("easy", 0.92)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
pytest tests/test_recalibrator.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'app.services.recalibrator'`

- [ ] **Step 3: Implement `backend/app/services/recalibrator.py`**

```python
"""Hierarchical Bayesian difficulty recalibrator.

Layer 1: Course-level Dirichlet-Multinomial learns systematic LLM bias.
Layer 2: Item-level Beta-Binomial refines individual labels.
"""

from __future__ import annotations

import copy
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DIFFICULTIES: list[str] = ["easy", "medium", "hard"]
DIFFICULTY_ORDER: dict[str, int] = {"easy": 0, "medium": 1, "hard": 2}

DIRICHLET_PRIOR_STRONG: float = 10.0
DIRICHLET_PRIOR_WEAK: float = 1.0
EQUIVALENT_SAMPLE_SIZE: float = 5.0
MIN_ATTEMPTS_FOR_LAYER1: int = 5
DOWNGRADE_THRESHOLD: float = 0.90
UPGRADE_THRESHOLD: float = 0.95
EASY_SCORE_THRESHOLD: float = 0.85
HARD_SCORE_THRESHOLD: float = 0.45
BATCH_TRIGGER_ATTEMPTS: int = 50


# ---------------------------------------------------------------------------
# Layer 1: Course-level Dirichlet
# ---------------------------------------------------------------------------


def build_initial_dirichlet() -> dict[str, dict[str, float]]:
    """Build initial Dirichlet params: strong on diagonal, weak off-diagonal."""
    return {
        row: {
            col: DIRICHLET_PRIOR_STRONG if row == col else DIRICHLET_PRIOR_WEAK
            for col in DIFFICULTIES
        }
        for row in DIFFICULTIES
    }


def compute_transition_matrix(
    dirichlet_params: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    """Normalize each row of Dirichlet params to get transition probabilities."""
    matrix: dict[str, dict[str, float]] = {}
    for row_diff in DIFFICULTIES:
        row = dirichlet_params[row_diff]
        total = sum(row.values())
        matrix[row_diff] = {col: row[col] / total for col in DIFFICULTIES}
    return matrix


def classify_observed_difficulty(mean_score: float) -> str:
    """Classify an item's observed difficulty from its mean score."""
    if mean_score >= EASY_SCORE_THRESHOLD:
        return "easy"
    if mean_score < HARD_SCORE_THRESHOLD:
        return "hard"
    return "medium"


def update_dirichlet(
    params: dict[str, dict[str, float]],
    llm_difficulty: str,
    observed_difficulty: str,
) -> dict[str, dict[str, float]]:
    """Increment one Dirichlet concentration parameter. Returns new dict."""
    updated = copy.deepcopy(params)
    updated[llm_difficulty][observed_difficulty] += 1
    return updated


# ---------------------------------------------------------------------------
# Layer 2: Item-level Beta posteriors
# ---------------------------------------------------------------------------


def compute_item_posterior(
    llm_difficulty: str,
    transition_matrix: dict[str, dict[str, float]],
    correct_count: int,
    hard_count: int,
    attempt_count: int,
) -> dict[str, float]:
    """Compute posterior difficulty probabilities for a single item.

    Prior comes from the course-level transition matrix row for this item's
    LLM-assigned difficulty, scaled by EQUIVALENT_SAMPLE_SIZE.

    Evidence comes from the item's own attempt data:
      correct_count (score >= 0.8) → easy signal
      hard_count (score < 0.4) → hard signal
      medium_count (remainder) → medium signal
    """
    k = EQUIVALENT_SAMPLE_SIZE
    prior_row = transition_matrix[llm_difficulty]

    medium_count = attempt_count - correct_count - hard_count

    # Build Beta parameters for each hypothesis
    # α = prior strength for this hypothesis + evidence for this hypothesis
    # β = prior strength against + evidence against
    alpha_easy = prior_row["easy"] * k + correct_count
    beta_easy = (1 - prior_row["easy"]) * k + hard_count

    alpha_medium = prior_row["medium"] * k + medium_count
    beta_medium = (1 - prior_row["medium"]) * k + (correct_count + hard_count)

    alpha_hard = prior_row["hard"] * k + hard_count
    beta_hard = (1 - prior_row["hard"]) * k + correct_count

    # Posterior means
    posterior = {
        "easy": alpha_easy / (alpha_easy + beta_easy) if (alpha_easy + beta_easy) > 0 else 0.0,
        "medium": alpha_medium / (alpha_medium + beta_medium) if (alpha_medium + beta_medium) > 0 else 0.0,
        "hard": alpha_hard / (alpha_hard + beta_hard) if (alpha_hard + beta_hard) > 0 else 0.0,
    }
    return posterior


# ---------------------------------------------------------------------------
# Relabeling decision
# ---------------------------------------------------------------------------


def make_relabel_decision(
    llm_difficulty: str,
    posterior: dict[str, float],
) -> tuple[str, float] | None:
    """Decide whether to relabel an item.

    Returns (new_difficulty, confidence) if relabeling, None if keeping label.
    Uses asymmetric thresholds: 0.90 for downgrade, 0.95 for upgrade.
    """
    best = max(posterior, key=lambda d: posterior[d])

    if best == llm_difficulty:
        return None

    is_downgrade = DIFFICULTY_ORDER[best] < DIFFICULTY_ORDER[llm_difficulty]
    threshold = DOWNGRADE_THRESHOLD if is_downgrade else UPGRADE_THRESHOLD

    if posterior[best] >= threshold:
        return (best, posterior[best])

    return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend
pytest tests/test_recalibrator.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/recalibrator.py backend/tests/test_recalibrator.py
git commit -m "feat: add Bayesian difficulty recalibrator core math"
```

---

### Task 4: Batch recalibration job — `run_recalibration`

**Files:**
- Modify: `backend/app/services/recalibrator.py` (add `run_recalibration` async function)
- Create: `backend/tests/test_recalibration_batch.py`

This task adds the database-facing batch job that orchestrates the full pipeline: load stats → classify → update Dirichlet → compute posteriors → relabel items → backfill attempts.

- [ ] **Step 1: Write failing test for the batch job**

Create `backend/tests/test_recalibration_batch.py`:

```python
"""Integration tests for the recalibration batch job."""

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.recalibrator import (
    build_initial_dirichlet,
    compute_transition_matrix,
    run_recalibration_pure,
    EASY_SCORE_THRESHOLD,
    MIN_ATTEMPTS_FOR_LAYER1,
)


def _make_stats(
    pool_item_id: str | None = None,
    llm_difficulty: str = "medium",
    attempt_count: int = 20,
    correct_count: int = 18,
    hard_count: int = 0,
    score_sum: float = 17.5,
    instructor_override: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        pool_item_id=pool_item_id or str(uuid.uuid4()),
        llm_difficulty=llm_difficulty,
        attempt_count=attempt_count,
        correct_count=correct_count,
        hard_count=hard_count,
        score_sum=score_sum,
        instructor_override=instructor_override,
    )


class TestRunRecalibrationPure:
    def test_relabels_easy_item(self):
        """A 'medium' item with 18/20 correct should be relabeled 'easy'."""
        stats = [_make_stats(llm_difficulty="medium", attempt_count=20, correct_count=18, hard_count=0, score_sum=17.5)]
        dirichlet = build_initial_dirichlet()

        new_dirichlet, relabels, reverts = run_recalibration_pure(stats, dirichlet)

        assert len(relabels) == 1
        item_id, new_diff, confidence = relabels[0]
        assert new_diff == "easy"
        assert confidence >= 0.90

    def test_skips_instructor_override(self):
        stats = [_make_stats(instructor_override=True)]
        dirichlet = build_initial_dirichlet()

        _, relabels, _ = run_recalibration_pure(stats, dirichlet)
        assert len(relabels) == 0

    def test_no_relabel_when_correct(self):
        """A 'medium' item with 50% correct stays medium."""
        stats = [_make_stats(attempt_count=20, correct_count=10, hard_count=5, score_sum=12.0)]
        dirichlet = build_initial_dirichlet()

        _, relabels, _ = run_recalibration_pure(stats, dirichlet)
        assert len(relabels) == 0

    def test_upgrade_hard_item(self):
        """An 'easy' item that most students get wrong should be upgraded."""
        stats = [_make_stats(
            llm_difficulty="easy",
            attempt_count=25,
            correct_count=1,
            hard_count=20,
            score_sum=5.0,
        )]
        dirichlet = build_initial_dirichlet()

        _, relabels, _ = run_recalibration_pure(stats, dirichlet)
        assert len(relabels) == 1
        assert relabels[0][1] == "hard"

    def test_dirichlet_updates_from_qualifying_items(self):
        """Course-level Dirichlet should shift when items have enough data."""
        stats = [
            _make_stats(llm_difficulty="medium", attempt_count=20, correct_count=18, hard_count=0, score_sum=17.5),
            _make_stats(llm_difficulty="medium", attempt_count=20, correct_count=17, hard_count=0, score_sum=17.0),
            _make_stats(llm_difficulty="medium", attempt_count=20, correct_count=19, hard_count=0, score_sum=18.5),
        ]
        dirichlet = build_initial_dirichlet()

        new_dirichlet, _, _ = run_recalibration_pure(stats, dirichlet)
        matrix = compute_transition_matrix(new_dirichlet)
        # After 3 medium→easy observations, P(easy|medium) should increase
        assert matrix["medium"]["easy"] > 0.2

    def test_items_below_min_attempts_still_get_posteriors(self):
        """Items with < MIN_ATTEMPTS_FOR_LAYER1 don't contribute to Dirichlet
        but still get item-level posteriors computed."""
        stats = [
            # Qualifying item shifts Dirichlet
            _make_stats(llm_difficulty="medium", attempt_count=20, correct_count=18, hard_count=0, score_sum=17.5),
            # Non-qualifying item (only 3 attempts) but all correct
            _make_stats(
                pool_item_id="low-data-item",
                llm_difficulty="medium",
                attempt_count=3,
                correct_count=3,
                hard_count=0,
                score_sum=3.0,
            ),
        ]
        dirichlet = build_initial_dirichlet()

        _, relabels, _ = run_recalibration_pure(stats, dirichlet)
        # The first item should relabel. The second might not have enough evidence.
        relabeled_ids = {r[0] for r in relabels}
        assert stats[0].pool_item_id in relabeled_ids
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
pytest tests/test_recalibration_batch.py -v 2>&1 | head -10
```

Expected: `ImportError: cannot import name 'run_recalibration_pure'`

- [ ] **Step 3: Implement `run_recalibration_pure` in `backend/app/services/recalibrator.py`**

Append to the end of `recalibrator.py`:

```python
# ---------------------------------------------------------------------------
# Batch recalibration (pure logic — no database calls)
# ---------------------------------------------------------------------------


def run_recalibration_pure(
    stats_list: list[Any],
    dirichlet_params: dict[str, dict[str, float]],
) -> tuple[
    dict[str, dict[str, float]],        # updated dirichlet
    list[tuple[str, str, float]],        # relabels: (pool_item_id, new_diff, confidence)
    list[str],                           # reverts: pool_item_ids to revert
]:
    """Run the full recalibration pipeline on in-memory data.

    Args:
        stats_list: list of objects with attributes:
            pool_item_id, llm_difficulty, attempt_count, correct_count,
            hard_count, score_sum, instructor_override
        dirichlet_params: current course-level Dirichlet parameters

    Returns:
        (updated_dirichlet, relabels, reverts)
    """
    # Reset Dirichlet to initial priors, then rebuild from qualifying items
    fresh_dirichlet = build_initial_dirichlet()

    # Step 1: Classify qualifying items and update Dirichlet
    for s in stats_list:
        if s.instructor_override:
            continue
        if s.attempt_count < MIN_ATTEMPTS_FOR_LAYER1:
            continue
        mean_score = float(s.score_sum) / s.attempt_count
        observed = classify_observed_difficulty(mean_score)
        fresh_dirichlet = update_dirichlet(fresh_dirichlet, s.llm_difficulty, observed)

    # Step 2: Compute transition matrix from updated Dirichlet
    matrix = compute_transition_matrix(fresh_dirichlet)

    # Step 3: Compute item-level posteriors and make relabel decisions
    relabels: list[tuple[str, str, float]] = []
    reverts: list[str] = []

    for s in stats_list:
        if s.instructor_override:
            continue

        posterior = compute_item_posterior(
            llm_difficulty=s.llm_difficulty,
            transition_matrix=matrix,
            correct_count=s.correct_count,
            hard_count=s.hard_count,
            attempt_count=s.attempt_count,
        )

        decision = make_relabel_decision(s.llm_difficulty, posterior)
        if decision is not None:
            new_diff, confidence = decision
            relabels.append((s.pool_item_id, new_diff, confidence))
        else:
            # If no relabel is warranted, this item should revert if previously relabeled
            reverts.append(s.pool_item_id)

    return fresh_dirichlet, relabels, reverts
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend
pytest tests/test_recalibration_batch.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/recalibrator.py backend/tests/test_recalibration_batch.py
git commit -m "feat: add batch recalibration pipeline (pure logic)"
```

---

### Task 5: Database-facing batch job and online accumulation

**Files:**
- Modify: `backend/app/services/recalibrator.py` (add `run_recalibration_job`, `accumulate_stats`, `maybe_trigger_recalibration`)
- Modify: `backend/app/api/revision.py:369-437` (add accumulation calls in `submit_answer`)
- Modify: `backend/app/services/worker.py:59-70` (add `recalibration` task type)

- [ ] **Step 1: Add database-facing functions to `backend/app/services/recalibrator.py`**

Append to the end of the file:

```python
# ---------------------------------------------------------------------------
# Database-facing functions
# ---------------------------------------------------------------------------

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recalibration import RecalibrationModel, RecalibrationStats
from app.models.revision import RevisionAttempt, RevisionPoolItem


async def accumulate_stats(
    db: AsyncSession,
    pool_item_id: UUID,
    course_id: UUID,
    content_type: str,
    llm_difficulty: str,
    score: float,
) -> None:
    """Upsert per-item stats. Called from the /answer hot path (~1ms)."""
    stmt = (
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
                "score_sq_sum": RecalibrationStats.score_sq_sum + (score * score),
            },
        )
    )
    await db.execute(stmt)


async def maybe_trigger_recalibration(
    db: AsyncSession,
    course_id: UUID,
    content_type: str,
) -> None:
    """Check if enough attempts have accumulated to trigger a batch job."""
    from app.models.task import Task

    result = await db.execute(
        select(RecalibrationModel).where(
            RecalibrationModel.course_id == course_id,
            RecalibrationModel.content_type == content_type,
        )
    )
    model = result.scalar_one_or_none()

    if model is None:
        # Count total stats rows for this course/content_type
        count_result = await db.execute(
            select(RecalibrationStats.attempt_count).where(
                RecalibrationStats.course_id == course_id,
                RecalibrationStats.content_type == content_type,
            )
        )
        total = sum(r[0] for r in count_result)
    else:
        total = model.total_attempts_since_last_run + 1
        model.total_attempts_since_last_run = total

    if total >= BATCH_TRIGGER_ATTEMPTS:
        # Enqueue recalibration task
        task = Task(
            task_type="recalibration",
            payload={
                "course_id": str(course_id),
                "content_type": content_type,
            },
        )
        db.add(task)


async def run_recalibration_job(
    db: AsyncSession,
    course_id: UUID,
    content_type: str,
) -> dict[str, int]:
    """Execute the full batch recalibration for a (course, content_type).

    Returns summary dict with counts of items scanned, relabeled, reverted.
    """
    import logging

    logger = logging.getLogger(__name__)

    # 1. Load all stats for this course/content_type, joined with override flag
    result = await db.execute(
        select(
            RecalibrationStats.pool_item_id,
            RecalibrationStats.llm_difficulty,
            RecalibrationStats.attempt_count,
            RecalibrationStats.correct_count,
            RecalibrationStats.hard_count,
            RecalibrationStats.score_sum,
            RevisionPoolItem.instructor_override,
        )
        .join(
            RevisionPoolItem,
            RecalibrationStats.pool_item_id == RevisionPoolItem.id,
        )
        .where(
            RecalibrationStats.course_id == course_id,
            RecalibrationStats.content_type == content_type,
        )
    )
    rows = result.all()

    if not rows:
        return {"scanned": 0, "relabeled": 0, "reverted": 0}

    # Convert to SimpleNamespace for the pure function
    from types import SimpleNamespace

    stats_list = [
        SimpleNamespace(
            pool_item_id=str(r.pool_item_id),
            llm_difficulty=r.llm_difficulty,
            attempt_count=r.attempt_count,
            correct_count=r.correct_count,
            hard_count=r.hard_count,
            score_sum=float(r.score_sum),
            instructor_override=r.instructor_override,
        )
        for r in rows
    ]

    # 2. Load or build existing Dirichlet params
    model_result = await db.execute(
        select(RecalibrationModel).where(
            RecalibrationModel.course_id == course_id,
            RecalibrationModel.content_type == content_type,
        )
    )
    existing_model = model_result.scalar_one_or_none()
    old_dirichlet = (
        existing_model.dirichlet_params
        if existing_model
        else build_initial_dirichlet()
    )

    # 3. Run pure recalibration logic
    new_dirichlet, relabels, reverts = run_recalibration_pure(stats_list, old_dirichlet)
    new_matrix = compute_transition_matrix(new_dirichlet)

    # 4. Persist updated Dirichlet model
    if existing_model:
        existing_model.dirichlet_params = new_dirichlet
        existing_model.transition_matrix = new_matrix
        existing_model.items_used = len([s for s in stats_list if s.attempt_count >= MIN_ATTEMPTS_FOR_LAYER1])
        existing_model.total_attempts_since_last_run = 0
    else:
        new_model = RecalibrationModel(
            course_id=course_id,
            content_type=content_type,
            dirichlet_params=new_dirichlet,
            transition_matrix=new_matrix,
            items_used=len([s for s in stats_list if s.attempt_count >= MIN_ATTEMPTS_FOR_LAYER1]),
            total_attempts_since_last_run=0,
        )
        db.add(new_model)

    # 5. Apply relabels to pool items
    for pool_item_id_str, new_diff, confidence in relabels:
        pool_item_id = UUID(pool_item_id_str)
        await db.execute(
            update(RevisionPoolItem)
            .where(RevisionPoolItem.id == pool_item_id)
            .values(
                recalibrated_difficulty=new_diff,
                recalibration_confidence=round(confidence, 3),
            )
        )
        # Backfill corrected_difficulty on attempts
        await db.execute(
            update(RevisionAttempt)
            .where(
                RevisionAttempt.pool_item_id == pool_item_id,
                RevisionAttempt.corrected_difficulty.is_(None),
            )
            .values(corrected_difficulty=new_diff)
        )

    # 6. Revert items that no longer meet threshold
    for pool_item_id_str in reverts:
        pool_item_id = UUID(pool_item_id_str)
        await db.execute(
            update(RevisionPoolItem)
            .where(
                RevisionPoolItem.id == pool_item_id,
                RevisionPoolItem.recalibrated_difficulty.is_not(None),
            )
            .values(
                recalibrated_difficulty=None,
                recalibration_confidence=None,
            )
        )

    await db.flush()

    summary = {
        "scanned": len(stats_list),
        "relabeled": len(relabels),
        "reverted": len([r for r in reverts]),
    }
    logger.info(
        "Recalibration complete for course=%s content_type=%s: %s",
        course_id, content_type, summary,
    )
    return summary
```

- [ ] **Step 2: Add `recalibration` task type to `backend/app/services/worker.py`**

After line 68 (`await replenish_pool(session, task.payload)`), before the `else:` on line 69, add:

```python
    elif task.task_type == "recalibration":
        from app.services.recalibrator import run_recalibration_job
        from uuid import UUID
        course_id = task.payload.get("course_id")
        content_type = task.payload.get("content_type")
        if not course_id or not content_type:
            raise ValueError("Missing course_id or content_type in recalibration payload")
        await run_recalibration_job(session, UUID(course_id), content_type)
```

- [ ] **Step 3: Add accumulation calls in `submit_answer` in `backend/app/api/revision.py`**

At the top of the file, add to imports (after `update_policy` import on line 40):

```python
from app.services.recalibrator import accumulate_stats, maybe_trigger_recalibration
```

In `submit_answer()`, after line 379 (`db.add(attempt)`), before the session counter update on line 382, add:

```python
    # Recalibration stat accumulation
    await accumulate_stats(
        db,
        pool_item_id=pool_item.id,
        course_id=session.course_id,
        content_type=pool_item.content_type,
        llm_difficulty=pool_item.difficulty,
        score=score,
    )
    await maybe_trigger_recalibration(db, session.course_id, pool_item.content_type)
```

- [ ] **Step 4: Run existing tests to verify no regressions**

```bash
cd backend
pytest tests/test_bandit.py tests/test_api_revision.py tests/test_recalibrator.py tests/test_recalibration_batch.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/recalibrator.py backend/app/services/worker.py backend/app/api/revision.py backend/tests/test_recalibration_batch.py
git commit -m "feat: add recalibration batch job, online accumulation, and worker integration"
```

---

### Task 6: Bandit and pool query integration — use corrected difficulty

**Files:**
- Modify: `backend/app/services/bandit.py:120-142` (state vector uses corrected_difficulty)
- Modify: `backend/app/api/revision.py:119-144` (`_pick_item` uses COALESCE)
- Modify: `backend/app/api/revision.py:147-165` (`_pick_item_any_difficulty` same)

- [ ] **Step 1: Update `_pick_item` in `backend/app/api/revision.py`**

At line 137, change:

```python
        RevisionPoolItem.difficulty == difficulty,
```

to:

```python
        func.coalesce(RevisionPoolItem.recalibrated_difficulty, RevisionPoolItem.difficulty) == difficulty,
```

- [ ] **Step 2: Update `compute_state_vector` in `backend/app/services/bandit.py`**

The state vector function takes in-memory attempt objects. The attribute used for grouping is `a.difficulty` (lines 123 and 132). We need to use corrected difficulty when available.

Add a helper at the top of the function (after line 112, `if not attempts:`):

```python
    def _eff_diff(a: Any) -> str:
        """Use corrected difficulty if available, else original."""
        return getattr(a, "corrected_difficulty", None) or a.difficulty
```

Then replace `a.difficulty` with `_eff_diff(a)` on lines 123 and 132:

Line 123: change `if a.difficulty == diff_name` to `if _eff_diff(a) == diff_name`
Line 132: change `if a.difficulty == diff_name` to `if _eff_diff(a) == diff_name`

- [ ] **Step 3: Write test for corrected difficulty in state vector**

Add to `backend/tests/test_bandit.py` (at the end of the file):

```python
class TestCorrectedDifficulty:
    def test_state_vector_uses_corrected_difficulty(self):
        """When corrected_difficulty is set, state vector should group by it."""
        now = datetime.now(timezone.utc)
        attempts = [
            # LLM said "medium", recalibrated to "easy"
            SimpleNamespace(
                difficulty="medium",
                corrected_difficulty="easy",
                score=1.0,
                created_at=now,
            ),
        ] * 10

        vec = compute_state_vector(attempts, current_session_count=10)
        # avg_score_easy (index 0) should be 1.0, avg_score_medium (index 1) should be 0.5 (default)
        assert vec[0] == pytest.approx(1.0)
        assert vec[1] == pytest.approx(0.5)  # default — no medium attempts

    def test_state_vector_falls_back_to_difficulty(self):
        """When corrected_difficulty is None, use original difficulty."""
        now = datetime.now(timezone.utc)
        attempts = [
            SimpleNamespace(
                difficulty="medium",
                corrected_difficulty=None,
                score=0.7,
                created_at=now,
            ),
        ] * 10

        vec = compute_state_vector(attempts, current_session_count=10)
        assert vec[1] == pytest.approx(0.7)  # avg_score_medium
```

- [ ] **Step 4: Run tests**

```bash
cd backend
pytest tests/test_bandit.py tests/test_recalibrator.py -v
```

Expected: all tests pass, including the new corrected difficulty tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/bandit.py backend/app/api/revision.py backend/tests/test_bandit.py
git commit -m "feat: bandit and pool queries use corrected difficulty via COALESCE"
```

---

### Task 7: Instructor API endpoints and schemas

**Files:**
- Create: `backend/app/schemas/recalibration.py`
- Create: `backend/app/api/recalibration.py`
- Modify: `backend/app/api/__init__.py:1-28` (register new router)

- [ ] **Step 1: Create `backend/app/schemas/recalibration.py`**

```python
from pydantic import BaseModel


class RecalibrationContentTypeSummary(BaseModel):
    content_type: str
    items_scanned: int
    items_relabeled: int
    relabel_pct: float
    last_run: str | None  # ISO timestamp or None if never run


class RecalibrationOverviewResponse(BaseModel):
    summaries: list[RecalibrationContentTypeSummary]
    transition_matrices: dict[str, dict[str, dict[str, float]]]
    # e.g. {"quiz": {"easy": {"easy": 0.85, "medium": 0.12, "hard": 0.03}, ...}}


class RecalibrationItemRow(BaseModel):
    pool_item_id: str
    content_type: str
    item_preview: str
    llm_difficulty: str
    recalibrated_difficulty: str | None
    confidence: float | None
    attempt_count: int
    correct_rate: float
    instructor_override: bool


class RecalibrationItemsResponse(BaseModel):
    items: list[RecalibrationItemRow]
```

- [ ] **Step 2: Create `backend/app/api/recalibration.py`**

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_instructor
from app.models.recalibration import RecalibrationModel, RecalibrationStats
from app.models.revision import RevisionPoolItem
from app.models.user import User
from app.schemas.common import APIResponse, PaginatedResponse, PaginationMeta
from app.schemas.recalibration import (
    RecalibrationContentTypeSummary,
    RecalibrationItemRow,
    RecalibrationItemsResponse,
    RecalibrationOverviewResponse,
)

router = APIRouter(tags=["recalibration"])

CONTENT_TYPES = ["quiz", "flashcard", "speaking"]


@router.get(
    "/courses/{course_id}/recalibration/overview",
    response_model=APIResponse[RecalibrationOverviewResponse],
)
async def get_overview(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    summaries: list[RecalibrationContentTypeSummary] = []
    matrices: dict[str, dict[str, dict[str, float]]] = {}

    for ct in CONTENT_TYPES:
        # Count items scanned
        count_result = await db.execute(
            select(func.count()).where(
                RecalibrationStats.course_id == course_id,
                RecalibrationStats.content_type == ct,
            )
        )
        scanned = count_result.scalar() or 0

        # Count items relabeled
        relabel_result = await db.execute(
            select(func.count()).where(
                RevisionPoolItem.course_id == course_id,
                RevisionPoolItem.content_type == ct,
                RevisionPoolItem.recalibrated_difficulty.is_not(None),
            )
        )
        relabeled = relabel_result.scalar() or 0

        # Load model for this content type
        model_result = await db.execute(
            select(RecalibrationModel).where(
                RecalibrationModel.course_id == course_id,
                RecalibrationModel.content_type == ct,
            )
        )
        model = model_result.scalar_one_or_none()

        last_run = model.updated_at.isoformat() if model else None
        if model:
            matrices[ct] = model.transition_matrix

        summaries.append(
            RecalibrationContentTypeSummary(
                content_type=ct,
                items_scanned=scanned,
                items_relabeled=relabeled,
                relabel_pct=round(relabeled / scanned * 100, 1) if scanned > 0 else 0.0,
                last_run=last_run,
            )
        )

    return APIResponse(
        success=True,
        data=RecalibrationOverviewResponse(
            summaries=summaries,
            transition_matrices=matrices,
        ),
    )


@router.get(
    "/courses/{course_id}/recalibration/items",
    response_model=APIResponse[RecalibrationItemsResponse],
)
async def get_items(
    course_id: uuid.UUID,
    content_type: str | None = Query(None),
    llm_difficulty: str | None = Query(None),
    recalibrated_only: bool = Query(False),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    stmt = (
        select(
            RecalibrationStats.pool_item_id,
            RecalibrationStats.content_type,
            RecalibrationStats.llm_difficulty,
            RecalibrationStats.attempt_count,
            RecalibrationStats.correct_count,
            RevisionPoolItem.recalibrated_difficulty,
            RevisionPoolItem.recalibration_confidence,
            RevisionPoolItem.instructor_override,
            RevisionPoolItem.question_text,
            RevisionPoolItem.front,
            RevisionPoolItem.target_text,
        )
        .join(RevisionPoolItem, RecalibrationStats.pool_item_id == RevisionPoolItem.id)
        .where(RecalibrationStats.course_id == course_id)
        .order_by(RecalibrationStats.attempt_count.desc())
    )

    if content_type:
        stmt = stmt.where(RecalibrationStats.content_type == content_type)
    if llm_difficulty:
        stmt = stmt.where(RecalibrationStats.llm_difficulty == llm_difficulty)
    if recalibrated_only:
        stmt = stmt.where(RevisionPoolItem.recalibrated_difficulty.is_not(None))

    stmt = stmt.offset((page - 1) * limit).limit(limit)
    result = await db.execute(stmt)
    rows = result.all()

    items = []
    for r in rows:
        preview = r.question_text or r.front or r.target_text or "(no preview)"
        if len(preview) > 80:
            preview = preview[:77] + "..."

        correct_rate = r.correct_count / r.attempt_count if r.attempt_count > 0 else 0.0

        items.append(
            RecalibrationItemRow(
                pool_item_id=str(r.pool_item_id),
                content_type=r.content_type,
                item_preview=preview,
                llm_difficulty=r.llm_difficulty,
                recalibrated_difficulty=r.recalibrated_difficulty,
                confidence=float(r.recalibration_confidence) if r.recalibration_confidence else None,
                attempt_count=r.attempt_count,
                correct_rate=round(correct_rate, 3),
                instructor_override=r.instructor_override,
            )
        )

    return APIResponse(
        success=True,
        data=RecalibrationItemsResponse(items=items),
    )


@router.post(
    "/courses/{course_id}/recalibration/items/{item_id}/override",
    response_model=APIResponse[dict],
)
async def toggle_override(
    course_id: uuid.UUID,
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(RevisionPoolItem).where(
            RevisionPoolItem.id == item_id,
            RevisionPoolItem.course_id == course_id,
        )
    )
    pool_item = result.scalar_one_or_none()
    if not pool_item:
        raise HTTPException(status_code=404, detail="Pool item not found")

    # Toggle override
    new_override = not pool_item.instructor_override
    pool_item.instructor_override = new_override

    if new_override:
        # Reset recalibrated label
        pool_item.recalibrated_difficulty = None
        pool_item.recalibration_confidence = None

    await db.commit()

    return APIResponse(
        success=True,
        data={
            "pool_item_id": str(item_id),
            "instructor_override": new_override,
            "recalibrated_difficulty": pool_item.recalibrated_difficulty,
        },
    )
```

- [ ] **Step 3: Register router in `backend/app/api/__init__.py`**

After line 13 (`from app.api.revision import router as revision_router`), add:

```python
from app.api.recalibration import router as recalibration_router
```

After line 27 (`api_router.include_router(live_router)`), add:

```python
api_router.include_router(recalibration_router)
```

- [ ] **Step 4: Verify server starts**

```bash
cd backend
timeout 5 uvicorn app.main:app --port 8001 2>&1 | tail -5 || true
```

Expected: `Uvicorn running on http://0.0.0.0:8001` (no import errors).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/recalibration.py backend/app/api/recalibration.py backend/app/api/__init__.py
git commit -m "feat: add instructor recalibration API endpoints"
```

---

### Task 8: Frontend — recalibration hook and dashboard components

**Files:**
- Create: `frontend/src/hooks/use-recalibration.ts`
- Create: `frontend/src/components/recalibration/overview.tsx`
- Create: `frontend/src/components/recalibration/transition-matrix.tsx`
- Create: `frontend/src/components/recalibration/item-table.tsx`
- Modify: `frontend/src/app/dashboard/courses/[courseId]/page.tsx` (add Recalibration tab for instructors)

- [ ] **Step 1: Create `frontend/src/hooks/use-recalibration.ts`**

```typescript
"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@clerk/nextjs";
import { apiFetch } from "@/lib/api";

// --- Types ---

export interface RecalibrationContentTypeSummary {
  readonly content_type: string;
  readonly items_scanned: number;
  readonly items_relabeled: number;
  readonly relabel_pct: number;
  readonly last_run: string | null;
}

export interface RecalibrationOverview {
  readonly summaries: RecalibrationContentTypeSummary[];
  readonly transition_matrices: Record<
    string,
    Record<string, Record<string, number>>
  >;
}

export interface RecalibrationItemRow {
  readonly pool_item_id: string;
  readonly content_type: string;
  readonly item_preview: string;
  readonly llm_difficulty: string;
  readonly recalibrated_difficulty: string | null;
  readonly confidence: number | null;
  readonly attempt_count: number;
  readonly correct_rate: number;
  readonly instructor_override: boolean;
}

interface ApiEnvelope<T> {
  readonly success: boolean;
  readonly data: T;
}

// --- Hooks ---

export function useRecalibrationOverview(courseId: string) {
  const { getToken } = useAuth();

  return useQuery({
    queryKey: ["recalibration", "overview", courseId],
    queryFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<RecalibrationOverview>>(
        `/courses/${courseId}/recalibration/overview`,
        { token }
      );
      return res.data;
    },
  });
}

export function useRecalibrationItems(
  courseId: string,
  filters: {
    content_type?: string;
    llm_difficulty?: string;
    recalibrated_only?: boolean;
    page?: number;
    limit?: number;
  } = {}
) {
  const { getToken } = useAuth();
  const params = new URLSearchParams();
  if (filters.content_type) params.set("content_type", filters.content_type);
  if (filters.llm_difficulty)
    params.set("llm_difficulty", filters.llm_difficulty);
  if (filters.recalibrated_only) params.set("recalibrated_only", "true");
  if (filters.page) params.set("page", String(filters.page));
  if (filters.limit) params.set("limit", String(filters.limit));

  const qs = params.toString();

  return useQuery({
    queryKey: ["recalibration", "items", courseId, qs],
    queryFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<
        ApiEnvelope<{ items: RecalibrationItemRow[] }>
      >(`/courses/${courseId}/recalibration/items?${qs}`, { token });
      return res.data.items;
    },
  });
}

export function useToggleOverride(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (itemId: string) => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return apiFetch<ApiEnvelope<Record<string, unknown>>>(
        `/courses/${courseId}/recalibration/items/${itemId}/override`,
        { method: "POST", token }
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["recalibration", "items", courseId],
      });
      queryClient.invalidateQueries({
        queryKey: ["recalibration", "overview", courseId],
      });
    },
  });
}
```

- [ ] **Step 2: Create `frontend/src/components/recalibration/transition-matrix.tsx`**

```tsx
"use client";

interface TransitionMatrixProps {
  readonly matrix: Record<string, Record<string, number>>;
  readonly contentType: string;
}

const DIFFS = ["easy", "medium", "hard"] as const;

function cellColor(row: string, col: string, value: number): string {
  if (row === col) {
    return value >= 0.7
      ? "bg-[oklch(90%_0.05_145)]"
      : value >= 0.5
        ? "bg-[oklch(93%_0.05_75)]"
        : "bg-[oklch(90%_0.05_25)]";
  }
  return value >= 0.2
    ? "bg-[oklch(90%_0.05_25)]"
    : value >= 0.1
      ? "bg-[oklch(93%_0.05_75)]"
      : "";
}

export function TransitionMatrix({
  matrix,
  contentType,
}: TransitionMatrixProps) {
  return (
    <div>
      <h4 className="text-sm font-medium text-[var(--color-text-secondary)] mb-2 capitalize">
        {contentType} Difficulty Calibration
      </h4>
      <div className="text-xs text-[var(--color-text-tertiary)] mb-1">
        LLM Label → Observed Reality
      </div>
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr>
            <th className="p-2 text-left text-[var(--color-text-tertiary)]" />
            {DIFFS.map((d) => (
              <th
                key={d}
                className="p-2 text-center capitalize text-[var(--color-text-secondary)]"
              >
                {d}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {DIFFS.map((rowDiff) => (
            <tr key={rowDiff}>
              <td className="p-2 font-medium capitalize text-[var(--color-text-secondary)]">
                {rowDiff}
              </td>
              {DIFFS.map((colDiff) => {
                const val = matrix[rowDiff]?.[colDiff] ?? 0;
                return (
                  <td
                    key={colDiff}
                    className={`p-2 text-center rounded ${cellColor(rowDiff, colDiff, val)}`}
                  >
                    {(val * 100).toFixed(0)}%
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 3: Create `frontend/src/components/recalibration/item-table.tsx`**

```tsx
"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  useRecalibrationItems,
  useToggleOverride,
  type RecalibrationItemRow,
} from "@/hooks/use-recalibration";

interface ItemTableProps {
  readonly courseId: string;
}

function diffBadge(diff: string) {
  const colors: Record<string, string> = {
    easy: "bg-[oklch(90%_0.05_145)] text-[var(--color-success)]",
    medium: "bg-[oklch(93%_0.05_75)] text-[var(--color-warning)]",
    hard: "bg-[oklch(90%_0.05_25)] text-[var(--color-error)]",
  };
  return (
    <Badge className={`${colors[diff] ?? ""} border-transparent capitalize`}>
      {diff}
    </Badge>
  );
}

export function RecalibrationItemTable({ courseId }: ItemTableProps) {
  const [contentType, setContentType] = useState<string | undefined>();
  const [page, setPage] = useState(1);

  const { data: items, isLoading } = useRecalibrationItems(courseId, {
    content_type: contentType,
    page,
    limit: 20,
  });
  const toggleOverride = useToggleOverride(courseId);

  return (
    <div>
      <div className="flex gap-2 mb-4">
        {["all", "quiz", "flashcard", "speaking"].map((ct) => (
          <Button
            key={ct}
            variant={
              (ct === "all" && !contentType) || ct === contentType
                ? "default"
                : "outline"
            }
            size="sm"
            onClick={() => setContentType(ct === "all" ? undefined : ct)}
          >
            {ct === "all" ? "All" : ct.charAt(0).toUpperCase() + ct.slice(1)}
          </Button>
        ))}
      </div>

      {isLoading ? (
        <div className="text-sm text-[var(--color-text-tertiary)]">
          Loading items...
        </div>
      ) : !items?.length ? (
        <div className="text-sm text-[var(--color-text-tertiary)]">
          No recalibration data yet.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-[var(--color-border)]">
                <th className="p-2 text-left">Preview</th>
                <th className="p-2 text-center">LLM</th>
                <th className="p-2 text-center">Recalibrated</th>
                <th className="p-2 text-center">Confidence</th>
                <th className="p-2 text-center">Attempts</th>
                <th className="p-2 text-center">Correct %</th>
                <th className="p-2 text-center">Override</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item: RecalibrationItemRow) => (
                <tr
                  key={item.pool_item_id}
                  className="border-b border-[var(--color-border)]"
                >
                  <td className="p-2 max-w-[250px] truncate">
                    {item.item_preview}
                  </td>
                  <td className="p-2 text-center">
                    {diffBadge(item.llm_difficulty)}
                  </td>
                  <td className="p-2 text-center">
                    {item.recalibrated_difficulty
                      ? diffBadge(item.recalibrated_difficulty)
                      : "—"}
                  </td>
                  <td className="p-2 text-center">
                    {item.confidence
                      ? `${(item.confidence * 100).toFixed(1)}%`
                      : "—"}
                  </td>
                  <td className="p-2 text-center">{item.attempt_count}</td>
                  <td className="p-2 text-center">
                    {(item.correct_rate * 100).toFixed(1)}%
                  </td>
                  <td className="p-2 text-center">
                    {item.recalibrated_difficulty || item.instructor_override ? (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          toggleOverride.mutate(item.pool_item_id)
                        }
                        disabled={toggleOverride.isPending}
                      >
                        {item.instructor_override ? "Unlock" : "Reset"}
                      </Button>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex gap-2 mt-4 justify-center">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          disabled={page === 1}
        >
          Previous
        </Button>
        <span className="text-sm self-center">Page {page}</span>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setPage((p) => p + 1)}
          disabled={!items?.length || items.length < 20}
        >
          Next
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create `frontend/src/components/recalibration/overview.tsx`**

```tsx
"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useRecalibrationOverview } from "@/hooks/use-recalibration";
import { TransitionMatrix } from "./transition-matrix";
import { RecalibrationItemTable } from "./item-table";
import { formatRelativeTime } from "@/lib/format";

interface OverviewProps {
  readonly courseId: string;
}

export function RecalibrationOverview({ courseId }: OverviewProps) {
  const { data, isLoading, error } = useRecalibrationOverview(courseId);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="text-sm text-[var(--color-text-tertiary)]">
        Failed to load recalibration data.
      </div>
    );
  }

  const hasData = data.summaries.some((s) => s.items_scanned > 0);

  if (!hasData) {
    return (
      <Card>
        <CardContent className="pt-6">
          <p className="text-sm text-[var(--color-text-tertiary)]">
            No recalibration data yet. Data accumulates automatically as
            students answer revision questions.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {data.summaries
          .filter((s) => s.items_scanned > 0)
          .map((s) => (
            <Card key={s.content_type}>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm capitalize">
                  {s.content_type}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-semibold">
                  {s.items_relabeled}{" "}
                  <span className="text-sm font-normal text-[var(--color-text-tertiary)]">
                    / {s.items_scanned} items ({s.relabel_pct}%)
                  </span>
                </div>
                <div className="text-xs text-[var(--color-text-tertiary)] mt-1">
                  {s.last_run
                    ? `Last run ${formatRelativeTime(s.last_run)}`
                    : "Never run"}
                </div>
              </CardContent>
            </Card>
          ))}
      </div>

      {/* Transition matrices */}
      {Object.keys(data.transition_matrices).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Difficulty Calibration Matrices
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {Object.entries(data.transition_matrices).map(([ct, matrix]) => (
                <TransitionMatrix
                  key={ct}
                  matrix={matrix}
                  contentType={ct}
                />
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Item detail table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Item Details</CardTitle>
        </CardHeader>
        <CardContent>
          <RecalibrationItemTable courseId={courseId} />
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 5: Add Recalibration tab to course detail page**

In `frontend/src/app/dashboard/courses/[courseId]/page.tsx`, add the import at the top (after the existing component imports around line 31):

```typescript
import { RecalibrationOverview } from "@/components/recalibration/overview";
```

Then find the tabs section in the page (the instructor-only content area) and add a new tab for "Recalibration." The exact location depends on the existing tab structure — look for the existing tabs and add after them. The tab content should render:

```tsx
<RecalibrationOverview courseId={courseId} />
```

This tab should only be visible to instructors (use the existing `useRole()` hook to check).

- [ ] **Step 6: Verify frontend compiles**

```bash
cd frontend
npm run build 2>&1 | tail -20
```

Expected: build succeeds with no type errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/hooks/use-recalibration.ts frontend/src/components/recalibration/ frontend/src/app/dashboard/courses/\[courseId\]/page.tsx
git commit -m "feat: add instructor recalibration dashboard frontend"
```

---

### Task 9: Integration tests for recalibration API

**Files:**
- Create: `backend/tests/test_api_recalibration.py`

- [ ] **Step 1: Create `backend/tests/test_api_recalibration.py`**

```python
"""Integration test stubs for recalibration API endpoints.

These tests validate the API contract. They require the test database
with recalibration tables migrated (alembic upgrade head on langassistant_test).
"""

import pytest


class TestRecalibrationOverview:
    """GET /api/courses/{id}/recalibration/overview"""

    @pytest.mark.skip(reason="Requires test DB with seeded revision data")
    def test_returns_summaries_per_content_type(self):
        pass

    @pytest.mark.skip(reason="Requires test DB with seeded revision data")
    def test_returns_transition_matrices(self):
        pass

    @pytest.mark.skip(reason="Requires test DB with seeded revision data")
    def test_requires_instructor_role(self):
        pass


class TestRecalibrationItems:
    """GET /api/courses/{id}/recalibration/items"""

    @pytest.mark.skip(reason="Requires test DB with seeded revision data")
    def test_returns_paginated_items(self):
        pass

    @pytest.mark.skip(reason="Requires test DB with seeded revision data")
    def test_filters_by_content_type(self):
        pass

    @pytest.mark.skip(reason="Requires test DB with seeded revision data")
    def test_requires_instructor_role(self):
        pass


class TestToggleOverride:
    """POST /api/courses/{id}/recalibration/items/{itemId}/override"""

    @pytest.mark.skip(reason="Requires test DB with seeded revision data")
    def test_toggles_override_flag(self):
        pass

    @pytest.mark.skip(reason="Requires test DB with seeded revision data")
    def test_clears_recalibrated_label_on_override(self):
        pass

    @pytest.mark.skip(reason="Requires test DB with seeded revision data")
    def test_returns_404_for_missing_item(self):
        pass
```

- [ ] **Step 2: Run to verify stubs load**

```bash
cd backend
pytest tests/test_api_recalibration.py -v
```

Expected: all tests show as `SKIPPED`.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_api_recalibration.py
git commit -m "test: add integration test stubs for recalibration API"
```
