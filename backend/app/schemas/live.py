from pydantic import BaseModel


class CreateLiveSessionRequest(BaseModel):
    quiz_id: str
    time_limit_seconds: int = 30
    settings: dict = {}


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
    user_id: str
    full_name: str
    score: int
