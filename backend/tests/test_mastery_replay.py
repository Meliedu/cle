"""Tests for the 90-day attempt replay backfill job.

The replay handler walks quiz_attempts / flashcard_progress / revision_attempts
/ pronunciation_scores in the last N days for a course and re-applies each
attempt through the Beta-Binomial mastery update. Attempts older than the
window are skipped.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from app.services.jobs import run_replay_attempt_history


@pytest.mark.asyncio
async def test_replay_processes_quiz_attempts_in_window(
    db_session, test_instructor
):
    from app.models import (
        Concept,
        ConceptMastery,
        ConceptTag,
        Course,
        Question,
        Quiz,
        QuizAttempt,
    )

    course = Course(
        instructor_id=test_instructor.id,
        name="C",
        language="english",
        enroll_code="RP001",
    )
    db_session.add(course)
    await db_session.commit()

    concept = Concept(
        course_id=course.id,
        name="X",
        status="approved",
        instructor_curated=True,
    )
    db_session.add(concept)
    await db_session.commit()

    quiz = Quiz(course_id=course.id, title="Q", created_by=test_instructor.id)
    db_session.add(quiz)
    await db_session.commit()
    q = Question(
        quiz_id=quiz.id,
        question_index=0,
        question_text="?",
        options={"A": "a"},
        correct_answer="A",
        type="multiple_choice",
        difficulty="easy",
    )
    db_session.add(q)
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

    inside = QuizAttempt(
        quiz_id=quiz.id,
        user_id=test_instructor.id,
        answers={str(q.id): "A"},
    )
    too_old = QuizAttempt(
        quiz_id=quiz.id,
        user_id=test_instructor.id,
        answers={str(q.id): "A"},
    )
    db_session.add_all([inside, too_old])
    await db_session.flush()

    # ``created_at`` has server_default=func.now(); explicit Python attribute
    # writes get overwritten on commit. Force the values via UPDATE so the
    # window filter actually rejects ``too_old``.
    inside_at = datetime.now(timezone.utc) - timedelta(days=10)
    too_old_at = datetime.now(timezone.utc) - timedelta(days=120)
    await db_session.execute(
        update(QuizAttempt)
        .where(QuizAttempt.id == inside.id)
        .values(created_at=inside_at)
    )
    await db_session.execute(
        update(QuizAttempt)
        .where(QuizAttempt.id == too_old.id)
        .values(created_at=too_old_at)
    )
    await db_session.commit()

    await run_replay_attempt_history(
        db_session,
        {"course_id": str(course.id), "window_days": 90},
    )
    await db_session.commit()

    rows = (
        await db_session.execute(
            select(ConceptMastery).where(ConceptMastery.concept_id == concept.id)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].attempt_count == 1
    assert float(rows[0].alpha) > 1.0
