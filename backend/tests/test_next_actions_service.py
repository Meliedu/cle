import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import (
    Concept,
    ConceptMastery,
    ConceptTag,
    Course,
    CourseMeeting,
    Enrollment,
    NextAction,
    User,
)
from app.services.next_actions import (
    materialize_next_actions,
    record_serve,
)


@pytest.mark.asyncio
async def test_materialize_writes_rows_with_one_hour_ttl(
    db_session, test_instructor: User, test_student: User
):
    course = Course(
        name="Mat course",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="MAT-1",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=test_student.id, role="student"))

    c = Concept(course_id=course.id, name="Pivot", status="approved")
    db_session.add(c)
    await db_session.flush()
    db_session.add(
        ConceptMastery(
            user_id=test_student.id, concept_id=c.id, course_id=course.id,
            alpha=Decimal("1.000"), beta=Decimal("3.000"),
            confidence=Decimal("0.600"),
        )
    )
    await db_session.commit()

    rows = await materialize_next_actions(
        db_session, user_id=test_student.id, course_id=course.id
    )
    assert len(rows) >= 1
    persisted = (await db_session.execute(
        __import__("sqlalchemy").select(NextAction).where(
            NextAction.user_id == test_student.id, NextAction.course_id == course.id
        )
    )).scalars().all()
    assert len(persisted) == len(rows)
    for r in persisted:
        delta = r.expires_at - datetime.now(timezone.utc)
        assert timedelta(minutes=58) <= delta <= timedelta(minutes=62)
        assert r.engine_variant == "on"


@pytest.mark.asyncio
async def test_materialize_off_mode_returns_empty(
    db_session, test_instructor: User, test_student: User
):
    course = Course(
        name="Off course",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="MAT-2",
        adaptive_engine_mode="off",
    )
    db_session.add(course)
    await db_session.commit()

    rows = await materialize_next_actions(
        db_session, user_id=test_student.id, course_id=course.id
    )
    assert rows == []


@pytest.mark.asyncio
async def test_materialize_replaces_existing_unconsumed_rows(
    db_session, test_instructor: User, test_student: User
):
    course = Course(
        name="Replace",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="MAT-3",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()

    c = Concept(course_id=course.id, name="X", status="approved")
    db_session.add(c)
    await db_session.flush()
    db_session.add(
        ConceptMastery(
            user_id=test_student.id, concept_id=c.id, course_id=course.id,
            alpha=Decimal("1.000"), beta=Decimal("2.000"),
            confidence=Decimal("0.600"),
        )
    )
    await db_session.commit()

    first = await materialize_next_actions(
        db_session, user_id=test_student.id, course_id=course.id
    )
    second = await materialize_next_actions(
        db_session, user_id=test_student.id, course_id=course.id
    )
    # Same number of rows, no orphaned previous-cycle rows hanging around.
    persisted = (await db_session.execute(
        __import__("sqlalchemy").select(NextAction).where(
            NextAction.user_id == test_student.id,
            NextAction.course_id == course.id,
            NextAction.consumed_at.is_(None),
        )
    )).scalars().all()
    assert len(persisted) == len(second)


@pytest.mark.asyncio
async def test_record_serve_stamps_served_at(
    db_session, test_instructor: User, test_student: User
):
    course = Course(
        name="Serve",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="MAT-4",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    c = Concept(course_id=course.id, name="Z", status="approved")
    db_session.add(c)
    await db_session.flush()
    db_session.add(
        ConceptMastery(
            user_id=test_student.id, concept_id=c.id, course_id=course.id,
            alpha=Decimal("1.000"), beta=Decimal("2.000"),
            confidence=Decimal("0.600"),
        )
    )
    await db_session.commit()

    rows = await materialize_next_actions(
        db_session, user_id=test_student.id, course_id=course.id
    )
    assert all(r.served_at is None for r in rows)

    served = await record_serve(db_session, [r.id for r in rows])
    assert all(r.served_at is not None for r in served)
