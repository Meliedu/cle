"""Model/constraint tests for ``attendance_records`` (P3 Task 3).

``attendance_records`` is a student-owned row table (Decision 2): participation
only, never mastery. Its RLS owner-isolation policy is proven separately under
``meli_app`` in Task 14; here we cover only the ORM columns, defaults and
CHECK/UNIQUE constraints via ``Base.metadata.create_all`` in the disposable test
DB (``db_session``).

Owner = ``user_id``. One attendance row per ``(meeting_id, user_id)``. ``status``
is present|late|excused|absent; ``source`` is qr|manual_override. Manual override
fields (``override_reason``/``override_by``) are nullable — populated only when a
teacher overrides a scan.
"""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError

from app.models.attendance import AttendanceRecord
from app.models.course import Course
from app.models.curriculum import CourseMeeting


@pytest_asyncio.fixture
async def seed_meeting(db_session, test_instructor):
    course = Course(
        name="LANG1511",
        language="zh",
        instructor_id=test_instructor.id,
        enroll_code="ATT" + uuid.uuid4().hex[:5].upper(),
    )
    db_session.add(course)
    await db_session.flush()
    meeting = CourseMeeting(
        course_id=course.id,
        meeting_index=1,
        title="Session 1",
        scheduled_at=datetime.now(timezone.utc),
    )
    db_session.add(meeting)
    await db_session.commit()
    await db_session.refresh(meeting)
    return meeting


@pytest.mark.asyncio
async def test_attendance_create_and_defaults(db_session, seed_meeting, test_student):
    meeting = seed_meeting
    rec = AttendanceRecord(
        meeting_id=meeting.id,
        user_id=test_student.id,
        status="present",
        source="qr",
    )
    db_session.add(rec)
    await db_session.commit()
    await db_session.refresh(rec)
    assert rec.id is not None
    assert rec.status == "present"
    assert rec.source == "qr"
    assert rec.override_reason is None
    assert rec.override_by is None
    assert rec.checked_in_at is not None
    assert rec.created_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["present", "late", "excused", "absent"])
async def test_attendance_status_accepts_all_valid(
    db_session, seed_meeting, test_student, status
):
    meeting = seed_meeting
    rec = AttendanceRecord(
        meeting_id=meeting.id,
        user_id=test_student.id,
        status=status,
        source="qr",
    )
    db_session.add(rec)
    await db_session.commit()
    await db_session.refresh(rec)
    assert rec.status == status


@pytest.mark.asyncio
async def test_attendance_bad_status_rejected(db_session, seed_meeting, test_student):
    meeting = seed_meeting
    db_session.add(
        AttendanceRecord(
            meeting_id=meeting.id,
            user_id=test_student.id,
            status="nonsense",
            source="qr",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_attendance_bad_source_rejected(db_session, seed_meeting, test_student):
    meeting = seed_meeting
    db_session.add(
        AttendanceRecord(
            meeting_id=meeting.id,
            user_id=test_student.id,
            status="present",
            source="beacon",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_attendance_manual_override_fields(
    db_session, seed_meeting, test_student, test_instructor
):
    meeting = seed_meeting
    rec = AttendanceRecord(
        meeting_id=meeting.id,
        user_id=test_student.id,
        status="excused",
        source="manual_override",
        override_reason="Sick note on file",
        override_by=test_instructor.id,
    )
    db_session.add(rec)
    await db_session.commit()
    await db_session.refresh(rec)
    assert rec.source == "manual_override"
    assert rec.override_reason == "Sick note on file"
    assert rec.override_by == test_instructor.id


@pytest.mark.asyncio
async def test_attendance_unique_meeting_user(
    db_session, seed_meeting, test_student
):
    meeting = seed_meeting
    db_session.add(
        AttendanceRecord(
            meeting_id=meeting.id,
            user_id=test_student.id,
            status="present",
            source="qr",
        )
    )
    await db_session.flush()
    db_session.add(
        AttendanceRecord(
            meeting_id=meeting.id,
            user_id=test_student.id,
            status="late",
            source="qr",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
