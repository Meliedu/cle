import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import (
    ActionOutcome,
    Course,
    EngineOverride,
    InstructorAlert,
    NextAction,
    User,
)


@pytest.mark.asyncio
async def test_next_action_persists_with_polymorphic_target(db_session, test_instructor: User):
    course = Course(
        name="Models Course",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="DECI-MOD",
    )
    db_session.add(course)
    await db_session.flush()

    row = NextAction(
        user_id=test_instructor.id,
        course_id=course.id,
        action_type="practice_weakness",
        target_kind="concept",
        target_id=uuid.uuid4(),
        priority_score=Decimal("3.250"),
        candidate_source="outer_fringe",
        reason={"weak_mastery": 0.31, "confidence": 0.72},
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        engine_variant="on",
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    assert row.id is not None
    assert row.served_at is None and row.clicked_at is None and row.consumed_at is None


@pytest.mark.asyncio
async def test_engine_override_composite_pk(db_session, test_instructor: User, test_student: User):
    course = Course(
        name="Override Course",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="DECI-OVR",
    )
    db_session.add(course)
    await db_session.flush()

    db_session.add(
        EngineOverride(
            user_id=test_student.id,
            course_id=course.id,
            mode="off",
            set_by=test_instructor.id,
        )
    )
    await db_session.commit()
    # Composite PK: same (user, course) must conflict.
    db_session.add(
        EngineOverride(
            user_id=test_student.id,
            course_id=course.id,
            mode="on",
            set_by=test_instructor.id,
        )
    )
    with pytest.raises(Exception):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_instructor_alert_open_dedupe(db_session, test_instructor: User, test_student: User):
    course = Course(
        name="Alert Course",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="DECI-ALR",
    )
    db_session.add(course)
    await db_session.flush()

    db_session.add(
        InstructorAlert(
            course_id=course.id,
            instructor_id=test_instructor.id,
            target_user_id=test_student.id,
            alert_type="student_falling_behind",
            severity="warning",
            title="Lo Yan Wai is 3 deadlines behind",
            reason={"missed": 3},
        )
    )
    await db_session.commit()

    # Second open alert for same (course, type, target) is forbidden by the
    # partial unique index.
    db_session.add(
        InstructorAlert(
            course_id=course.id,
            instructor_id=test_instructor.id,
            target_user_id=test_student.id,
            alert_type="student_falling_behind",
            severity="warning",
            title="dup",
            reason={"missed": 4},
        )
    )
    with pytest.raises(Exception):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_action_outcome_orphans_when_next_action_deleted(db_session, test_instructor: User):
    course = Course(
        name="Outcome Course",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="DECI-OUT",
    )
    db_session.add(course)
    await db_session.flush()

    na = NextAction(
        user_id=test_instructor.id,
        course_id=course.id,
        action_type="do_quiz",
        priority_score=Decimal("1.000"),
        candidate_source="fallback",
        reason={},
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        engine_variant="off",
    )
    db_session.add(na)
    await db_session.flush()

    out = ActionOutcome(
        next_action_id=na.id,
        user_id=test_instructor.id,
        course_id=course.id,
        action_type="do_quiz",
        engine_variant="off",
        served_at=datetime.now(timezone.utc),
    )
    db_session.add(out)
    await db_session.commit()

    await db_session.delete(na)
    await db_session.commit()
    await db_session.refresh(out)
    assert out.next_action_id is None  # ON DELETE SET NULL
