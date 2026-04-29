import pytest
from app.api.deps import get_current_user
from app.main import app


@pytest.mark.asyncio
async def test_create_and_list_concept(client, db_session, test_instructor):
    from app.models import Course
    course = Course(
        instructor_id=test_instructor.id,
        name="Algorithms",
        language="english",
        enroll_code="ALG01",
    )
    db_session.add(course)
    await db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: test_instructor
    headers = {"Authorization": "Bearer test-token"}
    try:
        r = await client.post(
            f"/api/courses/{course.id}/concepts",
            json={"name": "Big-O Notation", "instructor_curated": True},
            headers=headers,
        )
        assert r.status_code == 201
        body = r.json()
        assert body["success"] is True
        assert body["data"]["name"] == "Big-O Notation"
        assert body["data"]["status"] == "approved"   # explicit instructor curation -> approved

        r = await client.get(f"/api/courses/{course.id}/concepts", headers=headers)
        assert r.status_code == 200
        assert len(r.json()["data"]) == 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_concept_cross_course_idor(client, db_session, test_instructor):
    """Instructor of course A cannot read concepts of course B."""
    from app.models import Concept, Course, User
    other = User(
        better_auth_id="dev_other_001",
        email="other@ust.hk",
        full_name="Other",
        role="instructor",
    )
    db_session.add(other)
    await db_session.commit()
    a = Course(instructor_id=test_instructor.id, name="A", language="english", enroll_code="A001")
    b = Course(instructor_id=other.id, name="B", language="english", enroll_code="B001")
    db_session.add_all([a, b])
    await db_session.commit()
    cb = Concept(course_id=b.id, name="Hidden", status="approved", instructor_curated=True)
    db_session.add(cb)
    await db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: test_instructor
    headers = {"Authorization": "Bearer test-token"}
    try:
        r = await client.get(f"/api/courses/{b.id}/concepts", headers=headers)
        assert r.status_code == 404      # get_owned_course returns 404 to mask existence
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_extract_endpoint_enqueues_task(client, db_session, test_instructor):
    from app.models import Course, Task
    from sqlalchemy import select

    course = Course(
        instructor_id=test_instructor.id,
        name="C", language="english", enroll_code="EX001",
    )
    db_session.add(course)
    await db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: test_instructor
    try:
        r = await client.post(
            f"/api/courses/{course.id}/concepts/extract",
            headers={"Authorization": "Bearer test-token"},
        )
        assert r.status_code == 200
        assert r.json()["data"]["enqueued"] is True
    finally:
        app.dependency_overrides.clear()

    tasks = (
        await db_session.execute(
            select(Task).where(Task.task_type == "extract_concept_candidates")
        )
    ).scalars().all()
    assert len(tasks) == 1
    assert tasks[0].payload["course_id"] == str(course.id)


@pytest.mark.asyncio
async def test_extract_endpoint_rejects_when_inflight(client, db_session, test_instructor):
    from app.models import Course, Task
    course = Course(
        instructor_id=test_instructor.id,
        name="C", language="english", enroll_code="EX002",
    )
    db_session.add(course)
    await db_session.commit()
    db_session.add(
        Task(
            task_type="extract_concept_candidates",
            payload={"course_id": str(course.id)},
            status="pending",
        )
    )
    await db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: test_instructor
    try:
        r = await client.post(
            f"/api/courses/{course.id}/concepts/extract",
            headers={"Authorization": "Bearer test-token"},
        )
        assert r.status_code == 409
        assert "in progress" in r.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()
