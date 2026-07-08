"""Work-item write service (P4 B3).

Pure, race-safe helpers for the course checklist spine (spec §4.6). These are
transactional building blocks with NO commit inside — the endpoint / cron
callers in B4/B5/B8/B9 own the commit (Decision 3). Every write mirrors the
race-safe ``on_conflict`` pattern used by ``mastery.py`` so a re-publish, a
backfill, or a concurrent first-attempt can never raise ``IntegrityError``.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.work_item import WorkItem, WorkItemProgress

logger = logging.getLogger(__name__)


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


#: Progress statuses a post-window (re)submission may DERIVE that would REGRESS a
#: completed row — a late/partial edit of one already-answered card. Anything
#: else (``completed``/``follow_up_assigned``/…) is a forward transition and is
#: written as-is.
_REGRESSION_FROM_COMPLETED: frozenset[str] = frozenset({"late", "submitted"})


async def upsert_progress_monotonic(
    db: AsyncSession,
    *,
    work_item_id: uuid.UUID,
    user_id: uuid.UUID,
    status: str,
) -> WorkItemProgress:
    """Upsert progress WITHOUT downgrading a ``completed`` row to ``late``/``submitted``.

    ``upsert_progress`` blindly overwrites ``status``; a student who finished a
    checkpoint / activity ON TIME (``completed``) but later EDITS one card AFTER
    ``close_at`` (still allowed while it is ``published``/``live``) derives
    ``late`` — which would clobber ``completed``. This wrapper reads the existing
    row first and, when it is already ``completed`` and the newly-derived status
    would be a regression (``late``/``submitted``), KEEPS ``completed`` ("first
    completion wins, never downgrades" — mirrors the attendance precedent and
    ``mark_missed_work_items``'s terminal-status protection). Every other
    transition (including the ``submitted``→``completed`` forward edge) defers to
    ``upsert_progress`` unchanged.

    Pure helper: the caller owns the commit.
    """
    if status in _REGRESSION_FROM_COMPLETED:
        existing = (
            await db.execute(
                select(WorkItemProgress.status).where(
                    WorkItemProgress.work_item_id == work_item_id,
                    WorkItemProgress.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if existing == "completed":
            status = "completed"
    return await upsert_progress(
        db, work_item_id=work_item_id, user_id=user_id, status=status
    )


async def remove_work_item(db: AsyncSession, work_item: WorkItem) -> None:
    """Soft-delete a checklist item (stamp ``deleted_at``).

    Pure helper: the caller owns the commit.
    """
    work_item.deleted_at = datetime.now(timezone.utc)
    db.add(work_item)


#: Checkpoint statuses that must own a ``checkpoint`` work_item — a checkpoint is
#: on the student checklist once it is student-visible (spec §4.6 + Decision 4).
_BACKFILL_STATUSES = ("published", "live", "closed", "archived")


async def backfill_work_items(db: AsyncSession) -> int:
    """Create one ``checkpoint`` work_item per pre-P4 published checkpoint.

    Inserts a checklist row for every non-deleted checkpoint in
    ``published|live|closed|archived`` that lacks one (Decision 4) and commits.
    Idempotent: a re-run finds nothing missing and returns ``0`` — the
    ``(course_id, source_kind, source_id)`` unique index + a pre-filter both
    guard against duplicates. Does NOT synthesize historical
    ``work_item_progress`` (progress is derived forward from new submissions).

    Returns the number of work_items created on this run. Safe to run repeatedly
    (ops/backfill entrypoint — NOT wired into startup).
    """
    # Local imports keep this module free of an import cycle at load time.
    from app.models.checkpoint import Checkpoint
    from app.models.course import Course

    checkpoints = (
        await db.execute(
            select(Checkpoint).where(
                Checkpoint.status.in_(_BACKFILL_STATUSES),
                Checkpoint.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    if not checkpoints:
        return 0

    cp_ids = [cp.id for cp in checkpoints]
    already = set(
        (
            await db.execute(
                select(WorkItem.source_id).where(
                    WorkItem.source_kind == "checkpoint",
                    WorkItem.source_id.in_(cp_ids),
                )
            )
        ).scalars().all()
    )

    # The checklist row's author is the checkpoint's course instructor.
    course_ids = {cp.course_id for cp in checkpoints}
    instructor_by_course = {
        cid: instr
        for cid, instr in (
            await db.execute(
                select(Course.id, Course.instructor_id).where(Course.id.in_(course_ids))
            )
        ).all()
    }

    created = 0
    for cp in checkpoints:
        if cp.id in already:
            continue
        created_by = instructor_by_course.get(cp.course_id)
        if created_by is None:
            # Orphaned checkpoint (course gone) — nothing sensible to author it.
            continue
        await upsert_work_item(
            db,
            course_id=cp.course_id,
            source_kind="checkpoint",
            source_id=cp.id,
            title=cp.title,
            required=True,
            score_bearing=False,
            due_at=cp.close_at,
            close_at=cp.close_at,
            created_by=created_by,
        )
        created += 1

    if created:
        await db.commit()
    return created


# --------------------------------------------------------------------------- #
#  P4 B9: mark_missed_work_items cron                                          #
# --------------------------------------------------------------------------- #

#: Progress statuses the cron may flip to ``missed``. Everything else is
#: protected (see ``_TERMINAL_STATUSES``): a student who is still ``pending``
#: or mid-attempt on a now-past-due required item has missed it.
_MISSABLE_STATUSES: frozenset[str] = frozenset({"pending", "in_progress"})

#: Statuses the cron must NEVER overwrite. ``completed``/``submitted`` are the
#: happy path; ``missed`` is already terminal (idempotency); ``late`` is a
#: submission that merely arrived late — a late submission is NOT missed;
#: ``follow_up_assigned`` means the loop already advanced past the deadline.
_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"completed", "submitted", "missed", "late", "follow_up_assigned"}
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def mark_missed_work_items(session: AsyncSession) -> int:
    """Flip actively-enrolled students to ``missed`` on past-due required items.

    Mirrors ``checkpoints.close_due_checkpoints`` (P3 T13): a privileged cron
    service that commits internally and returns the number of rows it changed.
    The worker connection is ``BYPASSRLS`` (migration ``28236be3d7b3``) so it may
    write every student's ``work_item_progress`` row.

    An item's deadline is ``close_at`` when set, else ``due_at``; an item with
    neither is never missed. For each ``required``, non-deleted work_item whose
    deadline is ``<= now``:

    - each ACTIVE ``student`` enrollment on the item's course whose progress is
      ``pending``/``in_progress`` is flipped to ``missed``;
    - each such student with NO progress row gets a fresh ``missed`` row (a
      never-started required item that is now past due is a missed item);
    - ``completed``/``submitted``/``missed``/``late``/``follow_up_assigned`` rows
      are left untouched (terminal / protected).

    Idempotent: a second run finds only protected rows and returns ``0``.
    Returns the number of progress rows created or flipped on this run.
    """
    # Local imports keep this module import-cycle free at load time.
    from app.models.course import Enrollment

    now = _utcnow()

    items = (
        await session.execute(
            select(WorkItem).where(
                WorkItem.required.is_(True),
                WorkItem.deleted_at.is_(None),
                or_(
                    WorkItem.close_at <= now,
                    and_(WorkItem.close_at.is_(None), WorkItem.due_at <= now),
                ),
            )
        )
    ).scalars().all()
    if not items:
        return 0

    item_ids = [it.id for it in items]
    course_ids = {it.course_id for it in items}

    # Active student roster per course, in one query.
    active_by_course: dict[uuid.UUID, list[uuid.UUID]] = {}
    for course_id, user_id in (
        await session.execute(
            select(Enrollment.course_id, Enrollment.user_id).where(
                Enrollment.course_id.in_(course_ids),
                Enrollment.role == "student",
                Enrollment.status == "active",
            )
        )
    ).all():
        active_by_course.setdefault(course_id, []).append(user_id)

    # Existing progress for these items, keyed on (item, user), in one query.
    existing: dict[tuple[uuid.UUID, uuid.UUID], WorkItemProgress] = {
        (row.work_item_id, row.user_id): row
        for row in (
            await session.execute(
                select(WorkItemProgress).where(
                    WorkItemProgress.work_item_id.in_(item_ids)
                )
            )
        ).scalars().all()
    }

    changed = 0
    for item in items:
        for user_id in active_by_course.get(item.course_id, ()):
            row = existing.get((item.id, user_id))
            if row is None:
                # Never-started: create the missed row directly. on_conflict is
                # unnecessary here (single serialized cron, prior read) but kept
                # defensive against a concurrent first-attempt insert.
                await session.execute(
                    pg_insert(WorkItemProgress)
                    .values(
                        id=uuid.uuid4(),
                        work_item_id=item.id,
                        user_id=user_id,
                        status="missed",
                    )
                    .on_conflict_do_nothing(
                        index_elements=["work_item_id", "user_id"]
                    )
                )
                changed += 1
            elif row.status in _MISSABLE_STATUSES:
                row.status = "missed"
                row.updated_at = now
                changed += 1
            # else: protected/terminal — leave untouched.

    if changed:
        await session.commit()
        logger.info("mark_missed_work_items marked %d progress row(s)", changed)
    return changed
