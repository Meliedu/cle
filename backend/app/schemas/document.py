import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    uploaded_by: uuid.UUID
    filename: str
    file_type: str
    file_size: int | None
    status: str
    page_count: int | None
    word_count: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
