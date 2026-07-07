"""B5 — ILO strength map (student + cohort), pure-read reshape.

The ILO map aggregates ``concept_mastery`` over the concepts tagged to each
``learning_objective`` (``concept_tags`` ``target_kind='objective'``). It
recomputes NOTHING and NEVER fabricates a 0 for an objective with no evidence —
those render ``has_evidence=false`` (Decision 7). The cohort view reuses the
``cohort_mastery`` weak definition (mastery < 0.5 among confidence >= 0.5).
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.api.deps import get_current_user
from app.main import app


async def _make_course(db_session, instructor):
    from app.models import Course
    course = Course(
        instructor_id=instructor.id,
        name="C", language="english", enroll_code=uuid.uuid4().hex[:8].upper(),
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


async def _make_user(db_session, role):
    from app.models import User
    u = User(
        better_auth_id=f"dev_{role}_{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@{'ust.hk' if role == 'instructor' else 'connect.ust.hk'}",
        full_name=f"Test {role}",
        role=role,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


async def _enroll(db_session, course, student, status="active"):
    from app.models import Enrollment
    db_session.add(
        Enrollment(
            course_id=course.id, user_id=student.id, role="student", status=status
        )
    )
    await db_session.commit()


async def _add_objective(db_session, course, statement, order_index=0):
    from app.models import LearningObjective
    o = LearningObjective(
        course_id=course.id, statement=statement, order_index=order_index,
    )
    db_session.add(o)
    await db_session.commit()
    await db_session.refresh(o)
    return o


async def _add_concept(db_session, course, name):
    from app.models import Concept
    c = Concept(
        course_id=course.id, name=name,
        status="approved", instructor_curated=True,
    )
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


async def _tag_objective(db_session, concept, objective):
    from app.models import ConceptTag
    db_session.add(
        ConceptTag(
            concept_id=concept.id, target_kind="objective", target_id=objective.id,
        )
    )
    await db_session.commit()


async def _add_mastery(db_session, course, student, concept, alpha, beta, confidence):
    from app.models import ConceptMastery
    now = datetime.now(timezone.utc)
    db_session.add(
        ConceptMastery(
            user_id=student.id, concept_id=concept.id, course_id=course.id,
            alpha=Decimal(alpha), beta=Decimal(beta),
            confidence=Decimal(confidence), attempt_count=5,
            last_attempt_at=now, last_decay_at=now, updated_at=now,
        )
    )
    await db_session.commit()


def _row_by_objective(rows, objective_id):
    return next(r for r in rows if r["objective_id"] == str(objective_id))


@pytest.mark.asyncio
async def test_student_ilo_map_aggregates_tagged_concept_mastery(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)

    o1 = await _add_objective(db_session, course, "Understand X", order_index=0)
    o2 = await _add_objective(db_session, course, "Apply Y", order_index=1)
    o3 = await _add_objective(db_session, course, "Analyze Z", order_index=2)

    ca = await _add_concept(db_session, course, "CA")
    cb = await _add_concept(db_session, course, "CB")
    cc = await _add_concept(db_session, course, "CC")

    # O1: two tagged concepts, both with caller mastery -> avg(0.8, 0.2) = 0.5
    await _tag_objective(db_session, ca, o1)
    await _tag_objective(db_session, cb, o1)
    await _add_mastery(db_session, course, test_student, ca, "4.000", "1.000", "0.600")
    await _add_mastery(db_session, course, test_student, cb, "1.000", "4.000", "0.600")

    # O2: a tagged concept but NO caller mastery -> no evidence, never a 0.
    await _tag_objective(db_session, cc, o2)

    # O3: no tagged concept at all -> no evidence.

    app.dependency_overrides[get_current_user] = lambda: test_student
    headers = {"Authorization": "Bearer test-token"}
    try:
        r = await client.get(
            f"/api/users/me/courses/{course.id}/ilo-map", headers=headers
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["has_evidence"] is True
        rows = data["objectives"]
        assert len(rows) == 3

        r1 = _row_by_objective(rows, o1.id)
        assert r1["has_evidence"] is True
        assert r1["strength"] == 0.5
        assert r1["evidence_concept_count"] == 2
        assert r1["concept_count"] == 2

        r2 = _row_by_objective(rows, o2.id)
        assert r2["has_evidence"] is False
        assert r2["strength"] is None
        assert r2["evidence_concept_count"] == 0
        assert r2["concept_count"] == 1

        r3 = _row_by_objective(rows, o3.id)
        assert r3["has_evidence"] is False
        assert r3["strength"] is None
        assert r3["concept_count"] == 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_student_ilo_map_empty_when_no_evidence(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)
    await _add_objective(db_session, course, "Understand X")

    app.dependency_overrides[get_current_user] = lambda: test_student
    headers = {"Authorization": "Bearer test-token"}
    try:
        r = await client.get(
            f"/api/users/me/courses/{course.id}/ilo-map", headers=headers
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["has_evidence"] is False
        assert len(data["objectives"]) == 1
        assert data["objectives"][0]["has_evidence"] is False
        assert data["objectives"][0]["strength"] is None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_student_ilo_map_403_when_not_active_enrollment(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student, status="pending")

    app.dependency_overrides[get_current_user] = lambda: test_student
    headers = {"Authorization": "Bearer test-token"}
    try:
        r = await client.get(
            f"/api/users/me/courses/{course.id}/ilo-map", headers=headers
        )
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_teacher_ilo_map_cohort_aggregate(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    test_student_2 = await _make_user(db_session, "student")
    await _enroll(db_session, course, test_student)
    await _enroll(db_session, course, test_student_2)

    o1 = await _add_objective(db_session, course, "Understand X", order_index=0)
    o2 = await _add_objective(db_session, course, "Apply Y", order_index=1)
    ca = await _add_concept(db_session, course, "CA")
    await _tag_objective(db_session, ca, o1)

    # student1 weak (0.2, confident), student2 strong (0.8, confident)
    await _add_mastery(db_session, course, test_student, ca, "1.000", "4.000", "0.600")
    await _add_mastery(db_session, course, test_student_2, ca, "4.000", "1.000", "0.600")

    app.dependency_overrides[get_current_user] = lambda: test_instructor
    headers = {"Authorization": "Bearer test-token"}
    try:
        r = await client.get(f"/api/courses/{course.id}/ilo-map", headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["has_evidence"] is True
        rows = data["objectives"]
        assert len(rows) == 2

        r1 = _row_by_objective(rows, o1.id)
        assert r1["has_evidence"] is True
        assert r1["avg_strength"] == 0.5
        assert r1["weak_students"] == 1
        assert r1["students_with_evidence"] == 2

        r2 = _row_by_objective(rows, o2.id)
        assert r2["has_evidence"] is False
        assert r2["avg_strength"] is None
        assert r2["weak_students"] == 0
        assert r2["students_with_evidence"] == 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_teacher_ilo_map_404_for_non_owner(
    client, db_session, test_instructor
):
    course = await _make_course(db_session, test_instructor)
    test_instructor_2 = await _make_user(db_session, "instructor")
    await _add_objective(db_session, course, "Understand X")

    app.dependency_overrides[get_current_user] = lambda: test_instructor_2
    headers = {"Authorization": "Bearer test-token"}
    try:
        r = await client.get(f"/api/courses/{course.id}/ilo-map", headers=headers)
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()
