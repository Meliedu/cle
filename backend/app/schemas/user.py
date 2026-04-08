import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserResponse(BaseModel):
    id: uuid.UUID
    clerk_id: str
    email: EmailStr
    full_name: str | None
    role: str
    avatar_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
