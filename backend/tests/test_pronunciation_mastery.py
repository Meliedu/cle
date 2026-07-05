"""Pronunciation -> concept mastery wiring.

Closes the Phase 2 seam where pronunciation attempts had no FK link to
``pronunciation_items`` and so could not feed ``update_concept_mastery``.
The grade endpoint now persists ``pronunciation_item_id`` on the score row
and (when present) enqueues a Beta-Binomial update task with
``target_kind='pronunciation_item'``.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.api.speech import _enqueue_mastery_for_pronunciation


def _payload(task) -> dict:
    return task.payload


@pytest.mark.asyncio
async def test_enqueue_mastery_for_pronunciation_writes_task(db_session):
    """Helper writes one Task row with the canonical payload shape."""
    from app.models import Task

    user_id = uuid.uuid4()
    course_id = uuid.uuid4()
    item_id = uuid.uuid4()

    _enqueue_mastery_for_pronunciation(
        db_session,
        user_id=user_id,
        course_id=course_id,
        pronunciation_item_id=item_id,
        overall_score=87.5,
    )
    await db_session.commit()

    tasks = (
        await db_session.execute(
            select(Task).where(Task.task_type == "update_concept_mastery")
        )
    ).scalars().all()
    assert len(tasks) == 1
    p = _payload(tasks[0])
    assert p["user_id"] == str(user_id)
    assert p["course_id"] == str(course_id)
    assert p["target_kind"] == "pronunciation_item"
    assert p["target_id"] == str(item_id)
    assert p["attempt_kind"] == "pronunciation"
    # 87.5 / 100 = 0.875
    assert p["outcome"] == pytest.approx(0.875)
    assert tasks[0].status == "pending"


@pytest.mark.asyncio
async def test_enqueue_mastery_clamps_outcome_to_unit_interval(db_session):
    """Out-of-range overall_score values must clamp to [0, 1]."""
    from app.models import Task

    _enqueue_mastery_for_pronunciation(
        db_session,
        user_id=uuid.uuid4(),
        course_id=uuid.uuid4(),
        pronunciation_item_id=uuid.uuid4(),
        overall_score=150.0,
    )
    _enqueue_mastery_for_pronunciation(
        db_session,
        user_id=uuid.uuid4(),
        course_id=uuid.uuid4(),
        pronunciation_item_id=uuid.uuid4(),
        overall_score=-5.0,
    )
    await db_session.commit()

    tasks = (
        await db_session.execute(
            select(Task).where(Task.task_type == "update_concept_mastery")
        )
    ).scalars().all()
    outcomes = sorted(_payload(t)["outcome"] for t in tasks)
    assert outcomes == [0.0, 1.0]


@pytest.mark.asyncio
async def test_pronunciation_score_persists_item_fk(db_session, test_instructor):
    """The model column accepts a pronunciation_item_id and round-trips it."""
    from app.models import PronunciationItem, PronunciationScore, PronunciationSet
    from app.models.course import Course, Enrollment

    course = Course(
        instructor_id=test_instructor.id,
        name="C",
        language="english",
        enroll_code="MP001",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=test_instructor.id, role="instructor")
    )

    pron_set = PronunciationSet(
        course_id=course.id,
        created_by=test_instructor.id,
        title="Set",
        is_published=True,
        difficulty="medium",
        language="english",
    )
    db_session.add(pron_set)
    await db_session.flush()
    item = PronunciationItem(
        pronunciation_set_id=pron_set.id,
        item_index=0,
        text="hello",
        item_type="word",
        difficulty="medium",
    )
    db_session.add(item)
    await db_session.flush()

    score = PronunciationScore(
        user_id=test_instructor.id,
        course_id=course.id,
        pronunciation_item_id=item.id,
        language="english",
        target_text="hello",
        overall_score=Decimal("90.00"),
    )
    db_session.add(score)
    await db_session.commit()
    await db_session.refresh(score)

    assert score.pronunciation_item_id == item.id
