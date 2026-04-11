"""Tests for the contextual bandit difficulty adapter."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from app.services.bandit import (
    COLD_START_THRESHOLD,
    ENTROPY_COEFF,
    GRAD_CLIP_NORM,
    HIDDEN_DIM,
    LEARNING_RATE,
    NUM_ACTIONS,
    REWARD_DECAY,
    STATE_DIM,
    DifficultyPolicy,
    cold_start_select,
    compute_state_vector,
    create_initial_weights,
    deserialize_weights,
    is_degenerate,
    select_difficulty,
    serialize_weights,
    update_policy,
)

DIFFICULTIES = ["easy", "medium", "hard"]


def _make_attempt(
    difficulty: str = "medium",
    score: float = 0.7,
    created_at: datetime | None = None,
) -> SimpleNamespace:
    """Helper to build a fake attempt object with the fields bandit expects."""
    if created_at is None:
        created_at = datetime.now(timezone.utc)
    return SimpleNamespace(difficulty=difficulty, score=score, created_at=created_at)


# ---------------------------------------------------------------------------
# TestDifficultyPolicy
# ---------------------------------------------------------------------------


class TestDifficultyPolicy:
    def test_output_shape(self):
        policy = DifficultyPolicy()
        x = torch.randn(1, STATE_DIM)
        out = policy(x)
        assert out.shape == (1, NUM_ACTIONS)

    def test_sums_to_one(self):
        policy = DifficultyPolicy()
        x = torch.randn(1, STATE_DIM)
        out = policy(x)
        assert pytest.approx(out.sum().item(), abs=1e-5) == 1.0

    def test_initial_near_uniform(self):
        policy = DifficultyPolicy()
        x = torch.zeros(1, STATE_DIM)
        probs = policy(x).detach().numpy().flatten()
        # Each probability should be close to 1/3
        for p in probs:
            assert abs(p - 1.0 / NUM_ACTIONS) < 0.15

    def test_serialize_deserialize_roundtrip(self):
        policy = DifficultyPolicy()
        blob = serialize_weights(policy)
        assert isinstance(blob, bytes)
        assert len(blob) > 0

        restored = deserialize_weights(blob)
        assert isinstance(restored, DifficultyPolicy)

        x = torch.randn(1, STATE_DIM)
        orig_out = policy(x).detach().numpy()
        rest_out = restored(x).detach().numpy()
        np.testing.assert_allclose(orig_out, rest_out, atol=1e-6)


# ---------------------------------------------------------------------------
# TestColdStartSelect
# ---------------------------------------------------------------------------


class TestColdStartSelect:
    def test_no_history_returns_medium(self):
        assert cold_start_select([]) == "medium"

    def test_two_consecutive_high_scores_moves_up(self):
        history = [
            _make_attempt("easy", 0.85),
            _make_attempt("easy", 0.90),
        ]
        result = cold_start_select(history)
        assert result == "medium"  # one step up from easy

    def test_single_high_score_stays(self):
        history = [_make_attempt("medium", 0.85)]
        result = cold_start_select(history)
        assert result == "medium"

    def test_low_score_moves_down(self):
        history = [_make_attempt("medium", 0.3)]
        result = cold_start_select(history)
        assert result == "easy"

    def test_clamps_at_hard(self):
        history = [
            _make_attempt("hard", 0.90),
            _make_attempt("hard", 0.95),
        ]
        result = cold_start_select(history)
        assert result == "hard"  # already at ceiling

    def test_clamps_at_easy(self):
        history = [_make_attempt("easy", 0.2)]
        result = cold_start_select(history)
        assert result == "easy"  # already at floor


# ---------------------------------------------------------------------------
# TestComputeStateVector
# ---------------------------------------------------------------------------


class TestComputeStateVector:
    def test_empty_attempts_returns_defaults(self):
        vec = compute_state_vector([], current_session_count=0)
        assert vec.shape == (STATE_DIM,)
        # avg score per difficulty defaults to 0.5
        np.testing.assert_allclose(vec[0:3], 0.5, atol=1e-6)

    def test_with_easy_attempts(self):
        attempts = [_make_attempt("easy", 0.9) for _ in range(5)]
        vec = compute_state_vector(attempts, current_session_count=0)
        # easy slot should reflect actual average
        assert vec[0] > 0.8
        # medium/hard still default
        np.testing.assert_allclose(vec[1:3], 0.5, atol=1e-6)

    def test_attempt_count_normalized(self):
        attempts = [_make_attempt("medium", 0.7) for _ in range(50)]
        vec = compute_state_vector(attempts, current_session_count=0)
        assert pytest.approx(vec[6], abs=0.01) == 0.5  # 50/100

    def test_attempt_count_capped(self):
        attempts = [_make_attempt("medium", 0.7) for _ in range(200)]
        vec = compute_state_vector(attempts, current_session_count=0)
        assert pytest.approx(vec[6], abs=1e-6) == 1.0  # capped

    def test_session_progress_capped(self):
        vec = compute_state_vector([], current_session_count=50)
        assert pytest.approx(vec[9], abs=1e-6) == 1.0  # 50/20 capped at 1


# ---------------------------------------------------------------------------
# TestSelectDifficulty
# ---------------------------------------------------------------------------


class TestSelectDifficulty:
    def test_cold_start_uses_rules(self):
        state = np.zeros(STATE_DIM)
        weights = serialize_weights(DifficultyPolicy())
        # With 0 attempts (< COLD_START_THRESHOLD), should use cold start
        diff, log_prob = select_difficulty(
            state=state,
            weights=weights,
            attempt_count=0,
            recent_history=[],
            recent_difficulties=[],
        )
        assert diff in DIFFICULTIES
        assert log_prob == 0.0  # cold start doesn't compute log_prob

    def test_bandit_returns_valid_difficulty(self):
        state = np.random.rand(STATE_DIM).astype(np.float32)
        weights = serialize_weights(DifficultyPolicy())
        diff, log_prob = select_difficulty(
            state=state,
            weights=weights,
            attempt_count=COLD_START_THRESHOLD + 1,
            recent_history=[_make_attempt("medium", 0.7) for _ in range(5)],
            recent_difficulties=["easy", "medium", "hard", "medium", "easy"],
        )
        assert diff in DIFFICULTIES
        assert isinstance(log_prob, float)


# ---------------------------------------------------------------------------
# TestIsDegenerate
# ---------------------------------------------------------------------------


class TestIsDegenerate:
    def test_not_degenerate_with_variety(self):
        assert is_degenerate(["easy", "medium", "hard", "easy", "medium"]) is False

    def test_degenerate_all_same(self):
        assert is_degenerate(["medium"] * 5) is True

    def test_short_history_not_degenerate(self):
        assert is_degenerate(["medium", "medium"]) is False


# ---------------------------------------------------------------------------
# TestUpdatePolicy
# ---------------------------------------------------------------------------


class TestUpdatePolicy:
    def test_weights_change_after_update(self):
        policy = DifficultyPolicy()
        original_blob = serialize_weights(policy)
        state = np.random.rand(STATE_DIM).astype(np.float32)

        new_blob, new_mean, new_var = update_policy(
            weights=original_blob,
            state=state,
            chosen_idx=1,
            reward=0.8,
            reward_mean=0.5,
            reward_var=0.1,
            use_normalized_reward=True,
        )

        assert isinstance(new_blob, bytes)
        # Weights should have changed
        orig_policy = deserialize_weights(original_blob)
        new_policy = deserialize_weights(new_blob)

        orig_params = list(orig_policy.parameters())
        new_params = list(new_policy.parameters())

        any_changed = False
        for op, np_ in zip(orig_params, new_params):
            if not torch.allclose(op, np_):
                any_changed = True
                break
        assert any_changed

    def test_reward_stats_update(self):
        policy = DifficultyPolicy()
        blob = serialize_weights(policy)
        state = np.random.rand(STATE_DIM).astype(np.float32)

        _, new_mean, new_var = update_policy(
            weights=blob,
            state=state,
            chosen_idx=0,
            reward=1.0,
            reward_mean=0.5,
            reward_var=0.25,
            use_normalized_reward=True,
        )

        # EMA should move mean toward the new reward
        assert new_mean != 0.5
        assert isinstance(new_mean, float)
        assert isinstance(new_var, float)


class TestCorrectedDifficulty:
    def test_state_vector_uses_corrected_difficulty(self):
        """When corrected_difficulty is set, state vector should group by it."""
        now = datetime.now(timezone.utc)
        attempts = [
            SimpleNamespace(
                difficulty="medium",
                corrected_difficulty="easy",
                score=1.0,
                created_at=now,
            ),
        ] * 10

        vec = compute_state_vector(attempts, current_session_count=10)
        assert vec[0] == pytest.approx(1.0)  # avg_score_easy
        assert vec[1] == pytest.approx(0.5)  # avg_score_medium (default)

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
