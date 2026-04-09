from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from app.services.gamification import (
    BADGE_DEFINITIONS,
    calculate_quiz_xp,
    calculate_streak,
    check_badges,
)


class TestCalculateQuizXP:
    def test_perfect_score(self):
        assert calculate_quiz_xp(score=100.0) == 1000

    def test_partial_score(self):
        assert calculate_quiz_xp(score=80.0) == 800

    def test_zero_score(self):
        assert calculate_quiz_xp(score=0.0) == 0

    def test_rounds_down(self):
        assert calculate_quiz_xp(score=33.33) == 333


class TestCalculateStreak:
    def test_first_activity(self):
        streak, new_date = calculate_streak(0, None, date(2026, 4, 8))
        assert streak == 1
        assert new_date == date(2026, 4, 8)

    def test_consecutive_day(self):
        streak, _ = calculate_streak(5, date(2026, 4, 7), date(2026, 4, 8))
        assert streak == 6

    def test_same_day_no_increment(self):
        streak, _ = calculate_streak(5, date(2026, 4, 8), date(2026, 4, 8))
        assert streak == 5

    def test_gap_resets_streak(self):
        streak, _ = calculate_streak(10, date(2026, 4, 5), date(2026, 4, 8))
        assert streak == 1


class TestCheckBadges:
    def test_first_quiz_badge(self):
        progress = MagicMock(
            quizzes_completed=1,
            flashcards_reviewed=0,
            speaking_sessions=0,
            streak_days=0,
            badges=[],
        )
        new_badges = check_badges(progress, quiz_score=80.0, quiz_time_seconds=None)
        assert "first_quiz" in new_badges

    def test_perfect_score_badge(self):
        progress = MagicMock(
            quizzes_completed=5,
            flashcards_reviewed=0,
            speaking_sessions=0,
            streak_days=0,
            badges=["first_quiz"],
        )
        new_badges = check_badges(progress, quiz_score=100.0, quiz_time_seconds=None)
        assert "perfect_score" in new_badges

    def test_streak_7_badge(self):
        progress = MagicMock(
            quizzes_completed=5,
            flashcards_reviewed=10,
            speaking_sessions=0,
            streak_days=7,
            badges=["first_quiz"],
        )
        new_badges = check_badges(progress, quiz_score=None, quiz_time_seconds=None)
        assert "streak_7" in new_badges

    def test_no_duplicate_badges(self):
        progress = MagicMock(
            quizzes_completed=5,
            flashcards_reviewed=0,
            speaking_sessions=0,
            streak_days=7,
            badges=["first_quiz", "streak_7"],
        )
        new_badges = check_badges(progress, quiz_score=100.0, quiz_time_seconds=None)
        assert "first_quiz" not in new_badges
        assert "streak_7" not in new_badges

    def test_speed_learner_badge(self):
        progress = MagicMock(
            quizzes_completed=3,
            flashcards_reviewed=0,
            speaking_sessions=0,
            streak_days=0,
            badges=[],
        )
        new_badges = check_badges(progress, quiz_score=90.0, quiz_time_seconds=45)
        assert "speed_learner" in new_badges
