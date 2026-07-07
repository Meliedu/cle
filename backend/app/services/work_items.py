"""Work-item write service (P4 B3).

Pure, race-safe helpers for the course checklist spine (spec §4.6). These are
transactional building blocks with NO commit inside — the endpoint / cron
callers in B4/B5/B8/B9 own the commit (Decision 3). Every write mirrors the
race-safe ``on_conflict`` pattern used by ``mastery.py`` so a re-publish, a
backfill, or a concurrent first-attempt can never raise ``IntegrityError``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.work_item import WorkItem, WorkItemProgress


async def upsert_work_item(
    db: AsyncSession,
    *,
    course_id: uuid.UUID,
    source_kind: str,
    source_id: uuid.UUID,
    title: str,
    required: bool,
    score_bearing: bool,
    due_at: datetime | None,
    close_at: datetime | None,
    created_by: uuid.UUID,
) -> WorkItem:
    """Idempotently create the checklist row for ``(course, source_kind, source)``.

    Mirrors ``mastery.py::_get_or_create_mastery``: ``INSERT ... ON CONFLICT DO
    NOTHING ... RETURNING`` then, when the conflict swallowed the insert (RETURNING
    yields ``None``), re-fetch the pre-existing row. A second call with the SAME
    ``(course_id, source_kind, source_id)`` returns the SAME row — the publish +
    backfill upsert is safe to run repeatedly (Decision 3).

    Pure helper: the caller owns the commit.
    """
    stmt = (
        pg_insert(WorkItem)
        .values(
            id=uuid.uuid4(),
            course_id=course_id,
            source_kind=source_kind,
            source_id=source_id,
            title=title,
            required=required,
            score_bearing=score_bearing,
            due_at=due_at,
            close_at=close_at,
            created_by=created_by,
        )
        .on_conflict_do_nothing(
            index_elements=["course_id", "source_kind", "source_id"]
        )
        .returning(WorkItem)
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is not None:
        return row

    # Conflict: the row already exists — re-fetch it (mirror mastery.py).
    return (
        await db.execute(
            select(WorkItem).where(
                WorkItem.course_id == course_id,
                WorkItem.source_kind == source_kind,
                WorkItem.source_id == source_id,
            )
        )
    ).scalar_one()


async def upsert_progress(
    db: AsyncSession,
    *,
    work_item_id: uuid.UUID,
    user_id: uuid.UUID,
    status: str,
) -> WorkItemProgress:
    """Upsert a student's checklist-item state on ``(work_item_id, user_id)``.

    A state transition updates the row in place (``ON CONFLICT DO UPDATE`` of
    ``status`` + ``updated_at``); the first write inserts it. One row per
    ``(work_item_id, user_id)`` (Decision 3).

    Pure helper: the caller owns the commit.
    """
    now = datetime.now(timezone.utc)
    stmt = (
        pg_insert(WorkItemProgress)
        .values(
            id=uuid.uuid4(),
            work_item_id=work_item_id,
            user_id=user_id,
            status=status,
        )
        .on_conflict_do_update(
            index_elements=["work_item_id", "user_id"],
            set_={"status": status, "updated_at": now},
        )
        .returning(WorkItemProgress)
    )
    row = (await db.execute(stmt)).scalar_one()
    # RETURNING an ORM entity re-uses the identity-mapped instance without
    # overwriting its attributes, so on the DO UPDATE path ``row`` can still
    # carry the pre-update ``status``. Refresh to reflect the persisted values.
    await db.refresh(row)
    return row


async def remove_work_item(db: AsyncSession, work_item: WorkItem) -> None:
    """Soft-delete a checklist item (stamp ``deleted_at``).

    Pure helper: the caller owns the commit.
    """
    work_item.deleted_at = datetime.now(timezone.utc)
    db.add(work_item)
