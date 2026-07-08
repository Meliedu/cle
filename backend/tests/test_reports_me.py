"""P7 Task B7: student report archive + delivery state.

The student-facing read side of the ``reports`` table (spec §4.9, Decision 2):

* ``GET /users/me/courses/{id}/reports`` — student, ``verify_enrollment``
  active-only (403 otherwise). Returns ONLY the caller's ``audience='student'``
  AND ``status='sent'`` reports. A ``draft`` / ``reviewed`` report is INVISIBLE —
  the student NEVER sees pre-send draft content (Core §0.2 / Decision 3). Another
  student's report and a teacher-audience row are likewise excluded.
* ``GET /users/me/reports/{id}`` — the caller's own SENT report; 404 for another
  student's report and 404 for a non-sent (draft/reviewed) own report.

Mirrors the ``test_insights_api.py`` student-read convention: the ``client``
fixture + ``app.dependency_overrides[get_current_user]`` to act as the student.
The endpoint filters on ``user_id`` explicitly (defense-in-depth on top of the
owner-isolation RLS, which the ``db_session`` superuser bypasses in tests).
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from app.api.deps import get_current_user
from app.main import app
from app.models import Course, Enrollment, User
from app.models.report import Report


async def _make_course(db_session, instructor) -> Course:
    course = Course(
        instructor_id=instructor.id,
        name="Reports Me",
        language="english",
        enroll_code=uuid.uuid4().hex[:8].upper(),
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


async def _enroll(db_session, course, student, status="active") -> None:
    db_session.add(
        Enrollment(
            course_id=course.id, user_id=student.id, role="student", status=status
        )
    )
    await db_session.commit()


async def _make_report(
    db_session,
    course,
    *,
    user_id,
    audience="student",
    status="sent",
    period="weekly",
    body=None,
) -> Report:
    now = datetime.now(timezone.utc)
    report = Report(
        course_id=course.id,
        audience=audience,
        user_id=user_id,
        period=period,
        period_start=now - timedelta(days=7),
        period_end=now,
        body=body if body is not None else {"summary": "delivered"},
        evidence_refs=[],
        status=status,
    )
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)
    return report


@pytest_asyncio.fixture
async def other_student(db_session) -> User:
    u = User(
        better_auth_id="rpt_me_other_stu",
        email="rptmeother@connect.ust.hk",
        full_name="Other Student",
        role="student",
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


_HEADERS = {"Authorization": "Bearer test-token"}


# ----- archive: /users/me/courses/{id}/reports -----


@pytest.mark.asyncio
async def test_archive_returns_only_own_sent_reports(
    client, db_session, test_instructor, test_student, other_student
):
    """Only the caller's OWN sent student-audience reports surface."""
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)

    sent = await _make_report(
        db_session, course, user_id=test_student.id, status="sent"
    )
    # Invisible: still-draft + reviewed-but-not-sent own reports (no draft leak).
    await _make_report(db_session, course, user_id=test_student.id, status="draft")
    await _make_report(
        db_session, course, user_id=test_student.id, status="reviewed"
    )
    # Invisible: another student's sent report.
    await _make_report(
        db_session, course, user_id=other_student.id, status="sent"
    )
    # Invisible: teacher-audience course-level row (user_id NULL).
    await _make_report(
        db_session, course, user_id=None, audience="teacher", status="sent"
    )

    app.dependency_overrides[get_current_user] = lambda: test_student
    try:
        r = await client.get(
            f"/api/users/me/courses/{course.id}/reports", headers=_HEADERS
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["id"] == str(sent.id)
        assert data[0]["status"] == "sent"
        assert data[0]["audience"] == "student"
        assert data[0]["user_id"] == str(test_student.id)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_archive_empty_when_nothing_sent(
    client, db_session, test_instructor, test_student
):
    """A student with only draft/reviewed reports gets an empty archive shell."""
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)
    await _make_report(db_session, course, user_id=test_student.id, status="draft")
    await _make_report(
        db_session, course, user_id=test_student.id, status="reviewed"
    )

    app.dependency_overrides[get_current_user] = lambda: test_student
    try:
        r = await client.get(
            f"/api/users/me/courses/{course.id}/reports", headers=_HEADERS
        )
        assert r.status_code == 200
        assert r.json()["data"] == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_archive_403_when_not_active_enrollment(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    # Pending (not active) enrollment must be rejected by verify_enrollment.
    await _enroll(db_session, course, test_student, status="pending")
    await _make_report(db_session, course, user_id=test_student.id, status="sent")

    app.dependency_overrides[get_current_user] = lambda: test_student
    try:
        r = await client.get(
            f"/api/users/me/courses/{course.id}/reports", headers=_HEADERS
        )
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


# ----- detail: /users/me/reports/{id} -----


@pytest.mark.asyncio
async def test_detail_returns_own_sent_report(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)
    sent = await _make_report(
        db_session, course, user_id=test_student.id, status="sent",
        body={"summary": "hello"},
    )

    app.dependency_overrides[get_current_user] = lambda: test_student
    try:
        r = await client.get(
            f"/api/users/me/reports/{sent.id}", headers=_HEADERS
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["id"] == str(sent.id)
        assert data["status"] == "sent"
        assert data["body"] == {"summary": "hello"}
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_detail_other_students_report_404(
    client, db_session, test_instructor, test_student, other_student
):
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)
    theirs = await _make_report(
        db_session, course, user_id=other_student.id, status="sent"
    )

    app.dependency_overrides[get_current_user] = lambda: test_student
    try:
        r = await client.get(
            f"/api/users/me/reports/{theirs.id}", headers=_HEADERS
        )
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_detail_non_sent_own_report_404(
    client, db_session, test_instructor, test_student
):
    """An own draft/reviewed report is NOT deliverable — 404, never draft content."""
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)
    draft = await _make_report(
        db_session, course, user_id=test_student.id, status="reviewed"
    )

    app.dependency_overrides[get_current_user] = lambda: test_student
    try:
        r = await client.get(
            f"/api/users/me/reports/{draft.id}", headers=_HEADERS
        )
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_detail_dropped_enrollment_owner_403(
    client, db_session, test_instructor, test_student
):
    """Fix 3: a non-active (rejected/dropped) owner is 403 even for their OWN
    sent report — defense-in-depth via verify_enrollment (mirrors get_signal)."""
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student, status="rejected")
    sent = await _make_report(
        db_session, course, user_id=test_student.id, status="sent"
    )

    app.dependency_overrides[get_current_user] = lambda: test_student
    try:
        r = await client.get(
            f"/api/users/me/reports/{sent.id}", headers=_HEADERS
        )
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_detail_missing_report_404(
    client, db_session, test_student
):
    app.dependency_overrides[get_current_user] = lambda: test_student
    try:
        r = await client.get(
            f"/api/users/me/reports/{uuid.uuid4()}", headers=_HEADERS
        )
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()
