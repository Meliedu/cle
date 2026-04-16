import asyncio
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
    player_correct: dict[str, dict[int, bool]] = field(default_factory=dict)
    participants: set[str] = field(default_factory=set)
    anonymous_users: set[str] = field(default_factory=set)
    # Lazily populated display-name cache so WS broadcasts can render real
    # names without a DB round-trip per broadcast.
    player_names: dict[str, str] = field(default_factory=dict)
    review_mode: str = "per_question"  # "per_question" | "final"

    def set_anonymity(self, user_id: str, anonymous: bool) -> None:
        if anonymous:
            self.anonymous_users.add(user_id)
        else:
            self.anonymous_users.discard(user_id)

    def get_answer_distribution(self, question_index: int) -> dict[str, int]:
        """Count player answers for a single question keyed by option label."""
        counts: dict[str, int] = {}
        for answers in self.player_answers.values():
            choice = answers.get(question_index)
            if choice is None:
                continue
            counts[choice] = counts.get(choice, 0) + 1
        return counts

    def elapsed_seconds(self) -> float:
        """Seconds since the current question started; 0 if not yet active."""
        if self.question_started_at is None or self.status != "active":
            return 0.0
        return (datetime.now(timezone.utc) - self.question_started_at).total_seconds()

    def add_participant(self, user_id: str) -> bool:
        """Mark a user as present in the session. Returns True if newly added."""
        if user_id in self.participants:
            return False
        self.participants.add(user_id)
        return True

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

    def record_answer(
        self,
        user_id: str,
        answer: str,
        points: int,
        is_correct: bool = False,
    ) -> bool:
        """Record a player's answer for the current question.

        Returns True if recorded, False if the player has already answered this
        question (prevents score inflation from duplicate submissions).
        """
        user_answers = self.player_answers.setdefault(user_id, {})
        if self.current_question_index in user_answers:
            return False
        user_answers[self.current_question_index] = answer
        self.player_correct.setdefault(user_id, {})[
            self.current_question_index
        ] = is_correct
        self.player_scores[user_id] = self.player_scores.get(user_id, 0) + points
        self.participants.add(user_id)
        return True

    def get_leaderboard(
        self,
        top_n: int = 10,
        names: dict[str, str] | None = None,
        include_user_ids: bool = False,
    ) -> list[dict]:
        """Return leaderboard entries with a display_name.

        - If a user opted in to anonymity, display_name is "Anonymous".
        - If a name lookup is provided, use it; otherwise fall back to a short
          user id stub so the frontend never has to do that itself.
        - ``user_id`` is only emitted when ``include_user_ids=True``. Broadcast
          paths (which reach every connected client) default to False so raw
          UUIDs never leak to peers who shouldn't have them. Host-only views
          that need to correlate rows to users must opt in explicitly.
        """
        names = names or {}
        sorted_players = sorted(
            self.player_scores.items(), key=lambda x: x[1], reverse=True
        )[:top_n]
        result: list[dict] = []
        for i, (uid, score) in enumerate(sorted_players):
            if uid in self.anonymous_users:
                display_name = "Anonymous"
            else:
                display_name = names.get(uid) or f"Player {uid[:4]}"
            entry: dict = {
                "score": score,
                "rank": i + 1,
                "display_name": display_name,
            }
            if include_user_ids:
                entry["user_id"] = uid
            result.append(entry)
        return result


class ConnectionManager:
    """Manage WebSocket connections per session."""

    def __init__(self) -> None:
        self.connections: dict[str, list[WebSocket]] = {}
        self.sessions: dict[str, SessionState] = {}
        # Per-session locks serialize state mutations like next_question so
        # concurrent host clicks can't double-advance the quiz.
        self._locks: dict[str, asyncio.Lock] = {}

    def get_lock(self, session_id: str) -> asyncio.Lock:
        """Return (and lazily create) the asyncio.Lock for a session."""
        lock = self._locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[session_id] = lock
        return lock

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
        self,
        session_id: str,
        total_questions: int,
        time_limit: int,
        review_mode: str = "per_question",
    ) -> SessionState:
        state = SessionState(
            session_id=session_id,
            total_questions=total_questions,
            time_limit=time_limit,
            review_mode=review_mode,
        )
        self.sessions[session_id] = state
        return state

    def remove_session(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)
        self.connections.pop(session_id, None)
        self._locks.pop(session_id, None)


# Singleton
manager = ConnectionManager()
