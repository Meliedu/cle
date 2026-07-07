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


class EnrollByCodeResult(BaseModel):
    """Result of a join-by-code attempt.

    ``enrollment_status`` tells the funnel whether the join landed ``active``
    (instant join -> S013 join-success) or ``pending`` (awaits teacher approval
    -> pending-approval screen). ``course`` mirrors the prior bare
    ``CourseResponse`` payload so the client still has full course context.
    """

    course: CourseResponse
    enrollment_status: str


class CourseLookupResult(BaseModel):
    """Non-committing resolve of a join code (S003 code entry).

    Lets the student funnel turn a typed code into a ``course_id`` plus the
    branch signals it needs (``is_open`` for the setup gate, ``join_mode`` for
    the approval branch, ``code_active`` to distinguish an inactive code from an
    unknown one) *without* creating an enrollment. Unknown codes 404 (no
    existence leak); a known-but-inactive code returns 200 with
    ``code_active=False`` so S004 can show the right copy.
    """

    course_id: uuid.UUID
    name: str
    is_open: bool
    join_mode: str
    code_active: bool


class JoinRequestOut(BaseModel):
    """A pending (or decided) join request with the requesting student's info.

    ``requested_at`` mirrors the enrollment row's ``enrolled_at``. Reused for
    both the pending list (T033 join-request-approval) and the approve/deny
    responses so the client gets the post-decision status back.
    """

    enrollment_id: uuid.UUID
    user_id: uuid.UUID
    full_name: str | None
    email: str
    requested_at: datetime
    status: str


class RosterEntryOut(BaseModel):
    """An active enrollment row + user info for the class roster (T032)."""

    enrollment_id: uuid.UUID
    user_id: uuid.UUID
    full_name: str | None
    email: str
    role: str
    enrolled_at: datetime
    status: str


class EnrollmentCreate(BaseModel):
    user_email: str | None = None
    course_code: str | None = None


class EnrollmentResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    status: str
    enrolled_at: datetime

    model_config = {"from_attributes": True}
