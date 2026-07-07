"""Model/constraint tests for ``reports`` (P7 Task B1).

``reports`` is the NEW course-scoped report table (spec §4.9, Decision 2). ONE
table serves both audiences: ``audience`` ∈ ``student|teacher``; a per-student
weekly/end-term row carries ``user_id`` (owner-isolated via RLS in the
migration), a teacher course-level row has ``user_id = NULL`` (``NULL = GUC`` is
never true → invisible to students). ``period`` ∈ ``weekly|end_term``;
``status`` ∈ ``draft|reviewed|sent|archived`` (default ``draft``).

This covers only the ORM columns, defaults, and every CHECK — exercised via
``Base.metadata.create_all`` in the disposable test DB (``db_session``), which
requires the CHECKs to be declared in ``__table_args__``. RLS is enabled in the
migration only and is asserted in B7's dedicated RLS test.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.course import Course
from app.models.report import Report


@pytest_asyncio.fixture
async def seed_course(db_session, test_instructor):
    course = Course(
        name="LANG1511",
        language="zh",
        instructor_id=test_instructor.id,
        enroll_code="RPT" + uuid.uuid4().hex[:5].upper(),
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


def _make_report(
    course,
    *,
    audience="student",
    user_id=None,
    period="weekly",
    period_start=None,
    period_end=None,
    body=None,
    evidence_refs=None,
    status=None,
):
    now = datetime.now(timezone.utc)
    kwargs = dict(
        course_id=course.id,
        audience=audience,
        user_id=user_id,
        period=period,
        period_start=period_start or (now - timedelta(days=7)),
        period_end=period_end or now,
        body=body if body is not None else {"summary": "ok"},
        evidence_refs=evidence_refs if evidence_refs is not None else [],
    )
    if status is not None:
        kwargs["status"] = status
    return Report(**kwargs)


@pytest.mark.asyncio
async def test_report_create_and_defaults(db_session, seed_course, test_student):
    report = _make_report(seed_course, user_id=test_student.id)
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)

    assert report.id is not None
    assert report.course_id == seed_course.id
    assert report.audience == "student"
    assert report.user_id == test_student.id
    assert report.period == "weekly"
    assert report.period_start is not None
    assert report.period_end is not None
    assert report.body == {"summary": "ok"}
    assert report.evidence_refs == []
    # Defaults (Decision 2).
    assert report.status == "draft"
    assert report.export_history == []
    # Nullable review/send bookkeeping starts empty.
    assert report.reviewed_by is None
    assert report.reviewed_at is None
    assert report.sent_at is None
    # TimestampMixin (no SoftDeleteMixin — a report is never soft-deleted).
    assert report.created_at is not None
    assert report.updated_at is not None


@pytest.mark.asyncio
async def test_teacher_course_level_row_has_null_user_id(
    db_session, seed_course
):
    """A teacher course-level row carries ``user_id = NULL`` (Decision 2) so the
    ``user_id = GUC`` RLS predicate is never true → students never see it."""
    report = _make_report(seed_course, audience="teacher", user_id=None)
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)
    assert report.user_id is None
    assert report.audience == "teacher"


@pytest.mark.asyncio
async def test_evidence_refs_stores_uuid_array(
    db_session, seed_course, test_student
):
    refs = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    report = _make_report(
        seed_course, user_id=test_student.id, evidence_refs=refs
    )
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)
    assert report.evidence_refs == refs


@pytest.mark.asyncio
async def test_body_and_export_history_jsonb(
    db_session, seed_course, test_student
):
    body = {
        "summary": "s",
        "completed_work": ["a"],
        "weak_points": ["b"],
        "next_actions": ["c"],
        "claim_limits": "verbatim disclaimer",
    }
    report = _make_report(seed_course, user_id=test_student.id, body=body)
    report.export_history = [{"at": "2026-07-08T00:00:00Z", "by": "x"}]
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)
    assert report.body == body
    assert report.export_history == [{"at": "2026-07-08T00:00:00Z", "by": "x"}]


@pytest.mark.asyncio
async def test_review_send_bookkeeping(db_session, seed_course, test_student, test_instructor):
    now = datetime.now(timezone.utc)
    report = _make_report(
        seed_course, user_id=test_student.id, status="sent"
    )
    report.reviewed_by = test_instructor.id
    report.reviewed_at = now
    report.sent_at = now
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)
    assert report.status == "sent"
    assert report.reviewed_by == test_instructor.id
    assert report.reviewed_at is not None
    assert report.sent_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("audience", ["student", "teacher"])
async def test_audience_accepts_valid(
    db_session, seed_course, test_student, audience
):
    uid = test_student.id if audience == "student" else None
    report = _make_report(seed_course, audience=audience, user_id=uid)
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)
    assert report.audience == audience


@pytest.mark.asyncio
async def test_bad_audience_rejected(db_session, seed_course, test_student):
    db_session.add(
        _make_report(seed_course, audience="parent", user_id=test_student.id)
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("period", ["weekly", "end_term"])
async def test_period_accepts_valid(
    db_session, seed_course, test_student, period
):
    report = _make_report(seed_course, user_id=test_student.id, period=period)
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)
    assert report.period == period


@pytest.mark.asyncio
async def test_bad_period_rejected(db_session, seed_course, test_student):
    db_session.add(
        _make_report(seed_course, user_id=test_student.id, period="daily")
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status", ["draft", "reviewed", "sent", "archived"]
)
async def test_status_accepts_valid(
    db_session, seed_course, test_student, status
):
    report = _make_report(seed_course, user_id=test_student.id, status=status)
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)
    assert report.status == status


@pytest.mark.asyncio
async def test_bad_status_rejected(db_session, seed_course, test_student):
    db_session.add(
        _make_report(seed_course, user_id=test_student.id, status="published")
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_archive_index_columns_present(db_session, seed_course, test_student):
    """Smoke: an archive-style query over (course_id, audience, period) runs
    (the supporting index is declared for these queries)."""
    db_session.add(_make_report(seed_course, user_id=test_student.id))
    await db_session.commit()
    rows = (
        await db_session.execute(
            select(Report).where(
                Report.course_id == seed_course.id,
                Report.audience == "student",
                Report.period == "weekly",
            )
        )
    ).scalars().all()
    assert len(rows) == 1
