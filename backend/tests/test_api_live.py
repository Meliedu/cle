"""Basic import and schema tests for the live quiz API."""

from app.api.live import (
    create_live_session,
    get_live_session,
    list_live_sessions,
    router,
    websocket_live,
)
from app.schemas.live import (
    CreateLiveSessionRequest,
    LiveLeaderboardEntry,
    LiveSessionResponse,
)


class TestLiveSchemas:
    def test_create_live_session_request_defaults(self):
        req = CreateLiveSessionRequest(quiz_id="quiz-1")
        assert req.quiz_id == "quiz-1"
        assert req.time_limit_seconds == 30
        assert req.settings == {}

    def test_create_live_session_request_custom(self):
        req = CreateLiveSessionRequest(
            quiz_id="quiz-2",
            time_limit_seconds=15,
            settings={"shuffle": True},
        )
        assert req.time_limit_seconds == 15
        assert req.settings == {"shuffle": True}

    def test_live_session_response(self):
        resp = LiveSessionResponse(
            id="session-1",
            quiz_id="quiz-1",
            course_id="course-1",
            host_id="host-1",
            join_code="ABC123",
            status="waiting",
            participant_count=0,
            time_limit_seconds=30,
            created_at="2026-04-09T10:00:00+00:00",
        )
        assert resp.id == "session-1"
        assert resp.join_code == "ABC123"
        assert resp.status == "waiting"
        assert resp.participant_count == 0
        assert resp.time_limit_seconds == 30

    def test_live_session_response_active(self):
        resp = LiveSessionResponse(
            id="session-2",
            quiz_id="quiz-1",
            course_id="course-1",
            host_id="host-1",
            join_code="XYZ789",
            status="active",
            participant_count=5,
            time_limit_seconds=20,
            created_at="2026-04-09T11:00:00+00:00",
        )
        assert resp.status == "active"
        assert resp.participant_count == 5

    def test_live_leaderboard_entry(self):
        entry = LiveLeaderboardEntry(
            rank=1,
            user_id="user-1",
            full_name="Alice",
            score=950,
        )
        assert entry.rank == 1
        assert entry.user_id == "user-1"
        assert entry.full_name == "Alice"
        assert entry.score == 950

    def test_live_leaderboard_entry_zero_score(self):
        entry = LiveLeaderboardEntry(
            rank=3,
            user_id="user-3",
            full_name="Charlie",
            score=0,
        )
        assert entry.score == 0


class TestLiveRouterRegistered:
    def test_router_has_routes(self):
        assert len(router.routes) > 0

    def test_router_tags(self):
        assert "live-quiz" in router.tags

    def test_endpoint_functions_exist(self):
        assert callable(create_live_session)
        assert callable(list_live_sessions)
        assert callable(get_live_session)
        assert callable(websocket_live)
