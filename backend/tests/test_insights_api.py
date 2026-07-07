"""B4 — insights router + student learning profile (pure-read reshape).

The learning profile RESHAPES the caller's ``concept_mastery`` rows using the
SAME thresholds ``api/mastery.py::cohort_mastery`` applies (weak = mastery_score
< 0.5 among rows with confidence >= 0.5). It recomputes NOTHING.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.api.deps import get_current_user
from app.main import app
from app.pilot import get_pilot_profile


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


async def _enroll(db_session, course, student, status="active"):
    from app.models import Enrollment
    db_session.add(
        Enrollment(
            course_id=course.id, user_id=student.id, role="student", status=status
        )
    )
    await db_session.commit()


async def _add_mastery(db_session, course, student, concept_name, alpha, beta, confidence):
    from app.models import Concept, ConceptMastery
    c = Concept(
        course_id=course.id, name=concept_name,
        status="approved", instructor_curated=True,
    )
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    now = datetime.now(timezone.utc)
    db_session.add(
        ConceptMastery(
            user_id=student.id, concept_id=c.id, course_id=course.id,
            alpha=Decimal(alpha), beta=Decimal(beta),
            confidence=Decimal(confidence), attempt_count=5,
            last_attempt_at=now, last_decay_at=now, updated_at=now,
        )
    )
    await db_session.commit()
    return c


@pytest.mark.asyncio
async def test_learning_profile_groups_by_mastery_thresholds(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)
    # Strong: confidence >= 0.5, mastery 0.8 >= 0.5
    await _add_mastery(db_session, course, test_student, "Strong", "4.000", "1.000", "0.600")
    # Weak: confidence >= 0.5, mastery 0.2 < 0.5  (mirrors cohort_mastery weak def)
    await _add_mastery(db_session, course, test_student, "Weak", "1.000", "4.000", "0.600")
    # Developing: confidence < 0.5 (not enough evidence yet)
    await _add_mastery(db_session, course, test_student, "Developing", "2.000", "2.000", "0.200")

    app.dependency_overrides[get_current_user] = lambda: test_student
    headers = {"Authorization": "Bearer test-token"}
    try:
        r = await client.get(
            f"/api/users/me/courses/{course.id}/insights", headers=headers
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["has_evidence"] is True
        assert data["concept_count"] == 3
        assert [e["concept_name"] for e in data["groups"]["strong"]] == ["Strong"]
        assert [e["concept_name"] for e in data["groups"]["weak"]] == ["Weak"]
        assert [e["concept_name"] for e in data["groups"]["developing"]] == ["Developing"]
        # Disclaimer returned verbatim from the pilot claim_limits.
        assert (
            data["disclaimer"]
            == get_pilot_profile().claim_limits["learning_profile"]
        )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_learning_profile_empty_state_no_evidence(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)

    app.dependency_overrides[get_current_user] = lambda: test_student
    headers = {"Authorization": "Bearer test-token"}
    try:
        r = await client.get(
            f"/api/users/me/courses/{course.id}/insights", headers=headers
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["has_evidence"] is False
        assert data["concept_count"] == 0
        assert data["groups"]["strong"] == []
        assert data["groups"]["developing"] == []
        assert data["groups"]["weak"] == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_learning_profile_403_when_not_active_enrollment(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    # Pending (not active) enrollment must be rejected by verify_enrollment.
    await _enroll(db_session, course, test_student, status="pending")

    app.dependency_overrides[get_current_user] = lambda: test_student
    headers = {"Authorization": "Bearer test-token"}
    try:
        r = await client.get(
            f"/api/users/me/courses/{course.id}/insights", headers=headers
        )
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_learning_profile_reads_same_rows_as_mastery_endpoint(
    client, db_session, test_instructor, test_student
):
    """The profile reshapes the EXACT rows the mastery endpoint returns."""
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)
    await _add_mastery(db_session, course, test_student, "A", "4.000", "1.000", "0.600")
    await _add_mastery(db_session, course, test_student, "B", "1.000", "4.000", "0.600")

    app.dependency_overrides[get_current_user] = lambda: test_student
    headers = {"Authorization": "Bearer test-token"}
    try:
        mastery = await client.get(
            f"/api/users/me/courses/{course.id}/mastery", headers=headers
        )
        insights = await client.get(
            f"/api/users/me/courses/{course.id}/insights", headers=headers
        )
        assert mastery.status_code == 200
        assert insights.status_code == 200
        mastery_ids = {row["concept_id"] for row in mastery.json()["data"]}
        groups = insights.json()["data"]["groups"]
        insight_ids = {
            e["concept_id"]
            for grp in ("strong", "developing", "weak")
            for e in groups[grp]
        }
        assert insight_ids == mastery_ids
    finally:
        app.dependency_overrides.clear()
