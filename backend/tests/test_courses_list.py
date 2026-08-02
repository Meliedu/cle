"""GET /api/courses — the roster list.

The regression this file pins: a course whose instructor has no enrollment
row of their own was invisible to that instructor everywhere (dashboard,
roster, sidebar), because the list joined through `enrollments` only. An
owner must always see their course, enrollment row or not.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course, Enrollment, User


@pytest_asyncio.fixture
async def other_instructor(db_session: AsyncSession) -> User:
    user = User(
        better_auth_id="dev_other_instructor_001",
        email="other-instructor@ust.hk",
        full_name="Other Instructor",
        role="instructor",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _course(name: str, code: str, instructor: User, enroll_code: str) -> Course:
    return Course(
        name=name,
        code=code,
        language="chinese",
        instructor_id=instructor.id,
        enroll_code=enroll_code,
    )


@pytest.mark.asyncio
async def test_owned_course_without_enrollment_row_is_listed(
    async_client: AsyncClient, db_session: AsyncSession, logged_in_user: User
):
    course = _course("Orphan Draft", "ORPH100", logged_in_user, "ORPHC001")
    db_session.add(course)
    await db_session.commit()

    r = await async_client.get("/api/courses")
    assert r.status_code == 200
    codes = [c["code"] for c in r.json()["data"]]
    assert "ORPH100" in codes


@pytest.mark.asyncio
async def test_owned_and_enrolled_course_is_listed_once(
    async_client: AsyncClient, db_session: AsyncSession, logged_in_user: User
):
    course = _course("Owned Course", "OWNED100", logged_in_user, "OWNEDC01")
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(
            course_id=course.id,
            user_id=logged_in_user.id,
            role="instructor",
            status="active",
        )
    )
    await db_session.commit()

    r = await async_client.get("/api/courses")
    assert r.status_code == 200
    codes = [c["code"] for c in r.json()["data"]]
    assert codes.count("OWNED100") == 1
    assert r.json()["meta"]["total"] == len(codes)


@pytest.mark.asyncio
async def test_active_enrollment_in_another_instructors_course_is_listed(
    async_client: AsyncClient,
    db_session: AsyncSession,
    logged_in_user: User,
    other_instructor: User,
):
    course = _course("Their Course", "THEIR100", other_instructor, "THEIRC01")
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(
            course_id=course.id,
            user_id=logged_in_user.id,
            role="student",
            status="active",
        )
    )
    await db_session.commit()

    r = await async_client.get("/api/courses")
    codes = [c["code"] for c in r.json()["data"]]
    assert "THEIR100" in codes


@pytest.mark.asyncio
async def test_pending_enrollment_is_not_listed(
    async_client: AsyncClient,
    db_session: AsyncSession,
    logged_in_user: User,
    other_instructor: User,
):
    course = _course("Pending Course", "PEND100", other_instructor, "PENDC001")
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(
            course_id=course.id,
            user_id=logged_in_user.id,
            role="student",
            status="pending",
        )
    )
    await db_session.commit()

    r = await async_client.get("/api/courses")
    codes = [c["code"] for c in r.json()["data"]]
    assert "PEND100" not in codes
