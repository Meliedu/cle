import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.models import (
    ActionOutcome,
    Concept,
    ConceptMastery,
    Course,
    Enrollment,
    NextAction,
    User,
)


@pytest.mark.asyncio
async def test_list_next_actions_requires_enrollment_or_ownership(
    db_session, async_client: AsyncClient, logged_in_user: User, test_student: User
):
    course = Course(
        name="API course",
        language="en",
        instructor_id=logged_in_user.id,
        enroll_code="API-NA",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.commit()

    # logged_in_user is test_instructor by default → owner of the course → 200 + (possibly empty) list
    res = await async_client.get(f"/api/users/me/courses/{course.id}/next-actions")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True


@pytest.mark.asyncio
async def test_list_next_actions_recomputes_when_empty(
    db_session, async_client: AsyncClient, logged_in_user: User
):
    course = Course(
        name="Recompute",
        language="en",
        instructor_id=logged_in_user.id,
        enroll_code="API-RC",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    c = Concept(course_id=course.id, name="topic", status="approved")
    db_session.add(c)
    await db_session.flush()
    db_session.add(
        ConceptMastery(
            user_id=logged_in_user.id, concept_id=c.id, course_id=course.id,
            alpha=Decimal("1.000"), beta=Decimal("2.000"),
            confidence=Decimal("0.600"),
        )
    )
    await db_session.commit()

    res = await async_client.get(f"/api/users/me/courses/{course.id}/next-actions")
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body["data"], list) and len(body["data"]) >= 1


@pytest.mark.asyncio
async def test_list_next_actions_records_serve_and_observation(
    db_session, async_client: AsyncClient, logged_in_user: User
):
    course = Course(
        name="Serve obs",
        language="en",
        instructor_id=logged_in_user.id,
        enroll_code="API-SOB",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    c = Concept(course_id=course.id, name="x", status="approved")
    db_session.add(c)
    await db_session.flush()
    db_session.add(
        ConceptMastery(
            user_id=logged_in_user.id, concept_id=c.id, course_id=course.id,
            alpha=Decimal("1.000"), beta=Decimal("2.000"),
            confidence=Decimal("0.600"),
        )
    )
    await db_session.commit()

    res = await async_client.get(f"/api/users/me/courses/{course.id}/next-actions")
    assert res.status_code == 200
    await db_session.rollback()  # refresh session view (NOT expire_all)

    served = (await db_session.execute(
        __import__("sqlalchemy").select(NextAction).where(
            NextAction.user_id == logged_in_user.id, NextAction.course_id == course.id
        )
    )).scalars().all()
    assert all(r.served_at is not None for r in served)

    outcomes = (await db_session.execute(
        __import__("sqlalchemy").select(ActionOutcome).where(
            ActionOutcome.user_id == logged_in_user.id, ActionOutcome.course_id == course.id
        )
    )).scalars().all()
    assert len(outcomes) == len(served)
    assert all(o.clicked is False for o in outcomes)


@pytest.mark.asyncio
async def test_click_next_action_marks_clicked(
    db_session, async_client: AsyncClient, logged_in_user: User
):
    course = Course(
        name="Click",
        language="en",
        instructor_id=logged_in_user.id,
        enroll_code="API-CLK",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    na = NextAction(
        user_id=logged_in_user.id,
        course_id=course.id,
        action_type="practice_weakness",
        target_kind="concept",
        target_id=uuid.uuid4(),
        priority_score=Decimal("1.500"),
        candidate_source="outer_fringe",
        reason={"hi": "there"},
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        engine_variant="on",
        served_at=datetime.now(timezone.utc),
    )
    db_session.add(na)
    await db_session.commit()
    db_session.add(
        ActionOutcome(
            next_action_id=na.id,
            user_id=logged_in_user.id,
            course_id=course.id,
            action_type=na.action_type,
            target_kind=na.target_kind,
            target_id=na.target_id,
            engine_variant="on",
            served_at=na.served_at,
        )
    )
    await db_session.commit()

    res = await async_client.post(f"/api/next-actions/{na.id}/click")
    assert res.status_code == 200
    await db_session.refresh(na)
    assert na.clicked_at is not None

    refreshed_outcome = (await db_session.execute(
        __import__("sqlalchemy").select(ActionOutcome).where(
            ActionOutcome.next_action_id == na.id
        )
    )).scalar_one()
    assert refreshed_outcome.clicked is True


@pytest.mark.asyncio
async def test_click_other_users_action_404(
    db_session, async_client: AsyncClient, logged_in_user: User, test_student: User
):
    course = Course(
        name="Foreign",
        language="en",
        instructor_id=logged_in_user.id,
        enroll_code="API-FOR",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    foreign = NextAction(
        user_id=test_student.id,
        course_id=course.id,
        action_type="practice_weakness",
        target_kind="concept",
        target_id=uuid.uuid4(),
        priority_score=Decimal("1.000"),
        candidate_source="outer_fringe",
        reason={},
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        engine_variant="on",
    )
    db_session.add(foreign)
    await db_session.commit()

    res = await async_client.post(f"/api/next-actions/{foreign.id}/click")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_attempt_enqueue_is_deduped(
    db_session, async_client: AsyncClient, test_instructor: User
):
    """Two consecutive submit_attempt calls produce at most one
    materialize_next_actions task in the queue."""
    from app.models import Task

    # NOTE: the integration through quizzes/flashcards/revision is exercised
    # in their own test files. Here we only assert the helper itself dedups.
    from app.api._helpers import enqueue_next_actions_recompute

    course_id = uuid.uuid4()
    await enqueue_next_actions_recompute(
        db_session, user_id=test_instructor.id, course_id=course_id
    )
    await db_session.commit()
    await enqueue_next_actions_recompute(
        db_session, user_id=test_instructor.id, course_id=course_id
    )
    await db_session.commit()

    rows = (await db_session.execute(
        __import__("sqlalchemy").select(Task).where(
            Task.task_type == "materialize_next_actions"
        )
    )).scalars().all()
    assert len(rows) == 1
