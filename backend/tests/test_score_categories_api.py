"""Task 10: scores.py router — score-category CRUD (score-policy step, T024).

P1 subset of the spec ``scores.py``: ``GET/POST/PATCH/DELETE
/courses/{id}/score-categories``. A freshly created course already carries the
pilot's seeded default categories (Task 4); this router lets the teacher
view/edit/add/remove/reorder them. Guarded by ``get_owned_course`` (instructor +
ownership) so students get 403 and non-owners get 404.

Adapted to the real conftest fixtures (``async_client`` = ``logged_in_user``
instructor; ``db_session``). Mirrors ``test_checkpoints_api.py`` for the
non-owner / student cases.
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
from app.models.score import ScoreCategory


@pytest_asyncio.fixture
async def owned_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    """A course owned by ``logged_in_user`` pre-seeded with two categories in
    sort order (mirrors the pilot seeding done by ``create_course``)."""
    course = Course(
        name="Score Test", language="english",
        instructor_id=logged_in_user.id, enroll_code="SCORE001",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor")
    )
    db_session.add(ScoreCategory(course_id=course.id, name="Participation", sort=0))
    db_session.add(ScoreCategory(course_id=course.id, name="Quizzes", sort=1))
    await db_session.commit()
    await db_session.refresh(course)
    return course


# ----- list -----

@pytest.mark.asyncio
async def test_list_returns_seeded_categories_in_sort_order(
    async_client: AsyncClient, owned_course: Course
):
    r = await async_client.get(f"/api/courses/{owned_course.id}/score-categories")
    assert r.status_code == 200
    data = r.json()["data"]
    assert [c["name"] for c in data] == ["Participation", "Quizzes"]
    assert [c["sort"] for c in data] == [0, 1]


@pytest.mark.asyncio
async def test_freshly_created_course_returns_two_seeded_categories(
    async_client: AsyncClient,
):
    # Create a course through the real endpoint so the pilot seeding runs.
    created = await async_client.post(
        "/api/courses", json={"name": "LANG1511", "language": "zh"}
    )
    assert created.status_code == 201
    course_id = created.json()["data"]["id"]
    r = await async_client.get(f"/api/courses/{course_id}/score-categories")
    assert r.status_code == 200
    names = [c["name"] for c in r.json()["data"]]
    assert names == ["Participation", "Quizzes"]


# ----- create (append) -----

@pytest.mark.asyncio
async def test_create_appends_with_next_sort(
    async_client: AsyncClient, owned_course: Course
):
    r = await async_client.post(
        f"/api/courses/{owned_course.id}/score-categories",
        json={"name": "Final Exam", "weight": "40.00"},
    )
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["name"] == "Final Exam"
    assert data["sort"] == 2  # appended after the two seeded (0, 1)

    listed = (
        await async_client.get(f"/api/courses/{owned_course.id}/score-categories")
    ).json()["data"]
    assert [c["name"] for c in listed] == ["Participation", "Quizzes", "Final Exam"]


# ----- update -----

@pytest.mark.asyncio
async def test_update_renames_category(
    async_client: AsyncClient, owned_course: Course, db_session: AsyncSession
):
    cat = (
        await db_session.execute(
            select(ScoreCategory).where(
                ScoreCategory.course_id == owned_course.id,
                ScoreCategory.name == "Participation",
            )
        )
    ).scalar_one()
    r = await async_client.patch(
        f"/api/courses/{owned_course.id}/score-categories/{cat.id}",
        json={"name": "Class Participation", "points_pool": "10.00"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["name"] == "Class Participation"
    assert float(data["points_pool"]) == 10.0


@pytest.mark.asyncio
async def test_update_missing_category_404(
    async_client: AsyncClient, owned_course: Course
):
    r = await async_client.patch(
        f"/api/courses/{owned_course.id}/score-categories/{uuid.uuid4()}",
        json={"name": "x"},
    )
    assert r.status_code == 404


# ----- delete (soft) -----

@pytest.mark.asyncio
async def test_delete_soft_removes(
    async_client: AsyncClient, owned_course: Course, db_session: AsyncSession
):
    cat = (
        await db_session.execute(
            select(ScoreCategory).where(
                ScoreCategory.course_id == owned_course.id,
                ScoreCategory.name == "Quizzes",
            )
        )
    ).scalar_one()
    r = await async_client.delete(
        f"/api/courses/{owned_course.id}/score-categories/{cat.id}"
    )
    assert r.status_code == 200
    await db_session.refresh(cat)
    assert cat.deleted_at is not None
    # no longer listed
    listed = (
        await async_client.get(f"/api/courses/{owned_course.id}/score-categories")
    ).json()["data"]
    assert [c["name"] for c in listed] == ["Participation"]


# ----- ownership / role guards -----

@pytest.mark.asyncio
async def test_non_owner_gets_404(async_client: AsyncClient, db_session: AsyncSession):
    other = User(
        better_auth_id="score_other_instr", email="scoreother@ust.hk",
        full_name="Other", role="instructor",
    )
    db_session.add(other)
    await db_session.flush()
    course = Course(
        name="Foreign", language="english",
        instructor_id=other.id, enroll_code="SCOREFOR",
    )
    db_session.add(course)
    await db_session.commit()
    r = await async_client.get(f"/api/courses/{course.id}/score-categories")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_student_forbidden(db_session: AsyncSession, owned_course: Course):
    student = User(
        better_auth_id="score_student_01", email="scorestudent@connect.ust.hk",
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
            r = await ac.get(f"/api/courses/{owned_course.id}/score-categories")
            assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()
