"""Basic import tests for the progress API and schemas."""

from app.api.progress import get_leaderboard, get_my_progress, router
from app.schemas.progress import LeaderboardEntry, ProgressResponse, XPAwardResponse


class TestProgressSchemas:
    def test_progress_response_defaults(self):
        resp = ProgressResponse(
            course_id="abc",
            xp_points=0,
            streak_days=0,
            last_activity_date=None,
            quizzes_completed=0,
            flashcards_reviewed=0,
            speaking_sessions=0,
            badges=[],
        )
        assert resp.xp_points == 0
        assert resp.badges == []

    def test_progress_response_with_data(self):
        from datetime import date

        resp = ProgressResponse(
            course_id="course-123",
            xp_points=500,
            streak_days=3,
            last_activity_date=date(2026, 4, 8),
            quizzes_completed=5,
            flashcards_reviewed=20,
            speaking_sessions=2,
            badges=["first_quiz", "streak_7"],
        )
        assert resp.xp_points == 500
        assert resp.streak_days == 3
        assert len(resp.badges) == 2

    def test_leaderboard_entry(self):
        entry = LeaderboardEntry(
            rank=1,
            user_id="user-abc",
            full_name="Test User",
            avatar_url=None,
            xp_points=1000,
        )
        assert entry.rank == 1
        assert entry.full_name == "Test User"

    def test_xp_award_response(self):
        resp = XPAwardResponse(
            xp_earned=100,
            total_xp=500,
            streak_days=3,
            new_badges=["perfect_score"],
        )
        assert resp.xp_earned == 100
        assert len(resp.new_badges) == 1


class TestProgressRouterRegistered:
    def test_router_has_routes(self):
        assert len(router.routes) > 0

    def test_router_tags(self):
        assert "progress" in router.tags

    def test_endpoint_functions_exist(self):
        assert callable(get_my_progress)
        assert callable(get_leaderboard)
