"""P7 Task B5: reports.py router — teacher archive + detail + edit + approve.

Covers the owner-guarded teacher surface over the ``reports`` table (spec §4.9,
Decision 2/3):

* ``GET /courses/{id}/reports`` — the archive, filtered by ``audience`` /
  ``period`` / ``status`` (owner-guarded via ``get_owned_course`` → 404 non-owner).
* ``GET /reports/{id}`` — detail incl. ``evidence_refs`` (owner-guarded via the
  report's course → 404 on mismatch, no existence leak).
* ``PATCH /reports/{id}`` — edits ``body`` sections while ``status='draft'``;
  refuses editing a ``sent`` report (409 typed).
* ``POST /reports/{id}/approve`` — ``draft→reviewed``, sets ``reviewed_by`` /
  ``reviewed_at`` and appends an ``audit_events`` row (``report.approve``);
  approving a non-draft report is an illegal transition (409 typed).

Mirrors the conftest fixtures (``async_client`` = ``logged_in_user`` instructor;
``db_session``) and the ownership pattern from ``checkpoints.py``.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course, User
from app.models.audit_event import AuditEvent
from app.models.report import Report


@pytest_asyncio.fixture
async def owned_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="Reports Test", language="english",
        instructor_id=logged_in_user.id, enroll_code="RPTAPI01",
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


async def _make_report(
    db_session: AsyncSession,
    course: Course,
    *,
    audience="student",
    user_id=None,
    period="weekly",
    body=None,
    evidence_refs=None,
    status="draft",
) -> Report:
    now = datetime.now(timezone.utc)
    report = Report(
        course_id=course.id,
        audience=audience,
        user_id=user_id,
        period=period,
        period_start=now - timedelta(days=7),
        period_end=now,
        body=body if body is not None else {"summary": "ok"},
        evidence_refs=evidence_refs if evidence_refs is not None else [],
        status=status,
    )
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)
    return report


@pytest_asyncio.fixture
async def foreign_course(db_session: AsyncSession) -> Course:
    other = User(
        better_auth_id="rpt_other_instr", email="rptother@ust.hk",
        full_name="Other", role="instructor",
    )
    db_session.add(other)
    await db_session.flush()
    course = Course(
        name="Foreign", language="english",
        instructor_id=other.id, enroll_code="RPTFOR01",
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


# ----- archive -----

@pytest.mark.asyncio
async def test_archive_lists_course_reports(
    async_client, db_session, owned_course, test_student
):
    await _make_report(db_session, owned_course, user_id=test_student.id)
    await _make_report(
        db_session, owned_course, audience="teacher", user_id=None,
        period="end_term", status="reviewed",
    )
    r = await async_client.get(f"/api/courses/{owned_course.id}/reports")
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data) == 2


@pytest.mark.asyncio
async def test_archive_filters_by_audience_period_status(
    async_client, db_session, owned_course, test_student
):
    await _make_report(
        db_session, owned_course, audience="student",
        user_id=test_student.id, period="weekly", status="draft",
    )
    await _make_report(
        db_session, owned_course, audience="teacher", user_id=None,
        period="end_term", status="reviewed",
    )
    r = await async_client.get(
        f"/api/courses/{owned_course.id}/reports",
        params={"audience": "teacher", "period": "end_term", "status": "reviewed"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data) == 1
    assert data[0]["audience"] == "teacher"
    assert data[0]["period"] == "end_term"
    assert data[0]["status"] == "reviewed"


@pytest.mark.asyncio
async def test_archive_non_owner_404(async_client, foreign_course):
    r = await async_client.get(f"/api/courses/{foreign_course.id}/reports")
    assert r.status_code == 404


# ----- detail -----

@pytest.mark.asyncio
async def test_detail_returns_evidence_refs(
    async_client, db_session, owned_course, test_student
):
    refs = [uuid.uuid4(), uuid.uuid4()]
    report = await _make_report(
        db_session, owned_course, user_id=test_student.id, evidence_refs=refs,
    )
    r = await async_client.get(f"/api/reports/{report.id}")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["id"] == str(report.id)
    assert set(data["evidence_refs"]) == {str(x) for x in refs}


@pytest.mark.asyncio
async def test_detail_non_owner_404(
    async_client, db_session, foreign_course
):
    report = await _make_report(db_session, foreign_course, audience="teacher")
    r = await async_client.get(f"/api/reports/{report.id}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_detail_missing_404(async_client):
    r = await async_client.get(f"/api/reports/{uuid.uuid4()}")
    assert r.status_code == 404


# ----- edit -----

@pytest.mark.asyncio
async def test_patch_edits_body_while_draft(
    async_client, db_session, owned_course, test_student
):
    report = await _make_report(
        db_session, owned_course, user_id=test_student.id,
        body={"summary": "old"}, status="draft",
    )
    new_body = {"summary": "new", "weak_points": ["tone"]}
    r = await async_client.patch(
        f"/api/reports/{report.id}", json={"body": new_body}
    )
    assert r.status_code == 200
    assert r.json()["data"]["body"] == new_body
    await db_session.refresh(report)
    assert report.body == new_body


@pytest.mark.asyncio
async def test_patch_sent_report_409(
    async_client, db_session, owned_course, test_student
):
    report = await _make_report(
        db_session, owned_course, user_id=test_student.id, status="sent",
    )
    r = await async_client.patch(
        f"/api/reports/{report.id}", json={"body": {"summary": "x"}}
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "REPORT_NOT_EDITABLE"


@pytest.mark.asyncio
async def test_patch_non_owner_404(async_client, db_session, foreign_course):
    report = await _make_report(db_session, foreign_course, audience="teacher")
    r = await async_client.patch(
        f"/api/reports/{report.id}", json={"body": {"summary": "x"}}
    )
    assert r.status_code == 404


# ----- approve -----

@pytest.mark.asyncio
async def test_approve_draft_to_reviewed(
    async_client, db_session, owned_course, test_student, logged_in_user
):
    report = await _make_report(
        db_session, owned_course, user_id=test_student.id, status="draft",
    )
    r = await async_client.post(f"/api/reports/{report.id}/approve")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "reviewed"
    assert data["reviewed_by"] == str(logged_in_user.id)
    assert data["reviewed_at"] is not None

    await db_session.refresh(report)
    assert report.status == "reviewed"
    assert report.reviewed_by == logged_in_user.id
    assert report.reviewed_at is not None

    events = (
        await db_session.execute(
            select(AuditEvent).where(
                AuditEvent.event_type == "report.approve",
                AuditEvent.target_id == report.id,
            )
        )
    ).scalars().all()
    assert len(events) == 1
    assert events[0].target_kind == "report"
    assert events[0].course_id == owned_course.id
    assert events[0].actor_id == logged_in_user.id


@pytest.mark.asyncio
async def test_approve_sent_report_409(
    async_client, db_session, owned_course, test_student
):
    report = await _make_report(
        db_session, owned_course, user_id=test_student.id, status="sent",
    )
    r = await async_client.post(f"/api/reports/{report.id}/approve")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "REPORT_INVALID_TRANSITION"


@pytest.mark.asyncio
async def test_approve_already_reviewed_409(
    async_client, db_session, owned_course, test_student
):
    report = await _make_report(
        db_session, owned_course, user_id=test_student.id, status="reviewed",
    )
    r = await async_client.post(f"/api/reports/{report.id}/approve")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "REPORT_INVALID_TRANSITION"


@pytest.mark.asyncio
async def test_approve_non_owner_404(async_client, db_session, foreign_course):
    report = await _make_report(
        db_session, foreign_course, audience="teacher", status="draft",
    )
    r = await async_client.post(f"/api/reports/{report.id}/approve")
    assert r.status_code == 404
