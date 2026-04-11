"""Integration tests for the recalibration batch job."""

import uuid
from types import SimpleNamespace

import pytest

from app.services.recalibrator import (
    build_initial_dirichlet,
    compute_transition_matrix,
    run_recalibration_pure,
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
        """A 'medium' item with 45/50 correct should be relabeled 'easy'.

        With k=5 (EQUIVALENT_SAMPLE_SIZE) and a neutral Dirichlet prior,
        a single item needs ~50 attempts for the posterior to cross the 0.90
        downgrade threshold.  After the item's own Dirichlet update:
          transition["medium"]["easy"] ≈ 2/13 ≈ 0.154
          α_easy = 0.154*5 + 45 = 45.77,  β_easy = 0.846*5 + 0 = 4.23
          posterior_easy ≈ 0.915 → crosses 0.90
        """
        stats = [_make_stats(
            llm_difficulty="medium",
            attempt_count=50,
            correct_count=45,
            hard_count=0,
            score_sum=44.0,  # mean 0.88 → classified as "easy"
        )]
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
        """An 'easy' item that most students get wrong should be upgraded.

        Upgrade threshold is 0.95 (stricter than downgrade's 0.90), so we
        need ~100 attempts with overwhelming hard signals.  After Dirichlet:
          transition["easy"]["hard"] ≈ 2/13 ≈ 0.154
          α_hard = 0.154*5 + 95 = 95.77,  β_hard = 0.846*5 + 0 = 4.23
          posterior_hard ≈ 0.958 → crosses 0.95
        """
        stats = [_make_stats(
            llm_difficulty="easy",
            attempt_count=100,
            correct_count=0,
            hard_count=95,
            score_sum=5.0,  # mean 0.05 → classified as "hard"
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
        assert matrix["medium"]["easy"] > 0.2

    def test_items_below_min_attempts_still_get_posteriors(self):
        """Items with < MIN_ATTEMPTS_FOR_LAYER1 don't contribute to Dirichlet
        but still get item-level posteriors computed.

        The qualifying item (50 attempts, 45 correct) relabels to 'easy';
        the low-data item (3 attempts) doesn't contribute to the Dirichlet
        but still receives a posterior (lands in reverts since 3 attempts
        can't overcome the prior).
        """
        stats = [
            _make_stats(
                llm_difficulty="medium",
                attempt_count=50,
                correct_count=45,
                hard_count=0,
                score_sum=44.0,  # mean 0.88 → "easy"
            ),
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
        relabeled_ids = {r[0] for r in relabels}
        assert stats[0].pool_item_id in relabeled_ids
