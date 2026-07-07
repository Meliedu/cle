"""Model/constraint tests for ``work_items`` (P4 Task B1).

``work_items`` is the course-scoped, teacher-authored checklist spine
(spec §4.6). It is operational — mirrors ``CheckpointLaunch``: **NO RLS**
(every read is enrollment- or owner-guarded at the endpoint layer). Per-student
state lives in the separate owner-owned ``work_item_progress`` table (B2).

This covers only the ORM columns, defaults, the ``source_kind`` CHECK (the FULL
spec §4.6 enum, Decision 1), and the UNIQUE INDEX on
``(course_id, source_kind, source_id)`` that makes the publish/backfill upsert
idempotent (Decision 3) — exercised via ``Base.metadata.create_all`` in the
disposable test DB (``db_session``).
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.course import Course
from app.models.work_item import WorkItem

FULL_SOURCE_KINDS = [
    "checkpoint",
    "practice",
    "quiz",
    "activity",
    "material",
    "follow_up",
    "report",
]


@pytest_asyncio.fixture
async def seed_course(db_session, test_instructor):
    course = Course(
        name="LANG1511",
        language="zh",
        instructor_id=test_instructor.id,
        enroll_code="WITM" + uuid.uuid4().hex[:4].upper(),
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


def _make_item(
    course,
    created_by,
    *,
    source_kind="checkpoint",
    source_id=None,
    title="Session 1 checkpoint",
    required=None,
    score_bearing=None,
    due_at=None,
    close_at=None,
    visible_from=None,
):
    kwargs = dict(
        course_id=course.id,
        source_kind=source_kind,
        source_id=source_id or uuid.uuid4(),
        title=title,
        created_by=created_by,
        due_at=due_at,
        close_at=close_at,
        visible_from=visible_from,
    )
    if required is not None:
        kwargs["required"] = required
    if score_bearing is not None:
        kwargs["score_bearing"] = score_bearing
    return WorkItem(**kwargs)


@pytest.mark.asyncio
async def test_work_item_create_and_defaults(
    db_session, seed_course, test_instructor
):
    now = datetime.now(timezone.utc)
    item = _make_item(
        seed_course,
        test_instructor.id,
        due_at=now,
        close_at=now + timedelta(hours=1),
        visible_from=now - timedelta(days=1),
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    assert item.id is not None
    assert item.course_id == seed_course.id
    assert item.source_kind == "checkpoint"
    assert item.source_id is not None
    assert item.title == "Session 1 checkpoint"
    # Defaults (Decision 1): required=True, score_bearing=False.
    assert item.required is True
    assert item.score_bearing is False
    assert item.due_at is not None
    assert item.close_at is not None
    assert item.visible_from is not None
    assert item.created_by == test_instructor.id
    # TimestampMixin + SoftDeleteMixin.
    assert item.created_at is not None
    assert item.updated_at is not None
    assert item.deleted_at is None


@pytest.mark.asyncio
async def test_nullable_time_columns(db_session, seed_course, test_instructor):
    item = _make_item(seed_course, test_instructor.id)
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    assert item.due_at is None
    assert item.close_at is None
    assert item.visible_from is None


@pytest.mark.asyncio
@pytest.mark.parametrize("source_kind", FULL_SOURCE_KINDS)
async def test_source_kind_accepts_full_enum(
    db_session, seed_course, test_instructor, source_kind
):
    item = _make_item(seed_course, test_instructor.id, source_kind=source_kind)
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    assert item.source_kind == source_kind


@pytest.mark.asyncio
async def test_bad_source_kind_rejected(
    db_session, seed_course, test_instructor
):
    db_session.add(
        _make_item(seed_course, test_instructor.id, source_kind="meeting")
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_required_and_score_bearing_overridable(
    db_session, seed_course, test_instructor
):
    item = _make_item(
        seed_course,
        test_instructor.id,
        source_kind="material",
        required=False,
        score_bearing=True,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    assert item.required is False
    assert item.score_bearing is True


@pytest.mark.asyncio
async def test_unique_course_source(db_session, seed_course, test_instructor):
    """uq_work_items_course_source on (course_id, source_kind, source_id) —
    Decision 3 idempotency for the publish/backfill upsert."""
    source_id = uuid.uuid4()
    db_session.add(
        _make_item(
            seed_course,
            test_instructor.id,
            source_kind="checkpoint",
            source_id=source_id,
        )
    )
    await db_session.flush()
    db_session.add(
        _make_item(
            seed_course,
            test_instructor.id,
            source_kind="checkpoint",
            source_id=source_id,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_same_source_id_different_kind_allowed(
    db_session, seed_course, test_instructor
):
    """The unique index is on the (course, kind, source) TRIPLE — the same
    source_id under a different source_kind is a distinct row."""
    source_id = uuid.uuid4()
    db_session.add(
        _make_item(
            seed_course,
            test_instructor.id,
            source_kind="checkpoint",
            source_id=source_id,
        )
    )
    db_session.add(
        _make_item(
            seed_course,
            test_instructor.id,
            source_kind="material",
            source_id=source_id,
        )
    )
    await db_session.commit()  # no IntegrityError
    rows = (
        await db_session.execute(
            select(WorkItem).where(WorkItem.source_id == source_id)
        )
    ).scalars().all()
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_soft_delete_column(db_session, seed_course, test_instructor):
    item = _make_item(seed_course, test_instructor.id)
    db_session.add(item)
    await db_session.commit()
    item.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()
    await db_session.refresh(item)
    assert item.deleted_at is not None
