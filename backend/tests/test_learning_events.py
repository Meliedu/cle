"""Tests for learning-event capture (OBJ-03).

Two layers:

* Unit — ``record_attempt_event`` builds an immutable ``LearningEvent`` row
  with the right fields, never mutates the caller's ``value`` dict, and
  defaults ``occurred_at`` to "now".
* Integration — submitting a real quiz / flashcard attempt through the API
  writes a ``LearningEvent`` alongside the mastery ``Task`` (the capture is a
  best-effort side effect of the attempt handler).

No Postgres is assumed at authoring time; these are validated with
``pytest --collect-only`` + ``ruff``. They are written against the real
schema (``app.models.evidence.LearningEvent``) and the live attempt handlers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.api.deps import get_current_user
from app.main import app


@pytest.mark.asyncio
async def test_record_attempt_event_creates_row(db_session, test_student):
    """A single immutable LearningEvent is written with the given fields."""
    from app.models.course import Course
    from app.models.evidence import LearningEvent
    from app.services.learning_events import record_attempt_event

    course = Course(
        instructor_id=test_student.id,
        name="C",
        language="english",
        enroll_code="LE001",
    )
    db_session.add(course)
    await db_session.commit()

    occurred = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    await record_attempt_event(
        db_session,
        course_id=course.id,
        user_id=test_student.id,
        source_kind="quiz_attempt",
        source_id=None,
        value={"score": 42.0, "correct": 2, "total": 5},
        stage="after_class",
        occurred_at=occurred,
    )
    await db_session.commit()

    row = (
        await db_session.execute(
            select(LearningEvent).where(LearningEvent.course_id == course.id)
        )
    ).scalar_one()
    assert row.user_id == test_student.id
    assert row.source_kind == "quiz_attempt"
    assert row.source_id is None
    assert row.stage == "after_class"
    assert row.event_type == "attempt"  # default
    assert row.visibility_scope == "instructor"  # default
    assert row.value == {"score": 42.0, "correct": 2, "total": 5}
    assert row.occurred_at == occurred


@pytest.mark.asyncio
async def test_record_attempt_event_does_not_mutate_value(db_session, test_student):
    """The caller's ``value`` dict is copied, never mutated or aliased."""
    from app.models.course import Course
    from app.models.evidence import LearningEvent
    from app.services.learning_events import record_attempt_event

    course = Course(
        instructor_id=test_student.id,
        name="C",
        language="english",
        enroll_code="LE002",
    )
    db_session.add(course)
    await db_session.commit()

    original = {"quality": 1}
    snapshot = dict(original)
    await record_attempt_event(
        db_session,
        course_id=course.id,
        user_id=test_student.id,
        source_kind="flashcard",
        source_id=None,
        value=original,
        stage="review",
    )
    await db_session.commit()

    # Caller's dict is untouched.
    assert original == snapshot

    # The stored value is a distinct object (mutating the row's dict must not
    # reach back into the caller's input).
    row = (
        await db_session.execute(
            select(LearningEvent).where(LearningEvent.course_id == course.id)
        )
    ).scalar_one()
    assert row.value == snapshot
    assert row.value is not original


@pytest.mark.asyncio
async def test_record_attempt_event_defaults_occurred_at_to_now(
    db_session, test_student
):
    """Omitting ``occurred_at`` stamps the row with the current time."""
    from app.models.course import Course
    from app.models.evidence import LearningEvent
    from app.services.learning_events import record_attempt_event

    course = Course(
        instructor_id=test_student.id,
        name="C",
        language="english",
        enroll_code="LE003",
    )
    db_session.add(course)
    await db_session.commit()

    before = datetime.now(timezone.utc)
    await record_attempt_event(
        db_session,
        course_id=course.id,
        user_id=test_student.id,
        source_kind="revision",
        source_id=None,
        value={"score": 0.2},
    )
    await db_session.commit()
    after = datetime.now(timezone.utc)

    row = (
        await db_session.execute(
            select(LearningEvent).where(LearningEvent.course_id == course.id)
        )
    ).scalar_one()
    assert row.occurred_at is not None
    assert before <= row.occurred_at <= after
    assert row.stage == "review"  # default stage


@pytest.mark.asyncio
async def test_quiz_attempt_writes_learning_event(client, db_session, test_instructor):
    """Submitting a quiz attempt writes a LearningEvent(source_kind='quiz_attempt')."""
    from app.models import Concept, ConceptTag, Course, Question, Quiz
    from app.models.course import Enrollment
    from app.models.evidence import LearningEvent

    course = Course(
        instructor_id=test_instructor.id,
        name="C",
        language="english",
        enroll_code="LEQ01",
    )
    db_session.add(course)
    await db_session.commit()
    db_session.add(
        Enrollment(course_id=course.id, user_id=test_instructor.id, role="instructor")
    )
    await db_session.commit()

    quiz = Quiz(course_id=course.id, title="Q", created_by=test_instructor.id)
    db_session.add(quiz)
    await db_session.commit()
    q = Question(
        quiz_id=quiz.id,
        question_index=0,
        question_text="?",
        options={"A": "a", "B": "b"},
        correct_answer="A",
        type="multiple_choice",
        difficulty="easy",
    )
    db_session.add(q)
    await db_session.commit()
    concept = Concept(
        course_id=course.id, name="X", status="approved", instructor_curated=True
    )
    db_session.add(concept)
    await db_session.commit()
    db_session.add(
        ConceptTag(
            concept_id=concept.id,
            target_kind="question",
            target_id=q.id,
            weight=Decimal("1.00"),
        )
    )
    await db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: test_instructor
    try:
        r = await client.post(
            f"/api/quizzes/{quiz.id}/attempt",
            json={"answers": {str(q.id): "A"}},
            headers={"Authorization": "Bearer test-token"},
        )
        assert r.status_code in (200, 201), r.text
    finally:
        app.dependency_overrides.clear()

    events = (
        await db_session.execute(
            select(LearningEvent).where(LearningEvent.course_id == course.id)
        )
    ).scalars().all()
    assert len(events) == 1
    ev = events[0]
    assert ev.source_kind == "quiz_attempt"
    assert ev.user_id == test_instructor.id
    assert ev.stage == "after_class"
    assert ev.event_type == "attempt"
    # value carries the quiz score shape.
    assert float(ev.value["score"]) == 100.0
    assert ev.value["correct"] == 1
    assert ev.value["total"] == 1


@pytest.mark.asyncio
async def test_flashcard_review_writes_learning_event(
    client, db_session, test_instructor
):
    """A flashcard review writes a LearningEvent(source_kind='flashcard')."""
    from app.models import Concept, ConceptTag, Course
    from app.models.course import Enrollment
    from app.models.evidence import LearningEvent
    from app.models.flashcard import FlashcardCard, FlashcardSet

    course = Course(
        instructor_id=test_instructor.id,
        name="C",
        language="english",
        enroll_code="LEF01",
    )
    db_session.add(course)
    await db_session.commit()
    db_session.add(
        Enrollment(course_id=course.id, user_id=test_instructor.id, role="instructor")
    )
    await db_session.commit()

    fc_set = FlashcardSet(
        course_id=course.id,
        title="S",
        created_by=test_instructor.id,
        is_published=True,
    )
    db_session.add(fc_set)
    await db_session.commit()
    card = FlashcardCard(
        flashcard_set_id=fc_set.id,
        card_index=0,
        front="f",
        back="b",
        difficulty="medium",
    )
    db_session.add(card)
    await db_session.commit()
    concept = Concept(
        course_id=course.id, name="X", status="approved", instructor_curated=True
    )
    db_session.add(concept)
    await db_session.commit()
    db_session.add(
        ConceptTag(
            concept_id=concept.id,
            target_kind="flashcard_card",
            target_id=card.id,
            weight=Decimal("1.00"),
        )
    )
    await db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: test_instructor
    try:
        r = await client.put(
            f"/api/flashcard-sets/{fc_set.id}/progress",
            json={"card_id": str(card.id), "quality": 5},
            headers={"Authorization": "Bearer test-token"},
        )
        assert r.status_code in (200, 201), r.text
    finally:
        app.dependency_overrides.clear()

    events = (
        await db_session.execute(
            select(LearningEvent).where(LearningEvent.course_id == course.id)
        )
    ).scalars().all()
    assert len(events) == 1
    ev = events[0]
    assert ev.source_kind == "flashcard"
    assert ev.stage == "review"
    assert ev.value["quality"] == 5
