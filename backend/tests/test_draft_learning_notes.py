"""Tests for learning-note drafting (OBJ-04) — ``run_draft_learning_notes``.

The job scans the last 48h of ``learning_events`` for a course, picks per-user
"struggle" signals not already cited by a note, and drafts at most one
``review_status='draft'`` ``LearningNote`` per user. The LLM step is
non-raising with a deterministic template fallback.

Monkeypatch points (no network ever hit):

* Happy-path / idempotency — patch ``app.services.adaptive_jobs._llm_draft_note``
  (the smallest helper) with a deterministic async stub.
* Fallback — patch the module-level ``app.services.adaptive_jobs.AsyncOpenAI``
  so the *real* ``_llm_draft_note`` runs and its internal ``create`` call
  raises, exercising the try/except → template fallback path.

Validated with ``pytest --collect-only`` + ``ruff`` (no Postgres at authoring).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.services import adaptive_jobs


async def _seed_course_and_struggle_events(db_session, student, *, enroll_code, n=3):
    """Create a course plus ``n`` low-scoring quiz LearningEvents for ``student``.

    Returns ``(course, [event, ...])``.
    """
    from app.models.course import Course
    from app.models.evidence import LearningEvent

    course = Course(
        instructor_id=student.id,
        name="C",
        language="english",
        enroll_code=enroll_code,
    )
    db_session.add(course)
    await db_session.commit()

    now = datetime.now(timezone.utc)
    events = []
    for _ in range(n):
        ev = LearningEvent(
            course_id=course.id,
            user_id=student.id,
            source_kind="quiz_attempt",
            source_id=None,
            stage="after_class",
            event_type="attempt",
            value={"score": 20.0, "correct": 1, "total": 5},
            occurred_at=now,
        )
        db_session.add(ev)
        events.append(ev)
    await db_session.commit()
    for ev in events:
        await db_session.refresh(ev)
    return course, events


def _deterministic_draft():
    return {
        "observed_signal": "Student scored low on several recent quizzes.",
        "draft_interpretation": "May not yet grasp the material.",
        "limitation_note": "Based on quiz scores alone.",
        "suggested_follow_up": {
            "action_type": "review_with_student",
            "target_kind": None,
            "target_id": None,
        },
    }


@pytest.mark.asyncio
async def test_drafts_note_from_struggle_events(db_session, test_student, monkeypatch):
    """A struggle signal drafts exactly one draft note citing those events."""
    from app.models.evidence import LearningNote

    async def _stub(events):
        return _deterministic_draft()

    monkeypatch.setattr(adaptive_jobs, "_llm_draft_note", _stub)

    course, events = await _seed_course_and_struggle_events(
        db_session, test_student, enroll_code="DLN01"
    )

    result = await adaptive_jobs.run_draft_learning_notes(
        db_session, {"course_id": str(course.id)}
    )
    assert result["course_id"] == str(course.id)
    assert result["drafted"] == 1

    notes = (
        await db_session.execute(
            select(LearningNote).where(LearningNote.course_id == course.id)
        )
    ).scalars().all()
    assert len(notes) == 1
    note = notes[0]
    assert note.user_id == test_student.id
    assert note.review_status == "draft"
    assert note.evidence_category == "attempt_signal"
    assert note.observed_signal == _deterministic_draft()["observed_signal"]
    # Cites the seeded event ids.
    assert set(note.source_event_ids) == {str(ev.id) for ev in events}


@pytest.mark.asyncio
async def test_idempotent_does_not_redraft_cited_events(
    db_session, test_student, monkeypatch
):
    """A second run does not re-draft events already cited by a note."""
    from app.models.evidence import LearningNote

    async def _stub(events):
        return _deterministic_draft()

    monkeypatch.setattr(adaptive_jobs, "_llm_draft_note", _stub)

    course, _events = await _seed_course_and_struggle_events(
        db_session, test_student, enroll_code="DLN02"
    )

    first = await adaptive_jobs.run_draft_learning_notes(
        db_session, {"course_id": str(course.id)}
    )
    assert first["drafted"] == 1

    second = await adaptive_jobs.run_draft_learning_notes(
        db_session, {"course_id": str(course.id)}
    )
    assert second["drafted"] == 0

    notes = (
        await db_session.execute(
            select(LearningNote).where(LearningNote.course_id == course.id)
        )
    ).scalars().all()
    assert len(notes) == 1


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_template(
    db_session, test_student, monkeypatch
):
    """When the LLM call raises, a deterministic template note is still drafted."""
    from app.models.evidence import LearningNote

    class _BoomCompletions:
        async def create(self, *args, **kwargs):
            raise RuntimeError("simulated LLM outage")

    class _BoomChat:
        def __init__(self):
            self.completions = _BoomCompletions()

    class _BoomClient:
        def __init__(self, *args, **kwargs):
            self.chat = _BoomChat()

    # Patch the constructor so the real _llm_draft_note builds a client whose
    # create() raises inside its try/except → returns None → template fallback.
    monkeypatch.setattr(adaptive_jobs, "AsyncOpenAI", _BoomClient)

    course, events = await _seed_course_and_struggle_events(
        db_session, test_student, enroll_code="DLN03"
    )

    result = await adaptive_jobs.run_draft_learning_notes(
        db_session, {"course_id": str(course.id)}
    )
    assert result["drafted"] == 1

    note = (
        await db_session.execute(
            select(LearningNote).where(LearningNote.course_id == course.id)
        )
    ).scalar_one()
    assert note.review_status == "draft"
    assert note.evidence_category == "attempt_signal"
    # Template fallback signal mentions the low-scoring attempts.
    assert "low-scoring" in note.observed_signal
    assert set(note.source_event_ids) == {str(ev.id) for ev in events}
