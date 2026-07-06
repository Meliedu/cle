import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class NotificationPrefs(BaseModel):
    """Whitelisted notification preference keys. ``extra="forbid"`` makes the
    PATCH endpoint reject any key that is not one of the five below (422)."""

    model_config = ConfigDict(extra="forbid")

    checkpoint_published: bool | None = None
    report_ready: bool | None = None
    follow_up_assigned: bool | None = None
    quiz_due_soon: bool | None = None
    weekly_summary: bool | None = None


class NotificationPrefsUpdate(BaseModel):
    notification_prefs: NotificationPrefs


class UserResponse(BaseModel):
    id: uuid.UUID
    better_auth_id: str
    email: EmailStr
    full_name: str | None
    role: str
    avatar_url: str | None
    notification_prefs: dict = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class LinkUserRequest(BaseModel):
    """Body of the internal POST /api/internal/users/link endpoint, called
    by the Better Auth `databaseHooks.user.create.after` hook in the
    Next.js frontend. See `app/api/internal.py`.
    """

    better_auth_id: str = Field(min_length=1, max_length=255)
    email: EmailStr
    full_name: str | None = None
    avatar_url: str | None = None


class LinkUserResponse(BaseModel):
    user_id: uuid.UUID
    role: str
