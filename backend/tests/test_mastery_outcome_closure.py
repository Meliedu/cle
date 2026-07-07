"""P6 B2 — outcome-closure syncs the `follow_up` checklist progress.

When ``mastery.py::_close_follow_ups_for_attempt`` flips a ``FollowUpAction`` to
``completed`` (a later attempt satisfies it) and writes its ``OutcomeCheck``, the
matching ``follow_up`` work_item's ``work_item_progress`` for that student flips
to ``completed`` inside the SAME transaction (the handler commits).

The sync is best-effort: a follow-up with NO work_item (a pre-P6 follow-up) is a
no-op, never a raise. It rides the privileged worker connection (BYPASSRLS,
migration ``28236be3d7b3``), so it may write the student's row. Idempotent on a
worker retry: a second closure pass leaves the already-``completed`` progress
row unchanged.
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import (
    Concept,
    ConceptTag,
    Course,
    FollowUpAction,
    LearningNote,
    User,
)
from app.models.work_item import WorkItem, WorkItemProgress
from app.services.mastery import AttemptKind, apply_attempt_evidence
from app.services.work_items import upsert_progress, upsert_work_item


async def _build_scenario(
    db_session,
    instructor: User,
    *,
    with_work_item: bool = True,
):
    """Course + student + concept + pool_item tag + reviewed note + open
    follow-up. When ``with_work_item`` (the B1 seam), also create the
    ``follow_up`` work_item + a ``follow_up_assigned`` progress row.

    Returns ``(course, student, target_id, fua, work_item)`` (``work_item`` is
    ``None`` when ``with_work_item`` is False).
    """
    course = Course(
        instructor_id=instructor.id,
        name="Closure Sync",
        language="english",
        enroll_code=f"CSY-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(course)
    await db_session.commit()

    student = User(
        better_auth_id=f"sync-student-{uuid.uuid4().hex[:8]}",
        email=f"sync-{uuid.uuid4().hex[:8]}@connect.ust.hk",
        full_name="Sync Student",
        role="student",
    )
    db_session.add(student)
    await db_session.commit()

    concept = Concept(
        course_id=course.id,
        name="sync-concept",
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
        review_status="reviewed",
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

    work_item = None
    if with_work_item:
        # The B1 seam: a reviewed follow-up is keyed on the FollowUpAction id.
        work_item = await upsert_work_item(
            db_session,
            course_id=course.id,
            source_kind="follow_up",
            source_id=fua.id,
            title="Practice follow-up",
            required=True,
            score_bearing=False,
            due_at=fua.due_at,
            close_at=fua.due_at,
            created_by=instructor.id,
        )
        await upsert_progress(
            db_session,
            work_item_id=work_item.id,
            user_id=student.id,
            status="follow_up_assigned",
        )
        await db_session.commit()

    return course, student, target_id, fua, work_item


async def _progress_status(db_session, work_item_id, user_id) -> str:
    return (
        await db_session.execute(
            select(WorkItemProgress.status).where(
                WorkItemProgress.work_item_id == work_item_id,
                WorkItemProgress.user_id == user_id,
            )
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_closure_syncs_follow_up_progress_to_completed(
    db_session, test_instructor
):
    """A satisfying attempt flips the follow_up progress row to `completed`."""
    course, student, target_id, fua, work_item = await _build_scenario(
        db_session, test_instructor
    )
    assert (
        await _progress_status(db_session, work_item.id, student.id)
        == "follow_up_assigned"
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

    # Follow-up closed AND its checklist progress synced in the same transaction.
    refreshed = (
        await db_session.execute(
            select(FollowUpAction).where(FollowUpAction.id == fua.id)
        )
    ).scalar_one()
    assert refreshed.assignment_status == "completed"
    assert (
        await _progress_status(db_session, work_item.id, student.id)
        == "completed"
    )


@pytest.mark.asyncio
async def test_closure_without_work_item_is_noop(db_session, test_instructor):
    """A pre-P6 follow-up (no work_item) closes without raising — no-op sync."""
    course, student, target_id, fua, _ = await _build_scenario(
        db_session, test_instructor, with_work_item=False
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

    # No work_item existed → no progress row was fabricated.
    progress = (
        await db_session.execute(
            select(WorkItemProgress).where(WorkItemProgress.user_id == student.id)
        )
    ).scalars().all()
    assert progress == []


@pytest.mark.asyncio
async def test_closure_sync_is_idempotent_on_retry(db_session, test_instructor):
    """A second closure pass leaves the already-`completed` progress unchanged."""
    course, student, target_id, fua, work_item = await _build_scenario(
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

    rows = (
        await db_session.execute(
            select(WorkItemProgress).where(
                WorkItemProgress.work_item_id == work_item.id,
                WorkItemProgress.user_id == student.id,
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "completed"
