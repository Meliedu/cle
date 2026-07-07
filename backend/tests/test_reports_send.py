"""P7 Task B6: reports.py router — send + export + evidence appendix + share.

Covers the SECURITY-SENSITIVE send/export surface over the ``reports`` table
(spec §4.9, Decision 3/4):

* ``POST /reports/{id}/send`` — refuses 409 ``REPORT_NOT_REVIEWED`` unless
  ``status='reviewed'`` AND ``evidence_refs`` non-empty; on success moves
  ``reviewed→sent``, sets ``sent_at``, appends an ``audit_events`` (``report.send``)
  row.
* ``POST /reports/{id}/export`` — same gate; appends to the report's
  ``export_history`` JSONB + an ``audit_events`` (``report.export``) row; returns
  the export payload whose evidence appendix = the resolved ``evidence_refs``
  notes filtered to ``review_status IN ('reviewed','edited')`` (an unreviewed id
  in ``evidence_refs`` is filtered OUT defensively).
* ``PATCH /reports/{id}/share-settings`` — persists export-share flags.
* non-owner → 404 on all.

Mirrors the B5 conftest fixtures (``async_client`` = instructor; ``db_session``)
and the ownership pattern from ``checkpoints.py``.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course, User
from app.models.audit_event import AuditEvent
from app.models.evidence import LearningNote
from app.models.report import Report


@pytest_asyncio.fixture
async def owned_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="Reports Send Test", language="english",
        instructor_id=logged_in_user.id, enroll_code="RPTSND01",
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


@pytest_asyncio.fixture
async def foreign_course(db_session: AsyncSession) -> Course:
    other = User(
        better_auth_id="rpt_send_other", email="rptsendother@ust.hk",
        full_name="Other", role="instructor",
    )
    db_session.add(other)
    await db_session.flush()
    course = Course(
        name="Foreign Send", language="english",
        instructor_id=other.id, enroll_code="RPTSFOR1",
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


async def _make_note(
    db_session: AsyncSession,
    course: Course,
    *,
    review_status: str,
    observed_signal: str = "signal",
    draft_interpretation: str | None = "interp",
    limitation_note: str | None = "limits apply",
    user_id=None,
) -> LearningNote:
    note = LearningNote(
        course_id=course.id,
        user_id=user_id,
        observed_signal=observed_signal,
        draft_interpretation=draft_interpretation,
        limitation_note=limitation_note,
        review_status=review_status,
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)
    return note


async def _make_report(
    db_session: AsyncSession,
    course: Course,
    *,
    audience="student",
    user_id=None,
    period="weekly",
    body=None,
    evidence_refs=None,
    status="reviewed",
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


# ----- send gate -----

@pytest.mark.asyncio
async def test_send_refuses_draft(async_client, db_session, owned_course, test_student):
    report = await _make_report(
        db_session, owned_course, user_id=test_student.id,
        status="draft", evidence_refs=[uuid.uuid4()],
    )
    r = await async_client.post(f"/api/reports/{report.id}/send")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "REPORT_NOT_REVIEWED"


@pytest.mark.asyncio
async def test_send_refuses_reviewed_without_evidence(
    async_client, db_session, owned_course, test_student
):
    report = await _make_report(
        db_session, owned_course, user_id=test_student.id,
        status="reviewed", evidence_refs=[],
    )
    r = await async_client.post(f"/api/reports/{report.id}/send")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "REPORT_NOT_REVIEWED"


@pytest.mark.asyncio
async def test_send_success_moves_reviewed_to_sent_and_audits(
    async_client, db_session, owned_course, test_student, logged_in_user
):
    note = await _make_note(db_session, owned_course, review_status="reviewed")
    report = await _make_report(
        db_session, owned_course, user_id=test_student.id,
        status="reviewed", evidence_refs=[note.id],
    )
    r = await async_client.post(f"/api/reports/{report.id}/send")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "sent"
    assert data["sent_at"] is not None

    await db_session.refresh(report)
    assert report.status == "sent"
    assert report.sent_at is not None

    events = (
        await db_session.execute(
            select(AuditEvent).where(
                AuditEvent.event_type == "report.send",
                AuditEvent.target_id == report.id,
            )
        )
    ).scalars().all()
    assert len(events) == 1
    assert events[0].target_kind == "report"
    assert events[0].course_id == owned_course.id
    assert events[0].actor_id == logged_in_user.id


@pytest.mark.asyncio
async def test_send_non_owner_404(async_client, db_session, foreign_course):
    report = await _make_report(
        db_session, foreign_course, audience="teacher",
        status="reviewed", evidence_refs=[uuid.uuid4()],
    )
    r = await async_client.post(f"/api/reports/{report.id}/send")
    assert r.status_code == 404


# ----- export -----

@pytest.mark.asyncio
async def test_export_refuses_when_not_reviewed(
    async_client, db_session, owned_course, test_student
):
    report = await _make_report(
        db_session, owned_course, user_id=test_student.id,
        status="draft", evidence_refs=[uuid.uuid4()],
    )
    r = await async_client.post(f"/api/reports/{report.id}/export")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "REPORT_NOT_REVIEWED"


@pytest.mark.asyncio
async def test_export_appendix_excludes_unreviewed_notes(
    async_client, db_session, owned_course, test_student, logged_in_user
):
    reviewed = await _make_note(db_session, owned_course, review_status="reviewed")
    edited = await _make_note(db_session, owned_course, review_status="edited")
    # An unreviewed note whose id leaked into evidence_refs — must be filtered OUT.
    unreviewed = await _make_note(db_session, owned_course, review_status="draft")
    report = await _make_report(
        db_session, owned_course, user_id=test_student.id, status="reviewed",
        evidence_refs=[reviewed.id, edited.id, unreviewed.id],
    )
    r = await async_client.post(f"/api/reports/{report.id}/export")
    assert r.status_code == 200
    data = r.json()["data"]

    appendix_ids = {item["id"] for item in data["evidence_appendix"]}
    assert appendix_ids == {str(reviewed.id), str(edited.id)}
    assert str(unreviewed.id) not in appendix_ids
    # reviewed instructor-facing fields are exposed
    reviewed_item = next(
        i for i in data["evidence_appendix"] if i["id"] == str(reviewed.id)
    )
    assert reviewed_item["observed_signal"] == "signal"
    assert reviewed_item["review_status"] in ("reviewed", "edited")

    # export_history appended + audit row written
    await db_session.refresh(report)
    assert len(report.export_history) == 1

    events = (
        await db_session.execute(
            select(AuditEvent).where(
                AuditEvent.event_type == "report.export",
                AuditEvent.target_id == report.id,
            )
        )
    ).scalars().all()
    assert len(events) == 1
    assert events[0].actor_id == logged_in_user.id


@pytest.mark.asyncio
async def test_export_appends_history_each_call(
    async_client, db_session, owned_course, test_student
):
    note = await _make_note(db_session, owned_course, review_status="reviewed")
    report = await _make_report(
        db_session, owned_course, user_id=test_student.id, status="reviewed",
        evidence_refs=[note.id],
    )
    await async_client.post(f"/api/reports/{report.id}/export")
    await async_client.post(f"/api/reports/{report.id}/export")
    await db_session.refresh(report)
    assert len(report.export_history) == 2


@pytest.mark.asyncio
async def test_export_non_owner_404(async_client, db_session, foreign_course):
    report = await _make_report(
        db_session, foreign_course, audience="teacher",
        status="reviewed", evidence_refs=[uuid.uuid4()],
    )
    r = await async_client.post(f"/api/reports/{report.id}/export")
    assert r.status_code == 404


# ----- share settings -----

@pytest.mark.asyncio
async def test_share_settings_persisted(
    async_client, db_session, owned_course, test_student
):
    report = await _make_report(
        db_session, owned_course, user_id=test_student.id, status="reviewed",
    )
    r = await async_client.patch(
        f"/api/reports/{report.id}/share-settings",
        json={"include_evidence_appendix": False, "visible_to_student": True},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["share_settings"]["include_evidence_appendix"] is False
    assert data["share_settings"]["visible_to_student"] is True

    await db_session.refresh(report)
    assert report.body["share_settings"]["visible_to_student"] is True


@pytest.mark.asyncio
async def test_share_settings_non_owner_404(
    async_client, db_session, foreign_course
):
    report = await _make_report(
        db_session, foreign_course, audience="teacher", status="reviewed",
    )
    r = await async_client.patch(
        f"/api/reports/{report.id}/share-settings",
        json={"visible_to_student": True},
    )
    assert r.status_code == 404
