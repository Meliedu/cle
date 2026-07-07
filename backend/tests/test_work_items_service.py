"""Work-item write service (P4 B3).

Pure, race-safe helpers — no HTTP, NO commit inside (the transactional callers
in B4/B5/B8 own the commit, Decision 3). Mirrors ``mastery.py``'s
``on_conflict_do_nothing(...).returning(...)`` + re-fetch-on-conflict pattern.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from app.models.course import Course
from app.models.user import User
from app.models.work_item import WorkItem, WorkItemProgress
from app.services.work_items import (
    remove_work_item,
    upsert_progress,
    upsert_work_item,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def course(db_session, test_instructor: User) -> Course:
    c = Course(
        name="Phonetics",
        code="LING220",
        language="english",
        instructor_id=test_instructor.id,
        enroll_code="WORKIT01",
    )
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


async def test_upsert_work_item_inserts_new_row(db_session, course, test_instructor):
    source_id = uuid.uuid4()
    due = datetime.now(timezone.utc) + timedelta(days=1)
    close = due + timedelta(days=1)

    item = await upsert_work_item(
        db_session,
        course_id=course.id,
        source_kind="checkpoint",
        source_id=source_id,
        title="Week 1 checkpoint",
        required=True,
        score_bearing=False,
        due_at=due,
        close_at=close,
        created_by=test_instructor.id,
    )
    await db_session.commit()

    assert item.id is not None
    assert item.course_id == course.id
    assert item.source_kind == "checkpoint"
    assert item.source_id == source_id
    assert item.title == "Week 1 checkpoint"
    assert item.required is True
    assert item.score_bearing is False
    assert item.created_by == test_instructor.id


async def test_upsert_work_item_is_idempotent_on_conflict(
    db_session, course, test_instructor
):
    """A second call with the same (course_id, source_kind, source_id) returns
    the SAME row — no IntegrityError (race-safe upsert, Decision 3)."""
    source_id = uuid.uuid4()

    first = await upsert_work_item(
        db_session,
        course_id=course.id,
        source_kind="checkpoint",
        source_id=source_id,
        title="First title",
        required=True,
        score_bearing=False,
        due_at=None,
        close_at=None,
        created_by=test_instructor.id,
    )
    await db_session.commit()

    second = await upsert_work_item(
        db_session,
        course_id=course.id,
        source_kind="checkpoint",
        source_id=source_id,
        title="Second title (ignored)",
        required=False,
        score_bearing=True,
        due_at=None,
        close_at=None,
        created_by=test_instructor.id,
    )
    await db_session.commit()

    assert second.id == first.id
    # on_conflict_do_nothing → existing row is preserved unchanged.
    assert second.title == "First title"

    rows = (
        await db_session.execute(
            WorkItem.__table__.select().where(
                WorkItem.course_id == course.id,
                WorkItem.source_id == source_id,
            )
        )
    ).all()
    assert len(rows) == 1


async def test_upsert_work_item_distinct_source_kind_is_new_row(
    db_session, course, test_instructor
):
    source_id = uuid.uuid4()

    a = await upsert_work_item(
        db_session,
        course_id=course.id,
        source_kind="checkpoint",
        source_id=source_id,
        title="cp",
        required=True,
        score_bearing=False,
        due_at=None,
        close_at=None,
        created_by=test_instructor.id,
    )
    b = await upsert_work_item(
        db_session,
        course_id=course.id,
        source_kind="material",
        source_id=source_id,
        title="mat",
        required=True,
        score_bearing=False,
        due_at=None,
        close_at=None,
        created_by=test_instructor.id,
    )
    await db_session.commit()

    assert a.id != b.id


async def test_upsert_progress_inserts_then_updates(
    db_session, course, test_instructor, test_student
):
    item = await upsert_work_item(
        db_session,
        course_id=course.id,
        source_kind="checkpoint",
        source_id=uuid.uuid4(),
        title="cp",
        required=True,
        score_bearing=False,
        due_at=None,
        close_at=None,
        created_by=test_instructor.id,
    )
    await db_session.commit()

    first = await upsert_progress(
        db_session,
        work_item_id=item.id,
        user_id=test_student.id,
        status="in_progress",
    )
    await db_session.commit()

    assert first.work_item_id == item.id
    assert first.user_id == test_student.id
    assert first.status == "in_progress"

    updated = await upsert_progress(
        db_session,
        work_item_id=item.id,
        user_id=test_student.id,
        status="completed",
    )
    await db_session.commit()

    assert updated.id == first.id
    assert updated.status == "completed"

    rows = (
        await db_session.execute(
            WorkItemProgress.__table__.select().where(
                WorkItemProgress.work_item_id == item.id,
                WorkItemProgress.user_id == test_student.id,
            )
        )
    ).all()
    assert len(rows) == 1


async def test_remove_work_item_soft_deletes(db_session, course, test_instructor):
    item = await upsert_work_item(
        db_session,
        course_id=course.id,
        source_kind="checkpoint",
        source_id=uuid.uuid4(),
        title="cp",
        required=True,
        score_bearing=False,
        due_at=None,
        close_at=None,
        created_by=test_instructor.id,
    )
    await db_session.commit()
    assert item.deleted_at is None

    await remove_work_item(db_session, item)
    await db_session.commit()

    refreshed = await db_session.get(WorkItem, item.id)
    assert refreshed is not None
    assert refreshed.deleted_at is not None
