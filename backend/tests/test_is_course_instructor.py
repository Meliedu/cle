"""P7 B11 (Decision 9.3) — pin ``documents.py::_is_course_instructor`` behaviour.

The document-access guard treats *any* instructor-role Enrollment as course
staff — NOT only the course owner (``courses.instructor_id``). This is the
intentional co-instructor / course-staff model: a TA or co-instructor enrolled
with ``role='instructor'`` gets the teacher document surface. This test pins that
behaviour so a future refactor to owner-only is a conscious, tested change.
"""
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.documents import _is_course_instructor
from app.models.course import Course, Enrollment
from app.models.user import User


async def _course(db: AsyncSession, owner: User) -> Course:
    course = Course(
        name="Staff Course", language="zh", instructor_id=owner.id,
        enroll_code="ST" + uuid.uuid4().hex[:6].upper(),
    )
    db.add(course)
    await db.flush()
    return course


async def _user(db: AsyncSession, tag: str, role: str) -> User:
    u = User(
        better_auth_id=f"cistaff_{tag}", email=f"{tag}@ust.hk",
        full_name=tag, role=role,
    )
    db.add(u)
    await db.flush()
    return u


@pytest.mark.asyncio
async def test_owner_with_instructor_enrollment_is_instructor(
    db_session: AsyncSession, test_instructor: User
):
    course = await _course(db_session, test_instructor)
    db_session.add(
        Enrollment(course_id=course.id, user_id=test_instructor.id, role="instructor")
    )
    await db_session.commit()
    assert await _is_course_instructor(db_session, course.id, test_instructor.id) is True


@pytest.mark.asyncio
async def test_co_instructor_enrollment_is_instructor(
    db_session: AsyncSession, test_instructor: User
):
    """A co-instructor (not the owner) with an instructor enrollment counts."""
    course = await _course(db_session, test_instructor)
    co = await _user(db_session, "co", "instructor")
    db_session.add(
        Enrollment(course_id=course.id, user_id=co.id, role="instructor")
    )
    await db_session.commit()
    assert await _is_course_instructor(db_session, course.id, co.id) is True


@pytest.mark.asyncio
async def test_student_enrollment_is_not_instructor(
    db_session: AsyncSession, test_instructor: User
):
    course = await _course(db_session, test_instructor)
    student = await _user(db_session, "stud", "student")
    db_session.add(
        Enrollment(
            course_id=course.id, user_id=student.id, role="student", status="active"
        )
    )
    await db_session.commit()
    assert await _is_course_instructor(db_session, course.id, student.id) is False


@pytest.mark.asyncio
async def test_non_enrolled_user_is_not_instructor(
    db_session: AsyncSession, test_instructor: User
):
    course = await _course(db_session, test_instructor)
    outsider = await _user(db_session, "out", "instructor")
    await db_session.commit()
    assert await _is_course_instructor(db_session, course.id, outsider.id) is False
