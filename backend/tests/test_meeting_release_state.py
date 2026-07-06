import pytest
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import Course
from app.models.curriculum import CourseMeeting
from app.models.user import User


async def _make_course(db_session: AsyncSession, instructor: User, enroll_code: str) -> Course:
    course = Course(
        name="Test", language="english",
        instructor_id=instructor.id, enroll_code=enroll_code,
    )
    db_session.add(course)
    await db_session.flush()
    return course


@pytest.mark.asyncio
async def test_meeting_defaults_release_state_locked(db_session, test_instructor):
    course = await _make_course(db_session, test_instructor, "RELSTAT1")
    m = CourseMeeting(
        course_id=course.id, meeting_index=1,
        scheduled_at=datetime.now(timezone.utc),
    )
    db_session.add(m)
    await db_session.commit()
    await db_session.refresh(m)
    assert m.release_state == "locked"
    assert m.topic_summary is None


@pytest.mark.asyncio
async def test_release_state_check_constraint(db_session, test_instructor):
    from sqlalchemy.exc import IntegrityError
    course = await _make_course(db_session, test_instructor, "RELSTAT2")
    m = CourseMeeting(
        course_id=course.id, meeting_index=2,
        scheduled_at=datetime.now(timezone.utc), release_state="oops",
    )
    db_session.add(m)
    with pytest.raises(IntegrityError):
        await db_session.commit()
