"""Integration tests for mastery-update enqueue from attempt handlers.

Each attempt path (quiz / flashcard / revision) must commit a Task row of
``task_type='update_concept_mastery'`` with the correct payload after the
user's attempt is persisted. The pronunciation path is intentionally
omitted from this suite — see Task 14 report for why (PronunciationScore
rows have no item_id link, only ``target_text``).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.api.deps import get_current_user
from app.main import app


@pytest.mark.asyncio
async def test_quiz_attempt_enqueues_mastery_update(
    client, db_session, test_instructor
):
    """Submitting a quiz attempt must enqueue update_concept_mastery tasks."""
    from app.models import (
        Concept,
        ConceptTag,
        Course,
        Quiz,
        Question,
        Task,
    )
    from app.models.course import Enrollment

    course = Course(
        instructor_id=test_instructor.id,
        name="C",
        language="english",
        enroll_code="MQ001",
    )
    db_session.add(course)
    await db_session.commit()
    db_session.add(
        Enrollment(
            course_id=course.id, user_id=test_instructor.id, role="instructor"
        )
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
        course_id=course.id,
        name="X",
        status="approved",
        instructor_curated=True,
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

    tasks = (
        await db_session.execute(
            select(Task).where(Task.task_type == "update_concept_mastery")
        )
    ).scalars().all()
    assert len(tasks) >= 1
    payload = tasks[0].payload
    assert payload["target_kind"] == "question"
    assert payload["target_id"] == str(q.id)
    assert float(payload["outcome"]) == 1.0
    assert payload["attempt_kind"] == "quiz"
    assert payload["user_id"] == str(test_instructor.id)
    assert payload["course_id"] == str(course.id)


@pytest.mark.asyncio
async def test_flashcard_review_enqueues_mastery_update(
    client, db_session, test_instructor
):
    """Submitting a flashcard review must enqueue update_concept_mastery tasks."""
    from app.models import (
        Concept,
        ConceptTag,
        Course,
        Task,
    )
    from app.models.course import Enrollment
    from app.models.flashcard import FlashcardCard, FlashcardSet

    course = Course(
        instructor_id=test_instructor.id,
        name="C",
        language="english",
        enroll_code="MF001",
    )
    db_session.add(course)
    await db_session.commit()
    db_session.add(
        Enrollment(
            course_id=course.id, user_id=test_instructor.id, role="instructor"
        )
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
        course_id=course.id,
        name="X",
        status="approved",
        instructor_curated=True,
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
        # SM-2 quality=5 ("Easy") → FSRS rating=4 → mastery outcome 1.0
        r = await client.put(
            f"/api/flashcard-sets/{fc_set.id}/progress",
            json={"card_id": str(card.id), "quality": 5},
            headers={"Authorization": "Bearer test-token"},
        )
        assert r.status_code in (200, 201), r.text
    finally:
        app.dependency_overrides.clear()

    tasks = (
        await db_session.execute(
            select(Task).where(Task.task_type == "update_concept_mastery")
        )
    ).scalars().all()
    assert len(tasks) == 1
    payload = tasks[0].payload
    assert payload["target_kind"] == "flashcard_card"
    assert payload["target_id"] == str(card.id)
    assert float(payload["outcome"]) == 1.0
    assert payload["attempt_kind"] == "flashcard"


@pytest.mark.asyncio
async def test_run_update_concept_mastery_applies_evidence(
    db_session, test_instructor
):
    """Worker handler must update ConceptMastery rows from a payload."""
    from app.models import (
        Concept,
        ConceptMastery,
        ConceptTag,
        Course,
    )
    from app.services.jobs import run_update_concept_mastery

    course = Course(
        instructor_id=test_instructor.id,
        name="C",
        language="english",
        enroll_code="MJ001",
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
    target_id = uuid.uuid4()
    db_session.add(
        ConceptTag(
            concept_id=concept.id,
            target_kind="question",
            target_id=target_id,
            weight=Decimal("1.00"),
        )
    )
    await db_session.commit()

    result = await run_update_concept_mastery(
        db_session,
        {
            "user_id": str(test_instructor.id),
            "course_id": str(course.id),
            "target_kind": "question",
            "target_id": str(target_id),
            "outcome": 1.0,
            "attempt_kind": "quiz",
        },
    )
    assert result["touched_concepts"] == 1

    row = (
        await db_session.execute(
            select(ConceptMastery).where(
                ConceptMastery.user_id == test_instructor.id,
                ConceptMastery.concept_id == concept.id,
            )
        )
    ).scalar_one()
    # Initial alpha=1, +1 for correct outcome at weight 1.0
    assert float(row.alpha) == 2.0
    assert float(row.beta) == 1.0


@pytest.mark.asyncio
async def test_run_update_concept_mastery_dedupes_on_retry(db_session, test_instructor):
    """Re-running the same task must not double-count evidence."""
    from datetime import datetime, timezone
    from decimal import Decimal
    from app.models import Concept, ConceptMastery, ConceptTag, Course
    from app.services.jobs import run_update_concept_mastery

    course = Course(
        instructor_id=test_instructor.id,
        name="C", language="english", enroll_code="MD001",
    )
    db_session.add(course)
    await db_session.commit()
    concept = Concept(
        course_id=course.id, name="X",
        status="approved", instructor_curated=True,
    )
    db_session.add(concept)
    await db_session.commit()
    target_id = uuid.uuid4()
    db_session.add(
        ConceptTag(
            concept_id=concept.id, target_kind="question", target_id=target_id,
            weight=Decimal("1.00"),
        )
    )
    await db_session.commit()

    task_created_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "user_id": str(test_instructor.id),
        "course_id": str(course.id),
        "target_kind": "question",
        "target_id": str(target_id),
        "outcome": 1.0,
        "attempt_kind": "quiz",
        "_task_created_at": task_created_at,
    }
    r1 = await run_update_concept_mastery(db_session, payload)
    assert r1["touched_concepts"] == 1

    # Retry with the same task_created_at watermark — must dedupe.
    r2 = await run_update_concept_mastery(db_session, payload)
    assert r2.get("skipped") == "already_applied"

    # Mastery row should reflect ONE update (alpha = 1 + 1 = 2), not two.
    from sqlalchemy import select
    m = (
        await db_session.execute(
            select(ConceptMastery).where(
                ConceptMastery.user_id == test_instructor.id,
                ConceptMastery.concept_id == concept.id,
            )
        )
    ).scalar_one()
    assert float(m.alpha) == 2.0
    assert float(m.beta) == 1.0


@pytest.mark.asyncio
async def test_revision_attempt_enqueues_mastery_update(
    client, db_session, test_student
):
    """Submitting a revision answer must enqueue update_concept_mastery tasks."""
    from app.models import (
        Concept,
        ConceptTag,
        Course,
        Task,
    )
    from app.models.course import Enrollment
    from app.models.revision import (
        RevisionPoolItem,
        RevisionSession,
    )

    course = Course(
        instructor_id=test_student.id,
        name="C",
        language="english",
        enroll_code="MR001",
    )
    db_session.add(course)
    await db_session.commit()
    db_session.add(
        Enrollment(
            course_id=course.id, user_id=test_student.id, role="student"
        )
    )
    await db_session.commit()

    pool_item = RevisionPoolItem(
        course_id=course.id,
        content_type="quiz",
        difficulty="easy",
        question_text="2+2?",
        options={"A": "4", "B": "5"},
        correct_answer="A",
    )
    db_session.add(pool_item)
    await db_session.commit()

    session = RevisionSession(
        user_id=test_student.id,
        course_id=course.id,
        content_type="quiz",
    )
    db_session.add(session)
    await db_session.commit()

    concept = Concept(
        course_id=course.id,
        name="X",
        status="approved",
        instructor_curated=True,
    )
    db_session.add(concept)
    await db_session.commit()
    db_session.add(
        ConceptTag(
            concept_id=concept.id,
            target_kind="pool_item",
            target_id=pool_item.id,
            weight=Decimal("1.00"),
        )
    )
    await db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: test_student
    try:
        r = await client.post(
            f"/api/revision/sessions/{session.id}/answer",
            json={
                "pool_item_id": str(pool_item.id),
                "answer": "A",
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert r.status_code in (200, 201), r.text
    finally:
        app.dependency_overrides.clear()

    tasks = (
        await db_session.execute(
            select(Task).where(Task.task_type == "update_concept_mastery")
        )
    ).scalars().all()
    assert len(tasks) == 1
    payload = tasks[0].payload
    assert payload["target_kind"] == "pool_item"
    assert payload["target_id"] == str(pool_item.id)
    assert float(payload["outcome"]) == 1.0
    assert payload["attempt_kind"] == "revision"
