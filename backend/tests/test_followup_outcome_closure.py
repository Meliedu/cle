"""Outcome-Check closure (CLE §5.5).

A later attempt that touches the same target — or one of its tagged concepts —
closes the open ``FollowUpAction``, writes exactly one ``OutcomeCheck``, and
(only when the linked ``LearningNote`` is instructor-reviewed) promotes the
result into durable course memory via a ``CourseRecordItem``.
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import (
    Concept,
    ConceptTag,
    Course,
    CourseRecordItem,
    FollowUpAction,
    LearningNote,
    OutcomeCheck,
    User,
)
from app.services.mastery import AttemptKind, apply_attempt_evidence


async def _build_scenario(
    db_session,
    instructor: User,
    *,
    note_status: str = "reviewed",
):
    """Course + student + concept + pool_item tag + note + open follow-up.

    Returns ``(course, student, concept, target_id, note, fua)``.
    """
    course = Course(
        instructor_id=instructor.id,
        name="Closure",
        language="english",
        enroll_code=f"CLS-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(course)
    await db_session.commit()

    student = User(
        better_auth_id=f"close-student-{uuid.uuid4().hex[:8]}",
        email=f"close-{uuid.uuid4().hex[:8]}@connect.ust.hk",
        full_name="Closure Student",
        role="student",
    )
    db_session.add(student)
    await db_session.commit()

    concept = Concept(
        course_id=course.id,
        name="closure-concept",
        status="approved",
        instructor_curated=True,
    )
    db_session.add(concept)
    await db_session.commit()

    target_id = uuid.uuid4()
    db_session.add(
        ConceptTag(
            concept_id=concept.id,
            target_kind="pool_item",
            target_id=target_id,
            weight=Decimal("1.00"),
        )
    )

    note = LearningNote(
        course_id=course.id,
        user_id=student.id,
        source_event_ids=[],
        observed_signal="Student struggled with the concept.",
        review_status=note_status,
    )
    db_session.add(note)
    await db_session.flush()

    fua = FollowUpAction(
        learning_note_id=note.id,
        course_id=course.id,
        user_id=student.id,
        action_type="practice",
        target_kind="concept",
        target_id=concept.id,
        assignment_status="assigned",
    )
    db_session.add(fua)
    await db_session.commit()

    return course, student, concept, target_id, note, fua


@pytest.mark.asyncio
async def test_improved_outcome_closes_followup_and_records(
    db_session, test_instructor
):
    course, student, concept, target_id, note, fua = await _build_scenario(
        db_session, test_instructor
    )

    await apply_attempt_evidence(
        db_session,
        user_id=student.id,
        course_id=course.id,
        target_kind="pool_item",
        target_id=target_id,
        attempt_kind=AttemptKind.REVISION,
        outcome=0.9,
    )
    await db_session.commit()

    refreshed = (
        await db_session.execute(
            select(FollowUpAction).where(FollowUpAction.id == fua.id)
        )
    ).scalar_one()
    assert refreshed.assignment_status == "completed"

    checks = (
        await db_session.execute(
            select(OutcomeCheck).where(
                OutcomeCheck.follow_up_action_id == fua.id
            )
        )
    ).scalars().all()
    assert len(checks) == 1
    assert checks[0].status == "improved"
    assert checks[0].learning_note_id == note.id

    records = (
        await db_session.execute(
            select(CourseRecordItem).where(
                CourseRecordItem.learning_note_id == note.id
            )
        )
    ).scalars().all()
    assert len(records) == 1
    assert records[0].carry_forward is False


@pytest.mark.asyncio
async def test_persistent_outcome_carries_forward(db_session, test_instructor):
    course, student, concept, target_id, note, fua = await _build_scenario(
        db_session, test_instructor
    )

    await apply_attempt_evidence(
        db_session,
        user_id=student.id,
        course_id=course.id,
        target_kind="pool_item",
        target_id=target_id,
        attempt_kind=AttemptKind.REVISION,
        outcome=0.2,
    )
    await db_session.commit()

    check = (
        await db_session.execute(
            select(OutcomeCheck).where(
                OutcomeCheck.follow_up_action_id == fua.id
            )
        )
    ).scalar_one()
    assert check.status == "persistent"

    record = (
        await db_session.execute(
            select(CourseRecordItem).where(
                CourseRecordItem.learning_note_id == note.id
            )
        )
    ).scalar_one()
    assert record.carry_forward is True


@pytest.mark.asyncio
async def test_closure_is_idempotent(db_session, test_instructor):
    """Re-applying the same attempt must not write a second OutcomeCheck."""
    course, student, concept, target_id, note, fua = await _build_scenario(
        db_session, test_instructor
    )

    for _ in range(2):
        await apply_attempt_evidence(
            db_session,
            user_id=student.id,
            course_id=course.id,
            target_kind="pool_item",
            target_id=target_id,
            attempt_kind=AttemptKind.REVISION,
            outcome=0.9,
        )
        await db_session.commit()

    checks = (
        await db_session.execute(
            select(OutcomeCheck).where(
                OutcomeCheck.follow_up_action_id == fua.id
            )
        )
    ).scalars().all()
    assert len(checks) == 1


@pytest.mark.asyncio
async def test_unreviewed_note_skips_course_record(
    db_session, test_instructor
):
    """Closure still completes the follow-up + writes the OutcomeCheck, but
    a draft (un-reviewed) note must NOT become durable course memory."""
    course, student, concept, target_id, note, fua = await _build_scenario(
        db_session, test_instructor, note_status="draft"
    )

    await apply_attempt_evidence(
        db_session,
        user_id=student.id,
        course_id=course.id,
        target_kind="pool_item",
        target_id=target_id,
        attempt_kind=AttemptKind.REVISION,
        outcome=0.9,
    )
    await db_session.commit()

    refreshed = (
        await db_session.execute(
            select(FollowUpAction).where(FollowUpAction.id == fua.id)
        )
    ).scalar_one()
    assert refreshed.assignment_status == "completed"

    check = (
        await db_session.execute(
            select(OutcomeCheck).where(
                OutcomeCheck.follow_up_action_id == fua.id
            )
        )
    ).scalar_one()
    assert check.status == "improved"

    records = (
        await db_session.execute(
            select(CourseRecordItem).where(
                CourseRecordItem.learning_note_id == note.id
            )
        )
    ).scalars().all()
    assert records == []
