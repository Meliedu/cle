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


@pytest.mark.asyncio
async def test_replay_endpoint_rejects_when_inflight(
    client, db_session, test_instructor
):
    """A second /replay POST while a previous Task is pending must return 409.

    The replay handler is *not* watermark-idempotent: each Task fully
    re-applies the last N days of evidence. If two pending Tasks were
    enqueued (e.g. instructor double-clicks the button) they would each
    re-apply the window, doubling the priors. The endpoint guards against
    this by checking for an in-flight Task before enqueuing.
    """
    from app.api.deps import get_current_user
    from app.main import app
    from app.models import Course
    from app.models.task import Task as TaskModel

    course = Course(
        instructor_id=test_instructor.id,
        name="C",
        language="english",
        enroll_code="RP010",
    )
    db_session.add(course)
    await db_session.commit()

    # Pre-seed an in-flight replay Task for this course.
    db_session.add(
        TaskModel(
            task_type="replay_attempt_history",
            payload={"course_id": str(course.id), "window_days": 90},
            status="pending",
        )
    )
    await db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: test_instructor
    try:
        r = await client.post(
            f"/api/courses/{course.id}/concepts/replay",
            headers={"Authorization": "Bearer test-token"},
        )
        assert r.status_code == 409
        assert "in progress" in r.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()
