"""Tests for report drafting (P7 B3) — ``run_draft_report``.

Governing constraint (Core §0.2 / Decision 1): a report NEVER draws from an
unreviewed note. ``run_draft_report`` selects ONLY ``LearningNote`` rows with
``review_status IN ('reviewed','edited')`` AND ``report_eligibility=true`` in the
course + period window, sets ``evidence_refs`` to EXACTLY those note ids, and
NEVER lets an unreviewed / ineligible note's text reach ``body``. If zero
eligible reviewed notes exist, NO ``reports`` row is created.

The LLM composition step is non-raising with a deterministic fallback (mirrors
``_llm_draft_note``). Re-running for the same ``(course, period, user)`` window
does not duplicate.

Monkeypatch points (no network ever hit):

* Happy-path / idempotency — patch ``app.services.adaptive_jobs._llm_draft_report``
  with a deterministic async stub.
* Fallback — patch module-level ``app.services.adaptive_jobs.AsyncOpenAI`` so the
  *real* ``_llm_draft_report`` runs and its ``create`` call raises, exercising
  the try/except → template fallback path.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.services import adaptive_jobs

# Distinctive markers so a leak of unreviewed content is unambiguous in asserts.
REVIEWED_SIGNAL = "REVIEWED_SIGNAL_visible_in_report"
EDITED_SIGNAL = "EDITED_SIGNAL_visible_in_report"
UNREVIEWED_SECRET = "UNREVIEWED_SECRET_must_never_leak"
INELIGIBLE_SECRET = "INELIGIBLE_SECRET_must_never_leak"


@pytest_asyncio.fixture
async def seed_course(db_session, test_instructor):
    from app.models.course import Course

    course = Course(
        name="LANG1511",
        language="zh",
        instructor_id=test_instructor.id,
        enroll_code="DRPT" + uuid.uuid4().hex[:5].upper(),
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


def _window():
    now = datetime.now(timezone.utc)
    return now - timedelta(days=7), now + timedelta(hours=1)


def _payload(course, student, period_start, period_end, *, audience="student"):
    return {
        "course_id": str(course.id),
        "audience": audience,
        "period": "weekly",
        "user_id": str(student.id) if audience == "student" else None,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
    }


async def _add_note(
    db_session,
    course,
    student,
    *,
    review_status,
    report_eligibility,
    observed_signal,
):
    from app.models.evidence import LearningNote

    note = LearningNote(
        course_id=course.id,
        user_id=student.id,
        source_event_ids=[],
        evidence_category="attempt_signal",
        observed_signal=observed_signal,
        draft_interpretation=f"{observed_signal} interpretation",
        limitation_note="scores only",
        review_status=review_status,
        report_eligibility=report_eligibility,
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)
    return note


def _deterministic_summary():
    return {"summary": "Reviewed evidence summary for the period."}


@pytest.mark.asyncio
async def test_drafts_from_reviewed_notes_only(
    db_session, seed_course, test_student, monkeypatch
):
    """evidence_refs are EXACTLY the reviewed/edited + eligible notes; an
    unreviewed or ineligible note is never referenced and its text never lands
    in ``body`` (Core §0.2)."""
    from app.models.report import Report
    from app.pilot import get_pilot_profile

    async def _stub(notes, context):
        return _deterministic_summary()

    monkeypatch.setattr(adaptive_jobs, "_llm_draft_report", _stub)

    ps, pe = _window()
    reviewed = await _add_note(
        db_session, seed_course, test_student,
        review_status="reviewed", report_eligibility=True,
        observed_signal=REVIEWED_SIGNAL,
    )
    edited = await _add_note(
        db_session, seed_course, test_student,
        review_status="edited", report_eligibility=True,
        observed_signal=EDITED_SIGNAL,
    )
    # Unreviewed draft with eligibility flag set — still excluded (status gate).
    await _add_note(
        db_session, seed_course, test_student,
        review_status="draft", report_eligibility=True,
        observed_signal=UNREVIEWED_SECRET,
    )
    # Reviewed but NOT report-eligible — excluded (eligibility gate).
    await _add_note(
        db_session, seed_course, test_student,
        review_status="reviewed", report_eligibility=False,
        observed_signal=INELIGIBLE_SECRET,
    )

    result = await adaptive_jobs.run_draft_report(
        db_session, _payload(seed_course, test_student, ps, pe)
    )
    assert result["drafted"] == 1

    report = (
        await db_session.execute(
            select(Report).where(Report.course_id == seed_course.id)
        )
    ).scalar_one()

    assert report.status == "draft"
    assert report.audience == "student"
    assert report.user_id == test_student.id
    assert report.period == "weekly"
    # EXACTLY the reviewed + edited eligible note ids.
    assert set(report.evidence_refs) == {reviewed.id, edited.id}

    body_json = json.dumps(report.body)
    # Reviewed content present.
    assert REVIEWED_SIGNAL in body_json
    assert EDITED_SIGNAL in body_json
    # Unreviewed / ineligible content NEVER leaks into the report body.
    assert UNREVIEWED_SECRET not in body_json
    assert INELIGIBLE_SECRET not in body_json
    # claim_limits is the verbatim pilot report disclaimer.
    assert report.body["claim_limits"] == get_pilot_profile().claim_limits["report"]


@pytest.mark.asyncio
async def test_no_report_when_zero_eligible_notes(
    db_session, seed_course, test_student, monkeypatch
):
    """Zero eligible reviewed notes → NO report row (Decision 1)."""
    from app.models.report import Report

    async def _stub(notes, context):
        return _deterministic_summary()

    monkeypatch.setattr(adaptive_jobs, "_llm_draft_report", _stub)

    ps, pe = _window()
    # Only an unreviewed note exists.
    await _add_note(
        db_session, seed_course, test_student,
        review_status="draft", report_eligibility=True,
        observed_signal=UNREVIEWED_SECRET,
    )

    result = await adaptive_jobs.run_draft_report(
        db_session, _payload(seed_course, test_student, ps, pe)
    )
    assert result["drafted"] == 0

    rows = (
        await db_session.execute(
            select(Report).where(Report.course_id == seed_course.id)
        )
    ).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_idempotent_does_not_duplicate(
    db_session, seed_course, test_student, monkeypatch
):
    """Re-running for the same (course, period, user) window does not duplicate."""
    from app.models.report import Report

    async def _stub(notes, context):
        return _deterministic_summary()

    monkeypatch.setattr(adaptive_jobs, "_llm_draft_report", _stub)

    ps, pe = _window()
    await _add_note(
        db_session, seed_course, test_student,
        review_status="reviewed", report_eligibility=True,
        observed_signal=REVIEWED_SIGNAL,
    )

    first = await adaptive_jobs.run_draft_report(
        db_session, _payload(seed_course, test_student, ps, pe)
    )
    assert first["drafted"] == 1

    second = await adaptive_jobs.run_draft_report(
        db_session, _payload(seed_course, test_student, ps, pe)
    )
    assert second["drafted"] == 0

    rows = (
        await db_session.execute(
            select(Report).where(Report.course_id == seed_course.id)
        )
    ).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_template(
    db_session, seed_course, test_student, monkeypatch
):
    """When the LLM call raises, a deterministic template summary is used and the
    report still drafts (never raises)."""
    from app.models.report import Report

    class _BoomCompletions:
        async def create(self, *args, **kwargs):
            raise RuntimeError("simulated LLM outage")

    class _BoomChat:
        def __init__(self):
            self.completions = _BoomCompletions()

    class _BoomClient:
        def __init__(self, *args, **kwargs):
            self.chat = _BoomChat()

    monkeypatch.setattr(adaptive_jobs, "AsyncOpenAI", _BoomClient)

    ps, pe = _window()
    await _add_note(
        db_session, seed_course, test_student,
        review_status="reviewed", report_eligibility=True,
        observed_signal=REVIEWED_SIGNAL,
    )

    result = await adaptive_jobs.run_draft_report(
        db_session, _payload(seed_course, test_student, ps, pe)
    )
    assert result["drafted"] == 1

    report = (
        await db_session.execute(
            select(Report).where(Report.course_id == seed_course.id)
        )
    ).scalar_one()
    assert report.status == "draft"
    # Fallback still produced a summary section and referenced the reviewed note.
    assert report.body.get("summary")
    assert len(report.evidence_refs) == 1
    # Reviewed content still present; disclaimer verbatim.
    assert REVIEWED_SIGNAL in json.dumps(report.body)
