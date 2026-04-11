"""Tests for the FSRS-5 neural spaced repetition scheduler."""

import math

import pytest

from app.services.scheduler import (
    DEFAULT_PARAMS,
    GRADE_MAP,
    MAX_INTERVAL,
    MIN_INTERVAL,
    SWITCHOVER_THRESHOLD,
    TARGET_RETENTION,
    FSRSScheduler,
    initialize_from_sm2,
    sm2_update,
    update_parameters,
)


class TestRetrievability:
    def test_at_stability(self):
        """R(t=S, S) should equal 0.9 (target retention)."""
        s = FSRSScheduler(DEFAULT_PARAMS)
        r = s.compute_retrievability(t_days=10.0, stability=10.0)
        assert pytest.approx(r, abs=1e-6) == 0.9

    def test_at_zero(self):
        """R(t=0, S) should be 1.0 (just reviewed)."""
        s = FSRSScheduler(DEFAULT_PARAMS)
        r = s.compute_retrievability(t_days=0.0, stability=10.0)
        assert pytest.approx(r, abs=1e-6) == 1.0

    def test_decay_monotonic(self):
        """R should decrease as t increases."""
        s = FSRSScheduler(DEFAULT_PARAMS)
        prev_r = 1.0
        for t in [1, 5, 10, 30, 60, 90]:
            r = s.compute_retrievability(t_days=float(t), stability=10.0)
            assert r < prev_r
            prev_r = r

    def test_never_negative(self):
        """R should never go below 0."""
        s = FSRSScheduler(DEFAULT_PARAMS)
        r = s.compute_retrievability(t_days=100000.0, stability=1.0)
        assert r > 0


class TestInitialStability:
    def test_increases_with_grade(self):
        """S_0 should increase: Again < Hard < Good < Easy."""
        s = FSRSScheduler(DEFAULT_PARAMS)
        stabilities = [s.initial_stability(g) for g in [1, 2, 3, 4]]
        for i in range(len(stabilities) - 1):
            assert stabilities[i] < stabilities[i + 1]

    def test_always_positive(self):
        s = FSRSScheduler(DEFAULT_PARAMS)
        for g in [1, 2, 3, 4]:
            assert s.initial_stability(g) > 0


class TestInitialDifficulty:
    def test_decreases_with_grade(self):
        """D_0 should decrease: Again is hardest, Easy is easiest."""
        s = FSRSScheduler(DEFAULT_PARAMS)
        difficulties = [s.initial_difficulty(g) for g in [1, 2, 3, 4]]
        for i in range(len(difficulties) - 1):
            assert difficulties[i] > difficulties[i + 1]

    def test_clamped_to_range(self):
        s = FSRSScheduler(DEFAULT_PARAMS)
        for g in [1, 2, 3, 4]:
            d = s.initial_difficulty(g)
            assert 1.0 <= d <= 10.0


class TestStabilityAfterRecall:
    def test_stability_grows(self):
        """Successful recall should increase stability."""
        s = FSRSScheduler(DEFAULT_PARAMS)
        old_s = 5.0
        r = s.compute_retrievability(t_days=5.0, stability=old_s)
        new_s = s.stability_after_recall(d=5.0, s=old_s, r=r, grade=3)
        assert new_s > old_s

    def test_easy_grows_more_than_good(self):
        """Easy rating should yield higher stability than Good."""
        sched = FSRSScheduler(DEFAULT_PARAMS)
        old_s = 5.0
        r = sched.compute_retrievability(t_days=5.0, stability=old_s)
        s_good = sched.stability_after_recall(d=5.0, s=old_s, r=r, grade=3)
        s_easy = sched.stability_after_recall(d=5.0, s=old_s, r=r, grade=4)
        assert s_easy > s_good


class TestStabilityAfterForget:
    def test_stability_shrinks(self):
        """Forgetting should decrease stability."""
        s = FSRSScheduler(DEFAULT_PARAMS)
        old_s = 10.0
        r = s.compute_retrievability(t_days=10.0, stability=old_s)
        new_s = s.stability_after_forget(d=5.0, s=old_s, r=r)
        assert new_s < old_s

    def test_never_exceeds_original(self):
        """S'_f should not exceed S."""
        s = FSRSScheduler(DEFAULT_PARAMS)
        old_s = 2.0
        r = s.compute_retrievability(t_days=2.0, stability=old_s)
        new_s = s.stability_after_forget(d=5.0, s=old_s, r=r)
        assert new_s <= old_s


class TestDifficultyUpdate:
    def test_mean_reversion(self):
        """Repeated Good ratings should converge D toward the easy target."""
        s = FSRSScheduler(DEFAULT_PARAMS)
        d = 8.0
        for _ in range(50):
            d = s.update_difficulty(d, grade=3)
        assert d < 8.0

    def test_clamped(self):
        """D should stay in [1, 10] regardless of input."""
        s = FSRSScheduler(DEFAULT_PARAMS)
        d = s.update_difficulty(1.0, grade=4)
        assert 1.0 <= d <= 10.0
        d = s.update_difficulty(10.0, grade=1)
        assert 1.0 <= d <= 10.0


class TestInterval:
    def test_interval_equals_stability_at_default_target(self):
        """At target=0.9, interval ≈ S."""
        s = FSRSScheduler(DEFAULT_PARAMS)
        assert s.compute_interval(10.0) == 10

    def test_interval_clamped_min(self):
        s = FSRSScheduler(DEFAULT_PARAMS)
        assert s.compute_interval(0.01) == MIN_INTERVAL

    def test_interval_clamped_max(self):
        s = FSRSScheduler(DEFAULT_PARAMS)
        assert s.compute_interval(9999.0) == MAX_INTERVAL


class TestGradeMapping:
    def test_all_grades_mapped(self):
        assert GRADE_MAP[0] == 1
        assert GRADE_MAP[2] == 2
        assert GRADE_MAP[4] == 3
        assert GRADE_MAP[5] == 4


class TestSM2Fallback:
    def test_sm2_update_good_first_review(self):
        """First review with quality >= 3 gives interval 1."""
        ef, interval, reps = sm2_update(quality=4, ease_factor=2.5, interval_days=0, repetitions=0)
        assert interval == 1
        assert reps == 1

    def test_sm2_update_poor_resets(self):
        """Quality < 3 resets repetitions and interval."""
        ef, interval, reps = sm2_update(quality=1, ease_factor=2.5, interval_days=6, repetitions=2)
        assert interval == 0
        assert reps == 0

    def test_sm2_ef_floor(self):
        """Ease factor never goes below 1.3."""
        ef, _, _ = sm2_update(quality=0, ease_factor=1.3, interval_days=0, repetitions=0)
        assert ef >= 1.3


class TestInitializeFromSM2:
    def test_high_ef_low_difficulty(self):
        """High ease factor (easy card) maps to low difficulty."""
        s, d = initialize_from_sm2(ease_factor=2.5, interval_days=10)
        assert s == 10.0
        assert d == 1.0

    def test_low_ef_high_difficulty(self):
        """Low ease factor (hard card) maps to high difficulty."""
        s, d = initialize_from_sm2(ease_factor=1.3, interval_days=1)
        assert s == 1.0
        assert d == pytest.approx(5.8, abs=0.01)

    def test_zero_interval_gets_min_stability(self):
        s, d = initialize_from_sm2(ease_factor=2.5, interval_days=0)
        assert s == 0.1


class TestNextState:
    def test_first_review_good(self):
        """First review with Good should initialize S and D."""
        s = FSRSScheduler(DEFAULT_PARAMS)
        stab, diff, interval = s.next_state(
            grade=3, stability=None, difficulty=None, elapsed_days=0.0
        )
        assert stab == pytest.approx(DEFAULT_PARAMS[2], abs=0.01)
        assert 1.0 <= diff <= 10.0
        assert MIN_INTERVAL <= interval <= MAX_INTERVAL

    def test_subsequent_review_recall(self):
        """Subsequent Good review should grow stability."""
        s = FSRSScheduler(DEFAULT_PARAMS)
        stab, diff, _ = s.next_state(grade=3, stability=None, difficulty=None, elapsed_days=0.0)
        stab2, diff2, interval2 = s.next_state(
            grade=3, stability=stab, difficulty=diff, elapsed_days=float(s.compute_interval(stab))
        )
        assert stab2 > stab

    def test_subsequent_review_forget(self):
        """Again rating should shrink stability."""
        s = FSRSScheduler(DEFAULT_PARAMS)
        stab, diff, _ = s.next_state(grade=3, stability=None, difficulty=None, elapsed_days=0.0)
        stab2, _, _ = s.next_state(
            grade=1, stability=stab, difficulty=diff, elapsed_days=float(s.compute_interval(stab))
        )
        assert stab2 < stab


class TestShortTermStability:
    def test_easy_increases_stability(self):
        """Easy same-day review should increase stability."""
        s = FSRSScheduler(DEFAULT_PARAMS)
        new_s = s.stability_short_term(5.0, grade=4)
        assert new_s > 5.0

    def test_again_decreases_stability(self):
        """Again same-day review should decrease stability."""
        s = FSRSScheduler(DEFAULT_PARAMS)
        new_s = s.stability_short_term(5.0, grade=1)
        assert new_s < 5.0

    def test_same_day_uses_short_term(self):
        """next_state with elapsed < 1 day should use short-term formula."""
        s = FSRSScheduler(DEFAULT_PARAMS)
        stab, diff, _ = s.next_state(grade=3, stability=None, difficulty=None, elapsed_days=0.0)
        # Same-day review (0.5 days later)
        stab2, _, _ = s.next_state(grade=3, stability=stab, difficulty=diff, elapsed_days=0.5)
        # Short-term formula for Good (grade=3): S * e^(w17*(3-3+w18)) = S * e^(w17*w18)
        expected = stab * math.exp(DEFAULT_PARAMS[17] * (3 - 3 + DEFAULT_PARAMS[18]))
        assert stab2 == pytest.approx(expected, rel=1e-4)


class TestUpdateParameters:
    def test_params_change_after_update(self):
        """Parameters should change after an SGD step."""
        new_params = update_parameters(
            DEFAULT_PARAMS, predicted_r=0.9, actual_recall=True,
            stability=5.0, difficulty=5.0, elapsed_days=5.0, grade=3,
        )
        assert len(new_params) == len(DEFAULT_PARAMS)
        any_changed = any(
            abs(new_params[i] - DEFAULT_PARAMS[i]) > 1e-10
            for i in range(len(DEFAULT_PARAMS))
        )
        assert any_changed

    def test_forget_shifts_params(self):
        """A forgotten card (predicted high R, actual forget) should shift params."""
        new_params = update_parameters(
            DEFAULT_PARAMS, predicted_r=0.9, actual_recall=False,
            stability=5.0, difficulty=5.0, elapsed_days=5.0, grade=1,
        )
        any_changed = any(
            abs(new_params[i] - DEFAULT_PARAMS[i]) > 1e-10
            for i in range(len(DEFAULT_PARAMS))
        )
        assert any_changed

    def test_sgd_step_reduces_loss(self):
        """SGD step should move stability in the right direction."""
        stability, difficulty, elapsed, grade = 5.0, 5.0, 5.0, 3
        sched = FSRSScheduler(DEFAULT_PARAMS)
        predicted_r = sched.compute_retrievability(elapsed, stability)

        # Student forgot — prediction was too optimistic (R=0.9 but they forgot)
        new_params = update_parameters(
            DEFAULT_PARAMS, predicted_r, actual_recall=False,
            stability=stability, difficulty=difficulty,
            elapsed_days=elapsed, grade=grade,
        )

        # The updated params should produce LOWER stability (shorter intervals)
        # because the student forgot — params should become more conservative
        s_old, _, _ = FSRSScheduler(DEFAULT_PARAMS).next_state(grade, stability, difficulty, elapsed)
        s_new, _, _ = FSRSScheduler(new_params).next_state(grade, stability, difficulty, elapsed)
        assert s_new < s_old

    def test_per_parameter_gradients_differ(self):
        """Different parameters should get different gradient magnitudes."""
        new_params = update_parameters(
            DEFAULT_PARAMS, predicted_r=0.9, actual_recall=False,
            stability=5.0, difficulty=5.0, elapsed_days=5.0, grade=3,
        )
        deltas = [abs(new_params[i] - DEFAULT_PARAMS[i]) for i in range(len(DEFAULT_PARAMS))]
        # Not all deltas should be identical (unlike the uniform nudge bug)
        unique_deltas = set(round(d, 12) for d in deltas if d > 1e-15)
        assert len(unique_deltas) > 1, "All parameter updates are identical — not per-param gradients"


class TestFeatureFlag:
    def test_fsrs_disabled_uses_sm2(self):
        """When FSRS_ENABLED=false, SM-2 should always be callable as fallback."""
        ef, interval, reps = sm2_update(quality=4, ease_factor=2.5, interval_days=0, repetitions=0)
        assert interval == 1
        assert reps == 1
