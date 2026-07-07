"""P4 B4 — backfill checkpoint work_items for pre-P4 published checkpoints.

``backfill_work_items(session)`` inserts one ``checkpoint`` work_item per existing
checkpoint in ``published|live|closed|archived`` that lacks one, and is idempotent
on re-run (Decision 4). It never synthesizes historical ``work_item_progress``.
"""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course, User
from app.models.checkpoint import Checkpoint
from app.models.work_item import WorkItem
from app.services.work_items import backfill_work_items


@pytest_asyncio.fixture
async def course(db_session: AsyncSession, test_instructor: User) -> Course:
    c = Course(
        name="Backfill", language="english",
        instructor_id=test_instructor.id, enroll_code="BKFL0001",
    )
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


async def _mk_checkpoint(
    db_session: AsyncSession, course: Course, status: str, title: str
) -> Checkpoint:
    cp = Checkpoint(
        course_id=course.id, kind="session", title=title, status=status,
        close_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(cp)
    await db_session.flush()
    return cp


@pytest.mark.asyncio
async def test_backfill_creates_one_per_eligible_checkpoint(
    db_session: AsyncSession, course: Course
):
    pub = await _mk_checkpoint(db_session, course, "published", "Published")
    live = await _mk_checkpoint(db_session, course, "live", "Live")
    closed = await _mk_checkpoint(db_session, course, "closed", "Closed")
    arch = await _mk_checkpoint(db_session, course, "archived", "Archived")
    # These are NOT student-visible / not yet published — must be skipped.
    await _mk_checkpoint(db_session, course, "draft", "Draft")
    await _mk_checkpoint(db_session, course, "approved", "Approved")
    await _mk_checkpoint(db_session, course, "scheduled", "Scheduled")
    await db_session.commit()

    created = await backfill_work_items(db_session)
    assert created == 4

    rows = (
        await db_session.execute(
            select(WorkItem).where(WorkItem.source_kind == "checkpoint")
        )
    ).scalars().all()
    assert {r.source_id for r in rows} == {pub.id, live.id, closed.id, arch.id}
    for r in rows:
        assert r.required is True
        assert r.score_bearing is False
        assert r.course_id == course.id
        assert r.created_by == course.instructor_id
        assert r.due_at is not None
        assert r.close_at == r.due_at


@pytest.mark.asyncio
async def test_backfill_is_idempotent(db_session: AsyncSession, course: Course):
    await _mk_checkpoint(db_session, course, "published", "Published")
    await db_session.commit()

    first = await backfill_work_items(db_session)
    assert first == 1
    second = await backfill_work_items(db_session)
    assert second == 0

    rows = (await db_session.execute(select(WorkItem))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_backfill_skips_soft_deleted_checkpoints(
    db_session: AsyncSession, course: Course
):
    cp = await _mk_checkpoint(db_session, course, "published", "Deleted")
    cp.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()

    created = await backfill_work_items(db_session)
    assert created == 0
