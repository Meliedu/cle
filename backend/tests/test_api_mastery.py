import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.api.deps import get_current_user
from app.main import app


@pytest.mark.asyncio
async def test_student_self_mastery_lists_only_own_rows(
    client, db_session, test_instructor, test_student
):
    from app.models import Concept, ConceptMastery, Course, Enrollment
    course = Course(
        instructor_id=test_instructor.id,
        name="C", language="english", enroll_code="MM001",
    )
    db_session.add(course)
    await db_session.commit()
    db_session.add(
        Enrollment(course_id=course.id, user_id=test_student.id, role="student")
    )
    await db_session.commit()
    c1 = Concept(course_id=course.id, name="A", status="approved", instructor_curated=True)
    c2 = Concept(course_id=course.id, name="B", status="approved", instructor_curated=True)
    db_session.add_all([c1, c2])
    await db_session.commit()
    now = datetime.now(timezone.utc)
    # Student row
    db_session.add(
        ConceptMastery(
            user_id=test_student.id, concept_id=c1.id, course_id=course.id,
            alpha=Decimal("4.000"), beta=Decimal("2.000"),
            confidence=Decimal("0.500"), attempt_count=5,
            last_decay_at=now, updated_at=now,
        )
    )
    # Other student's row — should NOT show in self view.
    db_session.add(
        ConceptMastery(
            user_id=test_instructor.id, concept_id=c2.id, course_id=course.id,
            alpha=Decimal("1.000"), beta=Decimal("1.000"),
            confidence=Decimal("0.000"), attempt_count=0,
            last_decay_at=now, updated_at=now,
        )
    )
    await db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: test_student
    headers = {"Authorization": "Bearer test-token"}
    try:
        r = await client.get(
            f"/api/users/me/courses/{course.id}/mastery", headers=headers
        )
        assert r.status_code == 200
        rows = r.json()["data"]
        assert len(rows) == 1
        assert rows[0]["concept_name"] == "A"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_instructor_cohort_view(client, db_session, test_instructor, test_student):
    from app.models import Concept, ConceptMastery, Course, Enrollment
    course = Course(
        instructor_id=test_instructor.id,
        name="C", language="english", enroll_code="MM002",
    )
    db_session.add(course)
    await db_session.commit()
    db_session.add(
        Enrollment(course_id=course.id, user_id=test_student.id, role="student")
    )
    await db_session.commit()
    c1 = Concept(course_id=course.id, name="A", status="approved", instructor_curated=True)
    db_session.add(c1)
    await db_session.commit()
    now = datetime.now(timezone.utc)
    db_session.add(
        ConceptMastery(
            user_id=test_student.id, concept_id=c1.id, course_id=course.id,
            alpha=Decimal("2.000"), beta=Decimal("4.000"),
            confidence=Decimal("0.600"), attempt_count=5,
            last_decay_at=now, updated_at=now,
        )
    )
    await db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: test_instructor
    headers = {"Authorization": "Bearer test-token"}
    try:
        r = await client.get(f"/api/courses/{course.id}/mastery", headers=headers)
        assert r.status_code == 200
        rows = r.json()["data"]
        assert len(rows) == 1
        assert rows[0]["concept_name"] == "A"
        assert rows[0]["weak_students"] == 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_student_self_mastery_excludes_merged_concepts(
    client, db_session, test_instructor, test_student
):
    """Mastery rows for concepts merged into a canonical must NOT appear."""
    from app.models import Concept, ConceptMastery, Course, Enrollment
    course = Course(
        instructor_id=test_instructor.id,
        name="C", language="english", enroll_code="MM003",
    )
    db_session.add(course)
    await db_session.commit()
    db_session.add(
        Enrollment(course_id=course.id, user_id=test_student.id, role="student")
    )
    await db_session.commit()

    canonical = Concept(
        course_id=course.id, name="Canonical",
        status="approved", instructor_curated=True,
    )
    merged = Concept(
        course_id=course.id, name="Old Variant",
        status="merged", instructor_curated=False,
    )
    db_session.add_all([canonical, merged])
    await db_session.commit()
    merged.canonical_id = canonical.id
    await db_session.commit()

    now = datetime.now(timezone.utc)
    # Stale mastery row from before the merge — should be filtered out.
    db_session.add(
        ConceptMastery(
            user_id=test_student.id, concept_id=merged.id, course_id=course.id,
            alpha=Decimal("3.000"), beta=Decimal("2.000"),
            confidence=Decimal("0.400"), attempt_count=4,
            last_decay_at=now, updated_at=now,
        )
    )
    # Live mastery row on the canonical concept — must be returned.
    db_session.add(
        ConceptMastery(
            user_id=test_student.id, concept_id=canonical.id, course_id=course.id,
            alpha=Decimal("4.000"), beta=Decimal("1.000"),
            confidence=Decimal("0.700"), attempt_count=5,
            last_decay_at=now, updated_at=now,
        )
    )
    await db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: test_student
    headers = {"Authorization": "Bearer test-token"}
    try:
        r = await client.get(
            f"/api/users/me/courses/{course.id}/mastery", headers=headers
        )
        assert r.status_code == 200
        rows = r.json()["data"]
        concept_ids = {row["concept_id"] for row in rows}
        assert str(merged.id) not in concept_ids
        assert str(canonical.id) in concept_ids
        assert len(rows) == 1
    finally:
        app.dependency_overrides.clear()
