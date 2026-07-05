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
async def test_concurrent_reciprocal_prereqs_dont_form_cycle(
    db_session, test_instructor
):
    """Two reciprocal edges submitted in concurrent sessions must produce
    exactly one success + one cycle rejection — never two successes that
    together form a cycle.

    Regression: the cycle check ran before any lock, so concurrent POSTs
    each saw "no cycle" and both committed.
    """
    import asyncio
    from decimal import Decimal

    from sqlalchemy import or_, select, text
    from sqlalchemy.exc import IntegrityError

    from app.api.concept_prerequisites import (
        _CYCLE_CHECK_SQL,
        _course_graph_lock_key,
    )
    from app.models import Concept, ConceptPrerequisite, Course
    from tests.conftest import test_session_factory

    course = Course(
        instructor_id=test_instructor.id,
        name="Race",
        language="english",
        enroll_code="C0099",
    )
    db_session.add(course)
    await db_session.commit()
    a = Concept(course_id=course.id, name="A", status="approved", instructor_curated=True)
    b = Concept(course_id=course.id, name="B", status="approved", instructor_curated=True)
    db_session.add_all([a, b])
    await db_session.commit()
    a_id, b_id, course_id = a.id, b.id, course.id
    lock_key = _course_graph_lock_key(course_id)

    async def try_add_edge(prereq_id, dependent_id) -> str:
        async with test_session_factory() as s:
            await s.execute(
                text("SELECT pg_advisory_xact_lock(:k)"), {"k": lock_key}
            )
            cycle = (
                await s.execute(
                    _CYCLE_CHECK_SQL,
                    {"new_dependent": dependent_id, "new_prereq": prereq_id},
                )
            ).first()
            if cycle is not None:
                return "cycle"
            s.add(
                ConceptPrerequisite(
                    prereq_concept_id=prereq_id,
                    dependent_concept_id=dependent_id,
                    strength=Decimal("1.0"),
                    instructor_verified=True,
                )
            )
            try:
                await s.commit()
                return "inserted"
            except IntegrityError:
                await s.rollback()
                return "duplicate"

    results = await asyncio.gather(
        try_add_edge(a_id, b_id),
        try_add_edge(b_id, a_id),
    )
    assert sorted(results) == ["cycle", "inserted"]

    await db_session.rollback()
    rows = (
        await db_session.execute(
            select(ConceptPrerequisite).where(
                or_(
                    ConceptPrerequisite.prereq_concept_id == a_id,
                    ConceptPrerequisite.prereq_concept_id == b_id,
                )
            )
        )
    ).scalars().all()
    assert len(rows) == 1


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


@pytest.mark.asyncio
async def test_list_prerequisites_excludes_edge_with_merged_prereq(
    client, db_session, test_instructor
):
    """An edge whose prereq side becomes merged must NOT be returned."""
    from app.models import Concept, ConceptPrerequisite, Course
    course = Course(
        instructor_id=test_instructor.id,
        name="C", language="english", enroll_code="C0060",
    )
    db_session.add(course)
    await db_session.commit()

    # Create two valid concepts and link them as prereq → dependent.
    prereq = Concept(
        course_id=course.id, name="Prereq",
        status="approved", instructor_curated=True,
    )
    dependent = Concept(
        course_id=course.id, name="Dependent",
        status="approved", instructor_curated=True,
    )
    # An unrelated, fully-valid edge that should still be returned.
    other_prereq = Concept(
        course_id=course.id, name="OtherPrereq",
        status="approved", instructor_curated=True,
    )
    other_dep = Concept(
        course_id=course.id, name="OtherDep",
        status="approved", instructor_curated=True,
    )
    db_session.add_all([prereq, dependent, other_prereq, other_dep])
    await db_session.commit()

    db_session.add(
        ConceptPrerequisite(
            prereq_concept_id=prereq.id,
            dependent_concept_id=dependent.id,
            instructor_verified=True,
        )
    )
    db_session.add(
        ConceptPrerequisite(
            prereq_concept_id=other_prereq.id,
            dependent_concept_id=other_dep.id,
            instructor_verified=True,
        )
    )
    await db_session.commit()

    # Now mark the prereq side as merged into a canonical.
    canonical = Concept(
        course_id=course.id, name="Canonical",
        status="approved", instructor_curated=True,
    )
    db_session.add(canonical)
    await db_session.commit()
    prereq.canonical_id = canonical.id
    prereq.status = "merged"
    await db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: test_instructor
    try:
        r = await client.get(
            f"/api/courses/{course.id}/concept-prerequisites",
            headers={"Authorization": "Bearer test-token"},
        )
        assert r.status_code == 200
        rows = r.json()["data"]
        prereq_ids = {row["prereq_concept_id"] for row in rows}
        # The edge whose prereq side is merged must be filtered out.
        assert str(prereq.id) not in prereq_ids
        # Unrelated valid edge still present.
        assert str(other_prereq.id) in prereq_ids
    finally:
        app.dependency_overrides.clear()
