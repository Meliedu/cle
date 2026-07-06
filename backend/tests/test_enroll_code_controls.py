"""Task 16: enroll-code controls — rotate + deactivate (class-code step, T025).

The class-code setup step (T025) reveals / rotates / deactivates the course
``enroll_code``. This covers the two owner-guarded controls added to
``api/courses.py``:

- ``POST /courses/{id}/enroll-code/rotate`` → mint a fresh unique code, mark it
  active; the old code no longer resolves via ``enroll-by-code``.
- ``POST /courses/{id}/enroll-code/deactivate`` → flip ``enroll_code_active`` to
  ``False`` (the P2 join-refusal wiring reads this column; here we just assert
  the flip).

Guarded by ``get_owned_course`` (instructor + ownership) so students get 403 and
non-owners get 404. Mirrors ``test_score_categories_api.py`` fixtures.
"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.main import app
from app.models import Course, Enrollment, User


@pytest_asyncio.fixture
async def owned_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="Code Test", language="english",
        instructor_id=logged_in_user.id, enroll_code="CODE0001",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor")
    )
    await db_session.commit()
    await db_session.refresh(course)
    return course


# ----- rotate -----

@pytest.mark.asyncio
async def test_rotate_returns_new_active_code(
    async_client: AsyncClient, owned_course: Course, db_session: AsyncSession
):
    old_code = owned_course.enroll_code
    r = await async_client.post(
        f"/api/courses/{owned_course.id}/enroll-code/rotate"
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["enroll_code"] != old_code
    assert data["enroll_code_active"] is True

    # The old code no longer resolves to any live course.
    await db_session.refresh(owned_course)
    assert owned_course.enroll_code != old_code


@pytest.mark.asyncio
async def test_rotate_reactivates_a_deactivated_code(
    async_client: AsyncClient, owned_course: Course, db_session: AsyncSession
):
    await async_client.post(
        f"/api/courses/{owned_course.id}/enroll-code/deactivate"
    )
    r = await async_client.post(
        f"/api/courses/{owned_course.id}/enroll-code/rotate"
    )
    assert r.status_code == 200
    assert r.json()["data"]["enroll_code_active"] is True


# ----- deactivate -----

@pytest.mark.asyncio
async def test_deactivate_flips_active_flag(
    async_client: AsyncClient, owned_course: Course, db_session: AsyncSession
):
    r = await async_client.post(
        f"/api/courses/{owned_course.id}/enroll-code/deactivate"
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["enroll_code_active"] is False
    # code itself is preserved so a later rotate/reveal still has context
    assert data["enroll_code"] == owned_course.enroll_code

    await db_session.refresh(owned_course)
    assert owned_course.enroll_code_active is False


# ----- ownership / role guards -----

@pytest.mark.asyncio
async def test_rotate_missing_course_404(async_client: AsyncClient):
    r = await async_client.post(
        f"/api/courses/{uuid.uuid4()}/enroll-code/rotate"
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_non_owner_cannot_rotate(
    async_client: AsyncClient, db_session: AsyncSession
):
    other = User(
        better_auth_id="code_other_instr", email="codeother@ust.hk",
        full_name="Other", role="instructor",
    )
    db_session.add(other)
    await db_session.flush()
    course = Course(
        name="Foreign", language="english",
        instructor_id=other.id, enroll_code="CODEFOR1",
    )
    db_session.add(course)
    await db_session.commit()
    r = await async_client.post(
        f"/api/courses/{course.id}/enroll-code/rotate"
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_student_forbidden(db_session: AsyncSession, owned_course: Course):
    student = User(
        better_auth_id="code_student_01", email="codestudent@connect.ust.hk",
        full_name="Student", role="student",
    )
    db_session.add(student)
    await db_session.commit()

    async def override_db():
        yield db_session

    async def override_user():
        return student

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer x"},
        ) as ac:
            r = await ac.post(
                f"/api/courses/{owned_course.id}/enroll-code/deactivate"
            )
            assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()
