import pytest

from app.services.live_quiz import (
    ConnectionManager,
    SessionState,
    calculate_points,
    generate_join_code,
)


class TestGenerateJoinCode:
    def test_default_length(self):
        code = generate_join_code()
        assert len(code) == 6

    def test_custom_length(self):
        code = generate_join_code(length=8)
        assert len(code) == 8

    def test_only_uppercase_and_digits(self):
        code = generate_join_code(length=100)
        assert code == code.upper()
        assert all(c.isalpha() or c.isdigit() for c in code)

    def test_uniqueness(self):
        codes = {generate_join_code() for _ in range(50)}
        assert len(codes) > 1


class TestCalculatePoints:
    def test_instant_correct_answer(self):
        assert (
            calculate_points(
                is_correct=True, elapsed_seconds=0, time_limit=30, base_points=1000
            )
            == 1000
        )

    def test_half_time_correct(self):
        assert (
            calculate_points(
                is_correct=True, elapsed_seconds=15, time_limit=30, base_points=1000
            )
            == 500
        )

    def test_wrong_answer_zero_points(self):
        assert (
            calculate_points(
                is_correct=False, elapsed_seconds=5, time_limit=30, base_points=1000
            )
            == 0
        )

    def test_at_time_limit(self):
        assert (
            calculate_points(
                is_correct=True, elapsed_seconds=30, time_limit=30, base_points=1000
            )
            == 0
        )

    def test_over_time_limit_clamps_to_zero(self):
        assert (
            calculate_points(
                is_correct=True, elapsed_seconds=60, time_limit=30, base_points=1000
            )
            == 0
        )

    def test_custom_base_points(self):
        assert (
            calculate_points(
                is_correct=True, elapsed_seconds=0, time_limit=30, base_points=500
            )
            == 500
        )


class TestSessionState:
    def test_initial_state(self):
        state = SessionState(session_id="test", total_questions=5, time_limit=30)
        assert state.status == "waiting"
        assert state.current_question_index == 0
        assert state.question_started_at is None
        assert state.player_scores == {}
        assert state.player_answers == {}

    def test_start_transitions_to_active(self):
        state = SessionState(session_id="test", total_questions=5, time_limit=30)
        state.start()
        assert state.status == "active"
        assert state.question_started_at is not None

    def test_next_question_advances(self):
        state = SessionState(session_id="test", total_questions=5, time_limit=30)
        state.start()
        state.next_question()
        assert state.current_question_index == 1
        assert state.status == "active"

    def test_next_question_from_waiting_starts_session(self):
        """First call from waiting transitions to active without skipping Q1."""
        state = SessionState(session_id="test", total_questions=5, time_limit=30)
        assert state.status == "waiting"
        state.next_question()
        assert state.status == "active"
        assert state.current_question_index == 0
        assert state.question_started_at is not None

    def test_last_question_finishes(self):
        state = SessionState(session_id="test", total_questions=2, time_limit=30)
        state.start()
        state.next_question()  # index becomes 1 (last question)
        state.next_question()  # index becomes 2, past total_questions
        assert state.status == "finished"

    def test_record_answer_accumulates_across_questions(self):
        state = SessionState(session_id="test", total_questions=5, time_limit=30)
        state.start()
        assert state.record_answer("user1", "A", 1000) is True
        state.next_question()
        assert state.record_answer("user1", "B", 500) is True
        assert state.player_scores["user1"] == 1500

    def test_record_answer_rejects_duplicate_for_same_question(self):
        """Same user submitting twice for the same question must not double-score."""
        state = SessionState(session_id="test", total_questions=5, time_limit=30)
        state.start()
        assert state.record_answer("user1", "A", 1000) is True
        assert state.record_answer("user1", "B", 500) is False
        assert state.player_scores["user1"] == 1000
        assert state.player_answers["user1"] == {0: "A"}

    def test_record_answer_stores_answer_per_question(self):
        state = SessionState(session_id="test", total_questions=5, time_limit=30)
        state.start()
        state.record_answer("user1", "A", 1000)
        state.next_question()
        state.record_answer("user1", "C", 500)
        assert state.player_answers["user1"] == {0: "A", 1: "C"}

    def test_get_leaderboard_sorted(self):
        state = SessionState(session_id="test", total_questions=5, time_limit=30)
        state.player_scores = {"u1": 300, "u2": 900, "u3": 600}
        leaderboard = state.get_leaderboard()
        assert leaderboard[0] == {"user_id": "u2", "score": 900, "rank": 1}
        assert leaderboard[1] == {"user_id": "u3", "score": 600, "rank": 2}
        assert leaderboard[2] == {"user_id": "u1", "score": 300, "rank": 3}

    def test_get_leaderboard_top_n(self):
        state = SessionState(session_id="test", total_questions=5, time_limit=30)
        state.player_scores = {f"u{i}": i * 100 for i in range(20)}
        leaderboard = state.get_leaderboard(top_n=3)
        assert len(leaderboard) == 3
        assert leaderboard[0]["rank"] == 1

    def test_get_leaderboard_empty(self):
        state = SessionState(session_id="test", total_questions=5, time_limit=30)
        assert state.get_leaderboard() == []


class TestConnectionManager:
    def test_create_session(self):
        mgr = ConnectionManager()
        session = mgr.create_session("s1", total_questions=10, time_limit=20)
        assert session.session_id == "s1"
        assert session.total_questions == 10
        assert session.time_limit == 20
        assert session.status == "waiting"

    def test_get_session(self):
        mgr = ConnectionManager()
        mgr.create_session("s1", total_questions=5, time_limit=30)
        assert mgr.get_session("s1") is not None
        assert mgr.get_session("nonexistent") is None

    def test_remove_session(self):
        mgr = ConnectionManager()
        mgr.create_session("s1", total_questions=5, time_limit=30)
        mgr.connections["s1"] = []
        mgr.remove_session("s1")
        assert mgr.get_session("s1") is None
        assert "s1" not in mgr.connections

    def test_remove_nonexistent_session_no_error(self):
        mgr = ConnectionManager()
        mgr.remove_session("nonexistent")  # should not raise
