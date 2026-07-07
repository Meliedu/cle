import pytest
from sqlalchemy.exc import IntegrityError

from app.models.course import Course, Enrollment


async def _course(db_session, instructor):
    course = Course(
        name="LANG1511", language="zh", instructor_id=instructor.id,
        enroll_code="ABCD2345",
    )
    db_session.add(course)
    await db_session.flush()
    return course


@pytest.mark.asyncio
async def test_enrollment_defaults_active(db_session, test_instructor, test_student):
    course = await _course(db_session, test_instructor)
    e = Enrollment(course_id=course.id, user_id=test_student.id, role="student")
    db_session.add(e)
    await db_session.commit()
    await db_session.refresh(e)
    assert e.status == "active"


@pytest.mark.asyncio
async def test_enrollment_can_be_pending(db_session, test_instructor, test_student):
    course = await _course(db_session, test_instructor)
    e = Enrollment(
        course_id=course.id, user_id=test_student.id, role="student", status="pending",
    )
    db_session.add(e)
    await db_session.commit()
    await db_session.refresh(e)
    assert e.status == "pending"


@pytest.mark.asyncio
async def test_enrollment_status_check_constraint(db_session, test_instructor, test_student):
    course = await _course(db_session, test_instructor)
    e = Enrollment(
        course_id=course.id, user_id=test_student.id, role="student", status="nonsense",
    )
    db_session.add(e)
    with pytest.raises(IntegrityError):
        await db_session.commit()
