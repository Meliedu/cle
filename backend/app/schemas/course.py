import uuid
from datetime import datetime

from pydantic import BaseModel


class CourseCreate(BaseModel):
    name: str
    code: str | None = None
    description: str | None = None
    language: str
    semester: str | None = None
    settings: dict = {}


class CourseUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    description: str | None = None
    language: str | None = None
    semester: str | None = None
    settings: dict | None = None


class CourseResponse(BaseModel):
    id: uuid.UUID
    name: str
    code: str | None
    description: str | None
    language: str
    semester: str | None
    instructor_id: uuid.UUID
    enroll_code: str
    settings: dict
    setup_status: str
    setup_checklist: dict
    join_mode: str
    enroll_code_active: bool
    context_status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EnrollByCodeRequest(BaseModel):
    enroll_code: str


class EnrollmentCreate(BaseModel):
    user_email: str | None = None
    course_code: str | None = None


class EnrollmentResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    enrolled_at: datetime

    model_config = {"from_attributes": True}
