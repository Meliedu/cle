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

    @classmethod
    def is_enabled(cls, prefs: dict, key: str) -> bool:
        """Backend-authoritative opt-out default.

        Contract: absent key = enabled (opt-out model); the frontend form and
        future notification senders MUST use this rule when deciding whether
        a user receives a given notification.
        """
        return bool(prefs.get(key, True))


class NotificationPrefsUpdate(BaseModel):
    notification_prefs: NotificationPrefs


class UserResponse(BaseModel):
    id: uuid.UUID
    better_auth_id: str
    email: EmailStr
    full_name: str | None
    role: str
    avatar_url: str | None
    # Deliberately `dict`, not `NotificationPrefs`: the stored value is a
    # sparse map (only keys the user has toggled). Typing it as the schema
    # would serialize every absent key as null, changing the wire contract.
    # Consumers resolve absent keys via NotificationPrefs.is_enabled().
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
