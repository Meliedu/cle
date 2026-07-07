"""P7 B11 (Decision 9.2) — ``completed``-on-soft-deleted-card edge.

``_derive_progress_status`` flips a checklist item to ``completed`` once the
student's on-time response count reaches the live-card count. The on-time count
must be computed over LIVE (non-deleted) cards consistently with the live-card
denominator — otherwise a response to a since-soft-deleted card can inflate the
count and spuriously mark a still-incomplete checkpoint ``completed``.
"""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.checkpoint import Checkpoint, CheckpointCard
from app.models.course import Course
from app.models.user import User
from app.models.work_item import WorkItem, WorkItemProgress
from app.services.checkpoint_responses import submit_checkpoint_response


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _make_card(db: AsyncSession, cp: Checkpoint, position: int) -> CheckpointCard:
    card = CheckpointCard(
        checkpoint_id=cp.id, position=position, kind="review_point",
        prompt=f"Q{position}",
    )
    db.add(card)
    await db.flush()
    return card


@pytest.mark.asyncio
async def test_soft_deleted_answered_card_does_not_flip_to_completed(
    db_session: AsyncSession, test_instructor: User, test_student: User
):
    course = Course(
        name="Progress Course", language="zh", instructor_id=test_instructor.id,
        enroll_code="PC" + uuid.uuid4().hex[:6].upper(),
    )
    db_session.add(course)
    await db_session.flush()

    cp = Checkpoint(
        course_id=course.id, kind="session", title="CP", status="published",
        close_rule="manual",
    )
    db_session.add(cp)
    await db_session.flush()

    # Three live review cards; the checklist spine work_item.
    card_a = await _make_card(db_session, cp, 0)
    card_b = await _make_card(db_session, cp, 1)
    await _make_card(db_session, cp, 2)  # card C — never answered
    db_session.add(
        WorkItem(
            course_id=course.id, source_kind="checkpoint", source_id=cp.id,
            title="CP", created_by=test_instructor.id,
        )
    )
    await db_session.commit()

    # Answer A and B on time (C left unanswered).
    await submit_checkpoint_response(
        db_session, checkpoint=cp, card=card_a, user_id=test_student.id,
        confidence=2, text_response=None,
    )
    await submit_checkpoint_response(
        db_session, checkpoint=cp, card=card_b, user_id=test_student.id,
        confidence=2, text_response=None,
    )

    # Soft-delete the answered card A → live cards are now {B, C}; only B is
    # answered, C is not, so the checkpoint is NOT complete.
    card_a.deleted_at = _utcnow()
    await db_session.commit()

    # Re-submit B (recomputes progress). With the buggy count the stale A response
    # inflates on_time to 2 == live(2) → spurious ``completed``.
    await submit_checkpoint_response(
        db_session, checkpoint=cp, card=card_b, user_id=test_student.id,
        confidence=2, text_response=None,
    )

    wi = (
        await db_session.execute(
            select(WorkItem).where(
                WorkItem.source_kind == "checkpoint", WorkItem.source_id == cp.id
            )
        )
    ).scalar_one()
    progress = (
        await db_session.execute(
            select(WorkItemProgress).where(
                WorkItemProgress.work_item_id == wi.id,
                WorkItemProgress.user_id == test_student.id,
            )
        )
    ).scalar_one()
    assert progress.status == "submitted"
