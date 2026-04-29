import pytest
from app.api.deps import get_current_user
from app.main import app


@pytest.mark.asyncio
async def test_create_prerequisite_and_reject_cycle(client, db_session, test_instructor):
    from app.models import Concept, Course
    course = Course(
        instructor_id=test_instructor.id, name="C", language="english", enroll_code="C0001",
    )
    db_session.add(course)
    await db_session.commit()
    a = Concept(course_id=course.id, name="A", status="approved", instructor_curated=True)
    b = Concept(course_id=course.id, name="B", status="approved", instructor_curated=True)
    db_session.add_all([a, b])
    await db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: test_instructor
    headers = {"Authorization": "Bearer test-token"}
    try:
        # A → B (A is prereq of B)
        r = await client.post(
            f"/api/courses/{course.id}/concept-prerequisites",
            json={
                "prereq_concept_id": str(a.id),
                "dependent_concept_id": str(b.id),
                "strength": 1.0,
            },
            headers=headers,
        )
        assert r.status_code == 201

        # Now adding B → A would create cycle A → B → A.
        r = await client.post(
            f"/api/courses/{course.id}/concept-prerequisites",
            json={
                "prereq_concept_id": str(b.id),
                "dependent_concept_id": str(a.id),
            },
            headers=headers,
        )
        assert r.status_code == 409
        assert "cycle" in r.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_prerequisite_must_be_same_course(client, db_session, test_instructor):
    from app.models import Concept, Course
    a_course = Course(
        instructor_id=test_instructor.id, name="A", language="english", enroll_code="C0010",
    )
    b_course = Course(
        instructor_id=test_instructor.id, name="B", language="english", enroll_code="C0011",
    )
    db_session.add_all([a_course, b_course])
    await db_session.commit()
    a = Concept(course_id=a_course.id, name="A", status="approved", instructor_curated=True)
    b = Concept(course_id=b_course.id, name="B", status="approved", instructor_curated=True)
    db_session.add_all([a, b])
    await db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: test_instructor
    headers = {"Authorization": "Bearer test-token"}
    try:
        r = await client.post(
            f"/api/courses/{a_course.id}/concept-prerequisites",
            json={
                "prereq_concept_id": str(a.id),
                "dependent_concept_id": str(b.id),
            },
            headers=headers,
        )
        assert r.status_code == 400
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_prerequisite_rejects_merged_concept(client, db_session, test_instructor):
    """A merged concept (canonical_id != None) cannot be the endpoint of a new edge."""
    from app.models import Concept, Course
    course = Course(
        instructor_id=test_instructor.id, name="C", language="english", enroll_code="C0050",
    )
    db_session.add(course)
    await db_session.commit()
    canonical = Concept(
        course_id=course.id, name="Canonical", status="approved", instructor_curated=True,
    )
    merged = Concept(
        course_id=course.id, name="Old Variant", status="merged", instructor_curated=False,
    )
    db_session.add_all([canonical, merged])
    await db_session.commit()
    merged.canonical_id = canonical.id
    await db_session.commit()

    other = Concept(
        course_id=course.id, name="Other", status="approved", instructor_curated=True,
    )
    db_session.add(other)
    await db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: test_instructor
    try:
        # Try to make `merged` a prereq of `other` — must be rejected (400).
        r = await client.post(
            f"/api/courses/{course.id}/concept-prerequisites",
            json={
                "prereq_concept_id": str(merged.id),
                "dependent_concept_id": str(other.id),
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert r.status_code == 400
    finally:
        app.dependency_overrides.clear()
