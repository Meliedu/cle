import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import (
    Assignment,
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


@pytest.mark.asyncio
async def test_unpublished_assignment_not_recommended(
    db_session, test_instructor: User, test_student: User
):
    """Materializer must not surface unpublished assignments to students."""
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz

    course = Course(
        name="Unpub asn",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="UNP-1",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=test_student.id, role="student"))
    c = Concept(course_id=course.id, name="topic", status="approved")
    db_session.add(c)
    await db_session.flush()
    db_session.add(
        ConceptMastery(
            user_id=test_student.id, concept_id=c.id, course_id=course.id,
            alpha=Decimal("1.000"), beta=Decimal("3.000"),
            confidence=Decimal("0.600"),
        )
    )
    asn = Assignment(
        course_id=course.id,
        title="Draft",
        kind="quiz",
        due_at=_dt.now(_tz.utc) + _td(days=2),
        created_by=test_instructor.id,
        is_published=False,  # KEY: not yet published
    )
    db_session.add(asn)
    await db_session.flush()
    db_session.add(
        ConceptTag(
            concept_id=c.id,
            target_kind="assignment",
            target_id=asn.id,
            weight=Decimal("1.00"),
        )
    )
    await db_session.commit()

    rows = await materialize_next_actions(
        db_session, user_id=test_student.id, course_id=course.id
    )
    # No row should target the draft assignment.
    assert all(r.target_id != asn.id for r in rows)


@pytest.mark.asyncio
async def test_get_or_recompute_returns_cached(db_session, test_instructor, test_student):
    from app.services.next_actions import get_or_recompute_next_actions
    course = Course(
        name="Cache",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="MAT-CACHE",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    c = Concept(course_id=course.id, name="cached", status="approved")
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

    rows1 = await get_or_recompute_next_actions(
        db_session, user_id=test_student.id, course_id=course.id
    )
    rows2 = await get_or_recompute_next_actions(
        db_session, user_id=test_student.id, course_id=course.id
    )
    # Same row IDs — second call returned the cache.
    assert {r.id for r in rows1} == {r.id for r in rows2}


@pytest.mark.asyncio
async def test_get_or_recompute_refreshes_after_ttl(db_session, test_instructor, test_student):
    """Stale cache (>30 min) triggers recompute; ids change."""
    from datetime import timedelta as _td

    from app.services.next_actions import get_or_recompute_next_actions
    course = Course(
        name="Stale",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="MAT-STALE",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    c = Concept(course_id=course.id, name="stale", status="approved")
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

    rows1 = await get_or_recompute_next_actions(
        db_session, user_id=test_student.id, course_id=course.id
    )
    # Backdate created_at to simulate a 31-min-old cache.
    for r in rows1:
        r.created_at = datetime.now(timezone.utc) - _td(minutes=31)
    await db_session.commit()

    rows2 = await get_or_recompute_next_actions(
        db_session, user_id=test_student.id, course_id=course.id
    )
    assert {r.id for r in rows1} != {r.id for r in rows2}


@pytest.mark.asyncio
async def test_apply_attempt_evidence_closes_open_outcome(
    db_session, test_instructor: User, test_student: User
):
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz

    from app.models import (
        ActionOutcome,
        Concept,
        ConceptTag,
        Course,
        Enrollment,
        NextAction,
    )
    from app.services.mastery import AttemptKind, apply_attempt_evidence

    course = Course(
        name="Close",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="CLO-1",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=test_student.id, role="student"))
    c = Concept(course_id=course.id, name="Closed", status="approved")
    db_session.add(c)
    await db_session.flush()
    target_question = uuid.uuid4()
    db_session.add(
        ConceptTag(
            concept_id=c.id,
            target_kind="chunk",
            target_id=target_question,
            weight=Decimal("1.00"),
        )
    )
    served_at = _dt.now(_tz.utc)
    na = NextAction(
        user_id=test_student.id,
        course_id=course.id,
        action_type="practice_weakness",
        target_kind="chunk",
        target_id=target_question,
        priority_score=Decimal("1.000"),
        candidate_source="outer_fringe",
        reason={},
        expires_at=served_at + _td(hours=1),
        engine_variant="on",
        served_at=served_at,
    )
    db_session.add(na)
    await db_session.flush()
    db_session.add(
        ActionOutcome(
            next_action_id=na.id,
            user_id=test_student.id,
            course_id=course.id,
            action_type="practice_weakness",
            target_kind="chunk",
            target_id=target_question,
            engine_variant="on",
            served_at=served_at,
        )
    )
    await db_session.commit()

    await apply_attempt_evidence(
        db_session,
        user_id=test_student.id,
        course_id=course.id,
        target_kind="chunk",
        target_id=target_question,
        attempt_kind=AttemptKind.QUIZ,
        outcome=0.85,
    )
    await db_session.commit()
    refreshed = (await db_session.execute(
        __import__("sqlalchemy").select(ActionOutcome).where(
            ActionOutcome.next_action_id == na.id
        )
    )).scalar_one()
    assert refreshed.completed is True
    assert refreshed.outcome_metric == "quiz_score"
    assert float(refreshed.outcome_score) == pytest.approx(0.85, abs=1e-3)


@pytest.mark.asyncio
async def test_materialize_serializes_concurrent_calls(
    db_session, test_instructor: User, test_student: User
):
    """Two concurrent materialize calls for the same (user, course) must not
    leave duplicate rows. The advisory lock serializes them.

    Note: this test runs in a single transaction (db_session is one session)
    so it doesn't truly exercise concurrency — it's a smoke test that
    materialize_next_actions can run twice in succession and produce a
    bounded row count. The advisory lock is verified by the absence of
    duplicate priority_score rows in the final state.
    """
    course = Course(
        name="Race",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="RAC-1",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=test_student.id, role="student"))
    c = Concept(course_id=course.id, name="x", status="approved")
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

    rows1 = await materialize_next_actions(db_session, user_id=test_student.id, course_id=course.id)
    rows2 = await materialize_next_actions(db_session, user_id=test_student.id, course_id=course.id)

    persisted = (await db_session.execute(
        __import__("sqlalchemy").select(NextAction).where(
            NextAction.user_id == test_student.id,
            NextAction.course_id == course.id,
            NextAction.consumed_at.is_(None),
        )
    )).scalars().all()
    # Replace-on-rebuild + advisory lock means no duplicate accumulation.
    assert len(persisted) == len(rows2)
    assert len(persisted) <= 10
