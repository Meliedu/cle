"""Tests for the Bayesian difficulty recalibrator core math."""

import pytest

from app.services.recalibrator import (
    DIFFICULTIES,
    DIRICHLET_PRIOR_STRONG,
    DIRICHLET_PRIOR_WEAK,
    DOWNGRADE_THRESHOLD,
    EASY_SCORE_THRESHOLD,
    EQUIVALENT_SAMPLE_SIZE,
    HARD_SCORE_THRESHOLD,
    UPGRADE_THRESHOLD,
    build_initial_dirichlet,
    classify_observed_difficulty,
    compute_item_posterior,
    compute_transition_matrix,
    make_relabel_decision,
    update_dirichlet,
)


# ---------------------------------------------------------------------------
# TestDirichletInitialization
# ---------------------------------------------------------------------------


class TestDirichletInitialization:
    def test_initial_params_shape(self):
        params = build_initial_dirichlet()
        for diff in DIFFICULTIES:
            assert diff in params
            for inner_diff in DIFFICULTIES:
                assert inner_diff in params[diff]

    def test_diagonal_is_strong_prior(self):
        params = build_initial_dirichlet()
        for diff in DIFFICULTIES:
            assert params[diff][diff] == DIRICHLET_PRIOR_STRONG

    def test_off_diagonal_is_weak_prior(self):
        params = build_initial_dirichlet()
        for row in DIFFICULTIES:
            for col in DIFFICULTIES:
                if row != col:
                    assert params[row][col] == DIRICHLET_PRIOR_WEAK

    def test_transition_matrix_rows_sum_to_one(self):
        params = build_initial_dirichlet()
        matrix = compute_transition_matrix(params)
        for row in DIFFICULTIES:
            total = sum(matrix[row][col] for col in DIFFICULTIES)
            assert pytest.approx(total, abs=1e-9) == 1.0

    def test_initial_matrix_favors_diagonal(self):
        params = build_initial_dirichlet()
        matrix = compute_transition_matrix(params)
        for diff in DIFFICULTIES:
            assert matrix[diff][diff] > 0.8


# ---------------------------------------------------------------------------
# TestObservedDifficultyClassification
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# TestDirichletUpdate
# ---------------------------------------------------------------------------


class TestDirichletUpdate:
    def test_update_shifts_probability(self):
        params = build_initial_dirichlet()
        # Apply 10 observations: LLM says medium, students find it easy
        for _ in range(10):
            params = update_dirichlet(params, "medium", "easy")
        matrix = compute_transition_matrix(params)
        assert matrix["medium"]["easy"] > 0.4

    def test_update_preserves_other_rows(self):
        params = build_initial_dirichlet()
        original_easy_row = {k: v for k, v in params["easy"].items()}
        params = update_dirichlet(params, "medium", "easy")
        assert params["easy"] == original_easy_row

    def test_update_increments_by_one(self):
        params = build_initial_dirichlet()
        original_val = params["medium"]["easy"]
        updated = update_dirichlet(params, "medium", "easy")
        assert updated["medium"]["easy"] == original_val + 1


# ---------------------------------------------------------------------------
# TestItemPosterior
# ---------------------------------------------------------------------------


class TestItemPosterior:
    def test_no_data_returns_prior(self):
        params = build_initial_dirichlet()
        matrix = compute_transition_matrix(params)
        posterior = compute_item_posterior(
            llm_difficulty="medium",
            transition_matrix=matrix,
            correct_count=0,
            hard_count=0,
            attempt_count=0,
        )
        # With no data the posterior should match the prior —
        # for LLM=medium, medium should dominate
        assert posterior["medium"] > posterior["easy"]
        assert posterior["medium"] > posterior["hard"]

    def test_many_correct_shifts_to_easy(self):
        params = build_initial_dirichlet()
        matrix = compute_transition_matrix(params)
        posterior = compute_item_posterior(
            llm_difficulty="medium",
            transition_matrix=matrix,
            correct_count=18,
            hard_count=0,
            attempt_count=20,
        )
        # 18/20 correct overwhelms the prior — easy should dominate
        assert posterior["easy"] > 0.75
        assert posterior["easy"] == max(posterior.values())

    def test_many_wrong_shifts_to_hard(self):
        params = build_initial_dirichlet()
        matrix = compute_transition_matrix(params)
        posterior = compute_item_posterior(
            llm_difficulty="medium",
            transition_matrix=matrix,
            correct_count=0,
            hard_count=15,
            attempt_count=20,
        )
        assert posterior["hard"] > posterior["easy"]

    def test_biased_prior_accelerates_relabeling(self):
        """A course-level prior that suspects mislabeling should make
        the posterior converge faster than the default prior."""
        # Default prior
        default_params = build_initial_dirichlet()
        default_matrix = compute_transition_matrix(default_params)

        # Biased prior: medium→easy already observed many times
        biased_params = build_initial_dirichlet()
        for _ in range(20):
            biased_params = update_dirichlet(biased_params, "medium", "easy")
        biased_matrix = compute_transition_matrix(biased_params)

        # Same evidence: 8/10 correct
        default_post = compute_item_posterior(
            "medium", default_matrix, correct_count=8, hard_count=0, attempt_count=10,
        )
        biased_post = compute_item_posterior(
            "medium", biased_matrix, correct_count=8, hard_count=0, attempt_count=10,
        )
        # Biased prior should push easy posterior higher
        assert biased_post["easy"] > default_post["easy"]


# ---------------------------------------------------------------------------
# TestRelabelDecision
# ---------------------------------------------------------------------------


class TestRelabelDecision:
    def test_no_relabel_when_matches_llm(self):
        posterior = {"easy": 0.1, "medium": 0.8, "hard": 0.1}
        result = make_relabel_decision("medium", posterior)
        assert result is None

    def test_downgrade_at_lower_threshold(self):
        # 0.91 easy posterior for medium item — exceeds DOWNGRADE_THRESHOLD (0.90)
        posterior = {"easy": 0.91, "medium": 0.05, "hard": 0.04}
        result = make_relabel_decision("medium", posterior)
        assert result is not None
        label, confidence = result
        assert label == "easy"
        assert confidence == 0.91

    def test_upgrade_needs_higher_threshold(self):
        # 0.92 hard posterior for medium item — below UPGRADE_THRESHOLD (0.95)
        posterior = {"easy": 0.04, "medium": 0.04, "hard": 0.92}
        result = make_relabel_decision("medium", posterior)
        assert result is None

    def test_upgrade_at_high_confidence(self):
        # 0.96 hard posterior for medium item — above UPGRADE_THRESHOLD (0.95)
        posterior = {"easy": 0.02, "medium": 0.02, "hard": 0.96}
        result = make_relabel_decision("medium", posterior)
        assert result is not None
        label, confidence = result
        assert label == "hard"
        assert confidence == 0.96

    def test_downgrade_two_levels(self):
        # 0.92 easy posterior for hard item — downgrade, exceeds 0.90
        posterior = {"easy": 0.92, "medium": 0.05, "hard": 0.03}
        result = make_relabel_decision("hard", posterior)
        assert result is not None
        label, confidence = result
        assert label == "easy"
        assert confidence == 0.92
