from pydantic import BaseModel, Field


class CreateLiveSessionRequest(BaseModel):
    quiz_id: str
    # Bounded so a client can't set a nonsense time limit — 5 seconds is the
    # smallest usable per-question window; 600s (10 min) is a generous upper
    # bound for long-form questions.
    time_limit_seconds: int = Field(default=30, ge=5, le=600)
    settings: dict = Field(default_factory=dict)


class LiveSessionResponse(BaseModel):
    id: str
    quiz_id: str
    course_id: str
    host_id: str
    join_code: str
    status: str
    participant_count: int
    time_limit_seconds: int
    created_at: str
    is_host: bool = False


class LiveLeaderboardEntry(BaseModel):
    rank: int
    user_id: str | None = None
    full_name: str
    score: int
