import json
import secrets
import string
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import WebSocket


def generate_join_code(length: int = 6) -> str:
    """Generate a random join code of uppercase letters and digits."""
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


def calculate_points(
    is_correct: bool, elapsed_seconds: float, time_limit: int, base_points: int = 1000
) -> int:
    """Calculate points for an answer based on correctness and speed.

    Faster correct answers earn more points. Wrong answers earn zero.
    """
    if not is_correct:
        return 0
    ratio = max(0, 1 - elapsed_seconds / time_limit)
    return int(base_points * ratio)


@dataclass
class SessionState:
    """In-memory state machine for a live quiz session."""

    session_id: str
    total_questions: int
    time_limit: int
    status: str = "waiting"
    current_question_index: int = 0
    question_started_at: datetime | None = None
    player_scores: dict[str, int] = field(default_factory=dict)
    player_answers: dict[str, dict[int, str]] = field(default_factory=dict)

    def start(self) -> None:
        self.status = "active"
        self.question_started_at = datetime.now(timezone.utc)

    def next_question(self) -> None:
        if self.status == "waiting":
            self.status = "active"
            self.question_started_at = datetime.now(timezone.utc)
            return
        self.current_question_index += 1
        if self.current_question_index >= self.total_questions:
            self.status = "finished"
        else:
            self.question_started_at = datetime.now(timezone.utc)

    def record_answer(self, user_id: str, answer: str, points: int) -> None:
        if user_id not in self.player_answers:
            self.player_answers[user_id] = {}
        self.player_answers[user_id][self.current_question_index] = answer
        self.player_scores[user_id] = self.player_scores.get(user_id, 0) + points

    def get_leaderboard(self, top_n: int = 10) -> list[dict]:
        sorted_players = sorted(
            self.player_scores.items(), key=lambda x: x[1], reverse=True
        )[:top_n]
        return [
            {"user_id": uid, "score": score, "rank": i + 1}
            for i, (uid, score) in enumerate(sorted_players)
        ]


class ConnectionManager:
    """Manage WebSocket connections per session."""

    def __init__(self) -> None:
        self.connections: dict[str, list[WebSocket]] = {}
        self.sessions: dict[str, SessionState] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        if session_id not in self.connections:
            self.connections[session_id] = []
        self.connections[session_id].append(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        if session_id in self.connections:
            self.connections[session_id] = [
                ws for ws in self.connections[session_id] if ws != websocket
            ]

    async def broadcast(self, session_id: str, message: dict) -> None:
        if session_id in self.connections:
            data = json.dumps(message)
            for ws in self.connections[session_id]:
                try:
                    await ws.send_text(data)
                except Exception:
                    pass

    def get_session(self, session_id: str) -> SessionState | None:
        return self.sessions.get(session_id)

    def create_session(
        self, session_id: str, total_questions: int, time_limit: int
    ) -> SessionState:
        state = SessionState(
            session_id=session_id,
            total_questions=total_questions,
            time_limit=time_limit,
        )
        self.sessions[session_id] = state
        return state

    def remove_session(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)
        self.connections.pop(session_id, None)


# Singleton
manager = ConnectionManager()
