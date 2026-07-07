"""Attendance / QR-launch schemas (P3 T9+)."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# The four attendance states (mirrors the ``ck_attendance_records_status_valid``
# CHECK). ``absent`` is a legal override target AND the derived roster default
# for a student who never scanned.
AttendanceStatus = Literal["present", "late", "excused", "absent"]


class LaunchRequest(BaseModel):
    """Body for ``POST /checkpoints/{id}/launch``.

    ``rotate`` closes the prior active launch and issues a fresh token; the
    default (first launch) creates the single active launch.
    """

    rotate: bool = False


class LaunchResponse(BaseModel):
    """A minted (or rotated) QR launch — the signed ``token`` is rendered as a
    QR by the teacher panel (T045); ``window_end`` drives the countdown."""

    id: uuid.UUID
    checkpoint_id: uuid.UUID
    meeting_id: uuid.UUID
    token: str
    jti: str
    window_start: datetime
    window_end: datetime
    status: str

    model_config = {"from_attributes": True}


class ScanResponse(BaseModel):
    """Result of a QR scan (``POST /api/attend/{token}``, P3 T10).

    Carries the recorded attendance plus the ``intro_route`` the client routes
    to next (S034 checkpoint intro). ``status`` is ``present``/``late``.
    """

    attendance_id: uuid.UUID
    meeting_id: uuid.UUID
    checkpoint_id: uuid.UUID
    status: str
    source: str
    checked_in_at: datetime
    intro_route: str


# ----- roster result + manual override (P3 T11, T019) -----


class AttendanceRosterEntry(BaseModel):
    """One active-enrolled student's attendance for a meeting.

    ``absent`` is DERIVED — a student with no ``attendance_records`` row is
    reported ``absent`` with ``attendance_id``/``source``/``checked_in_at`` all
    ``None`` (there is nothing to override yet). A present/late/excused entry
    carries its row id so the teacher panel can PATCH an override.
    """

    user_id: uuid.UUID
    full_name: str | None
    email: str
    status: AttendanceStatus
    attendance_id: uuid.UUID | None = None
    source: str | None = None
    override_reason: str | None = None
    override_by: uuid.UUID | None = None
    checked_in_at: datetime | None = None


class AttendanceRoster(BaseModel):
    """Teacher roster for a single meeting (S037 / T019).

    Counts are over the derived roster (every active student appears exactly
    once). ``absent_count`` includes the derived-absent students.
    """

    meeting_id: uuid.UUID
    course_id: uuid.UUID
    present_count: int
    late_count: int
    excused_count: int
    absent_count: int
    entries: list[AttendanceRosterEntry]


class AttendanceOverrideRequest(BaseModel):
    """Body for ``PATCH /attendance/{id}`` — a teacher manual override.

    ``override_reason`` is REQUIRED (min length 1) so every override is
    attributable; a missing/blank reason is a 422 at the schema boundary.
    """

    status: AttendanceStatus
    override_reason: str = Field(min_length=1)


class AttendanceOverrideResponse(BaseModel):
    """The overridden ``attendance_records`` row (``source='manual_override'``)."""

    attendance_id: uuid.UUID
    meeting_id: uuid.UUID
    user_id: uuid.UUID
    status: str
    source: str
    override_reason: str | None
    override_by: uuid.UUID | None
    checked_in_at: datetime
