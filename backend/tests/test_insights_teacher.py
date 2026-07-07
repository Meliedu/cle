"""B8 — teacher course insights + effectiveness tracker (pure-read reshape).

``GET /courses/{id}/insights`` reshapes existing rows into a single payload:
cohort mastery summary (the ``cohort_mastery`` shape), open ``instructor_alerts``
counts by severity, and review-queue depth (open alerts / ``draft``+``queued``
notes). It recomputes NOTHING — the alert counts EQUAL
``GET /courses/{id}/alerts?status=open`` (Decision 1).

``GET /courses/{id}/effectiveness`` reshapes ``outcome_checks`` grouped by
``status`` and by follow-up ``action_type`` for the owned course (Decision 9).

Both are ``get_owned_course``-guarded: a non-owner gets 404.
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


async def _add_alert(db_session, course, instructor, severity, *, dedupe_key):
    from app.models import InstructorAlert
    a = InstructorAlert(
        course_id=course.id,
        instructor_id=instructor.id,
        alert_type="cohort_concept_weakness",
        severity=severity,
        title=f"{severity} alert",
        reason={"why": severity},
        dedupe_key=dedupe_key,
        status="open",
    )
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    return a


async def _add_note(db_session, course, user_id, review_status):
    from app.models import LearningNote
    n = LearningNote(
        course_id=course.id,
        user_id=user_id,
        observed_signal="signal",
        review_status=review_status,
    )
    db_session.add(n)
    await db_session.commit()
    await db_session.refresh(n)
    return n


async def _add_follow_up(db_session, course, student, action_type):
    from app.models import FollowUpAction
    f = FollowUpAction(
        course_id=course.id,
        user_id=student.id,
        action_type=action_type,
        assignment_status="assigned",
    )
    db_session.add(f)
    await db_session.commit()
    await db_session.refresh(f)
    return f


async def _add_outcome(db_session, course, student, status, *, follow_up=None):
    from app.models import OutcomeCheck
    o = OutcomeCheck(
        course_id=course.id,
        user_id=student.id,
        follow_up_action_id=follow_up.id if follow_up is not None else None,
        status=status,
    )
    db_session.add(o)
    await db_session.commit()
    await db_session.refresh(o)
    return o


def _headers():
    return {"Authorization": "Bearer test-token"}


# ---------------------------------------------------------------------------
# GET /courses/{id}/insights
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_course_insights_reshapes_cohort_alerts_and_queue(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)

    # Cohort mastery: one weak (confident) row + one strong (confident) row.
    weak = await _add_concept(db_session, course, "Weak")
    strong = await _add_concept(db_session, course, "Strong")
    await _add_mastery(db_session, course, test_student, weak, "1.000", "4.000", "0.600")
    await _add_mastery(db_session, course, test_student, strong, "4.000", "1.000", "0.600")

    # Open alerts across severities (distinct dedupe_key to dodge the open-idempotency index).
    await _add_alert(db_session, course, test_instructor, "critical", dedupe_key="a")
    await _add_alert(db_session, course, test_instructor, "warning", dedupe_key="b")
    await _add_alert(db_session, course, test_instructor, "warning", dedupe_key="c")
    await _add_alert(db_session, course, test_instructor, "info", dedupe_key="d")

    # Review-queue notes: draft + queued count; a reviewed note does NOT.
    await _add_note(db_session, course, test_student.id, "draft")
    await _add_note(db_session, course, test_student.id, "queued")
    await _add_note(db_session, course, test_student.id, "reviewed")

    app.dependency_overrides[get_current_user] = lambda: test_instructor
    try:
        r = await client.get(f"/api/courses/{course.id}/insights", headers=_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["has_evidence"] is True

        cm = data["cohort_mastery"]
        assert cm["concept_count"] == 2
        assert cm["concepts_with_evidence"] == 2
        assert cm["weak_student_signals"] == 1
        assert cm["avg_mastery"] is not None

        # Alert counts EQUAL the alerts endpoint (recompute nothing).
        alerts = await client.get(
            f"/api/courses/{course.id}/alerts?status=open", headers=_headers()
        )
        assert alerts.status_code == 200
        open_rows = alerts.json()["data"]
        by_sev = {"info": 0, "warning": 0, "critical": 0}
        for row in open_rows:
            by_sev[row["severity"]] += 1
        assert data["alerts"]["critical"] == by_sev["critical"] == 1
        assert data["alerts"]["warning"] == by_sev["warning"] == 2
        assert data["alerts"]["info"] == by_sev["info"] == 1
        assert data["alerts"]["total"] == len(open_rows) == 4

        rq = data["review_queue"]
        assert rq["open_alerts"] == 4
        assert rq["pending_notes"] == 2   # draft + queued, not reviewed
        assert rq["total"] == 6
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_course_insights_empty_no_evidence(
    client, db_session, test_instructor
):
    course = await _make_course(db_session, test_instructor)

    app.dependency_overrides[get_current_user] = lambda: test_instructor
    try:
        r = await client.get(f"/api/courses/{course.id}/insights", headers=_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["has_evidence"] is False
        assert data["cohort_mastery"]["concepts_with_evidence"] == 0
        assert data["alerts"]["total"] == 0
        assert data["review_queue"]["total"] == 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_course_insights_404_for_non_owner(
    client, db_session, test_instructor
):
    course = await _make_course(db_session, test_instructor)
    other = await _make_user(db_session, "instructor")

    app.dependency_overrides[get_current_user] = lambda: other
    try:
        r = await client.get(f"/api/courses/{course.id}/insights", headers=_headers())
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /courses/{id}/effectiveness
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_effectiveness_grouped_by_status_and_action_type(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)

    drill = await _add_follow_up(db_session, course, test_student, "practice_drill")
    review = await _add_follow_up(db_session, course, test_student, "review_material")
    drill2 = await _add_follow_up(db_session, course, test_student, "practice_drill")

    # practice_drill: one improved, one persistent. review_material: one resolved.
    await _add_outcome(db_session, course, test_student, "improved", follow_up=drill)
    await _add_outcome(db_session, course, test_student, "persistent", follow_up=drill2)
    await _add_outcome(db_session, course, test_student, "resolved", follow_up=review)
    # An outcome with no follow-up still counts in by_status but not by_action_type.
    await _add_outcome(db_session, course, test_student, "needs_review")

    app.dependency_overrides[get_current_user] = lambda: test_instructor
    try:
        r = await client.get(
            f"/api/courses/{course.id}/effectiveness", headers=_headers()
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["has_evidence"] is True
        assert data["total"] == 4

        bs = data["by_status"]
        assert bs["improved"] == 1
        assert bs["persistent"] == 1
        assert bs["resolved"] == 1
        assert bs["needs_review"] == 1

        groups = {g["action_type"]: g for g in data["by_action_type"]}
        assert groups["practice_drill"]["total"] == 2
        assert groups["practice_drill"]["by_status"]["improved"] == 1
        assert groups["practice_drill"]["by_status"]["persistent"] == 1
        assert groups["review_material"]["total"] == 1
        assert groups["review_material"]["by_status"]["resolved"] == 1
        # The follow-up-less outcome is NOT attributed to an action_type.
        assert sum(g["total"] for g in data["by_action_type"]) == 3
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_effectiveness_empty_no_evidence(
    client, db_session, test_instructor
):
    course = await _make_course(db_session, test_instructor)

    app.dependency_overrides[get_current_user] = lambda: test_instructor
    try:
        r = await client.get(
            f"/api/courses/{course.id}/effectiveness", headers=_headers()
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["has_evidence"] is False
        assert data["total"] == 0
        assert data["by_action_type"] == []
        # Tracked statuses are still present, zeroed.
        assert data["by_status"]["improved"] == 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_effectiveness_404_for_non_owner(
    client, db_session, test_instructor
):
    course = await _make_course(db_session, test_instructor)
    other = await _make_user(db_session, "instructor")

    app.dependency_overrides[get_current_user] = lambda: other
    try:
        r = await client.get(
            f"/api/courses/{course.id}/effectiveness", headers=_headers()
        )
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()
