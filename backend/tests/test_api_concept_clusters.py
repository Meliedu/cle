import pytest
import uuid

from app.api.deps import get_current_user
from app.main import app


@pytest.mark.asyncio
async def test_list_pending_clusters(client, db_session, test_instructor):
    from app.models import Concept, Course
    course = Course(
        instructor_id=test_instructor.id, name="C", language="english", enroll_code="CL001",
    )
    db_session.add(course)
    await db_session.commit()

    cluster_a = uuid.uuid4()
    cluster_b = uuid.uuid4()
    db_session.add_all([
        Concept(course_id=course.id, name="Big-O", status="pending", cluster_id=cluster_a),
        Concept(course_id=course.id, name="Big O Notation", status="pending", cluster_id=cluster_a),
        Concept(course_id=course.id, name="Hash Table", status="pending", cluster_id=cluster_b),
    ])
    await db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: test_instructor
    headers = {"Authorization": "Bearer test-token"}
    try:
        r = await client.get(
            f"/api/courses/{course.id}/concept-clusters",
            headers=headers,
        )
        assert r.status_code == 200
        clusters = r.json()["data"]
        assert len(clusters) == 2
        big_o = next(c for c in clusters if "Big" in c["suggested_name"])
        assert len(big_o["members"]) == 2
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_approve_cluster_collapses_to_canonical(client, db_session, test_instructor):
    from app.models import Concept, Course
    course = Course(
        instructor_id=test_instructor.id, name="C", language="english", enroll_code="CL002",
    )
    db_session.add(course)
    await db_session.commit()

    cluster_id = uuid.uuid4()
    a = Concept(course_id=course.id, name="Big-O", status="pending", cluster_id=cluster_id)
    b = Concept(course_id=course.id, name="Big O Notation", status="pending", cluster_id=cluster_id)
    db_session.add_all([a, b])
    await db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: test_instructor
    headers = {"Authorization": "Bearer test-token"}
    try:
        r = await client.post(
            f"/api/courses/{course.id}/concept-clusters/{cluster_id}/decide",
            json={"action": "approve", "final_name": "Big-O Notation"},
            headers=headers,
        )
        assert r.status_code == 200
        body = r.json()["data"]
        canon_id = body["canonical_concept_id"]

        # Refresh: roll back the test session's view so post-API mutations are
        # visible on subsequent reads (the API request committed via a shared
        # session, but our local refs still hold stale state).
        await db_session.rollback()
        from sqlalchemy import select
        from app.models import Concept as C
        rows = (
            await db_session.execute(
                select(C).where(C.course_id == course.id)
            )
        ).scalars().all()
        canon = next(r for r in rows if str(r.id) == canon_id)
        assert canon.status == "approved"
        assert canon.instructor_curated is True
        assert canon.cluster_id is None
        # Other members soft-merged.
        non_canon = [r for r in rows if str(r.id) != canon_id]
        assert all(m.status == "merged" for m in non_canon)
        assert all(m.canonical_id == canon.id for m in non_canon)
    finally:
        app.dependency_overrides.clear()
