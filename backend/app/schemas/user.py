import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserResponse(BaseModel):
    id: uuid.UUID
    better_auth_id: str
    email: EmailStr
    full_name: str | None
    role: str
    avatar_url: str | None
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
