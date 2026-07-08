"""Student activity-response submission + the PARTICIPATION-ONLY evidence seam
(P5 B9).

This is the ONE evidence path for activities (Decision 5 — no parallel system).
It COPIES ``checkpoint_responses.py`` structure but — because activities carry no
correctness signal (like attendance, P3) — it emits a single participation
``LearningEvent`` and **NEVER** an ``update_concept_mastery`` Task:

1. Upsert the student's submission (one row per ``(activity_id, user_id)`` so a
   resubmit updates in place; a ``comment_reaction`` STACKS successive reactions
   inside ``payload``), write ``work_item_progress`` on the response's OWN commit
   — so progress durability equals response durability.
2. Best-effort evidence seam (wrapped in try/except so a failure here can never
   roll back the committed response): write ONE ``LearningEvent``
   (``stage='during_class'``, ``source_kind='activity'``). No mastery.
3. Notify the live monitor (a best-effort no-op seam until B10 wires
   ``activity_monitor``).

The caller (endpoint) resolves + authorizes the activity (enrollment-scoped via
``verify_enrollment``) and passes the authenticated ``user_id`` — a student can
only ever write their own row, so "wrong-owner cannot write" holds at the app
layer (RLS is defense-in-depth).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity, ActivityResponse
from app.models.work_item import WorkItem
from app.services.learning_events import record_attempt_event
from app.services.work_items import upsert_progress_monotonic

logger = logging.getLogger(__name__)

#: Activity statuses that accept a student submission (§4.4). An activity is
#: answerable while it is student-visible.
OPEN_STATUSES: frozenset[str] = frozenset({"published", "live"})


def _merge_payload(
    fmt: str, existing: dict | None, incoming: dict
) -> dict:
    """Compute the payload to persist for a (re)submission.

    - ``comment_reaction`` STACKS: each submission appends its ``incoming`` object
      to an ``entries`` list inside the stored payload (§4.4), so a student can
      react/comment multiple times on one row.
    - ``swipe`` / ``vote`` REPLACE: a resubmit overwrites the payload in place (one
      opinion per student, changeable).
    """
    if fmt == "comment_reaction":
        entries = list((existing or {}).get("entries", []))
        entries.append(incoming)
        return {"entries": entries}
    return incoming


async def _notify_monitor(db: AsyncSession, activity_id: uuid.UUID) -> None:
    """Live-monitor broadcast seam (Decision 6, wired in B10).

    Pushes a ``submission`` broadcast to any connected teacher monitor via a
    reused ``ConnectionManager`` (``activity_monitor.broadcast_submission``).
    Best-effort: a broadcast failure must NEVER fail the student's already-
    committed response, so the whole thing is wrapped. ``activity_monitor`` does
    not exist yet (B10) — the import is guarded so this is a safe no-op until then.
    """
    try:
        from app.services.activity_monitor import broadcast_submission

        await broadcast_submission(db, activity_id)
    except Exception:  # noqa: BLE001 — non-fatal: response already persisted
        logger.debug(
            "Activity monitor broadcast skipped/failed for activity_id=%s "
            "(wired in B10)",
            activity_id,
        )


async def submit_activity_response(
    db: AsyncSession,
    *,
    activity: Activity,
    user_id: uuid.UUID,
    payload: dict,
) -> ActivityResponse:
    """Upsert one activity response and fire the PARTICIPATION-ONLY evidence seam.

    The caller has already resolved + authorized ``activity`` (only a
    ``published``/``live`` activity reaches here) and passes the authenticated
    ``user_id``.
    """
    # Capture identifiers up front: a best-effort rollback below expires the ORM
    # instances, so any later attribute access would trigger lazy async IO
    # (MissingGreenlet). Locals are immune.
    activity_id = activity.id
    course_id = activity.course_id
    fmt = activity.format
    close_at = activity.close_at

    now = datetime.now(timezone.utc)
    # Past close_at ⇒ late (an activity stays answerable while published/live, but
    # the row records that it arrived after the window).
    row_status = "late" if close_at is not None and now > close_at else "on_time"

    # ``comment_reaction`` needs the current stored payload to stack onto; swipe/
    # vote replace, so the read is only meaningful for the stacking format.
    existing_payload: dict | None = None
    if fmt == "comment_reaction":
        existing_payload = (
            await db.execute(
                select(ActivityResponse.payload).where(
                    ActivityResponse.activity_id == activity_id,
                    ActivityResponse.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
    new_payload = _merge_payload(fmt, existing_payload, payload)

    # Upsert on the (activity_id, user_id) unique constraint — a resubmit updates
    # in place (id is set explicitly because a Core INSERT does not fire the
    # Python-side ``default=uuid.uuid4``).
    stmt = (
        pg_insert(ActivityResponse)
        .values(
            id=uuid.uuid4(),
            activity_id=activity_id,
            user_id=user_id,
            payload=new_payload,
            status=row_status,
            submitted_at=now,
        )
        .on_conflict_do_update(
            index_elements=["activity_id", "user_id"],
            set_={
                "payload": new_payload,
                "status": row_status,
                "submitted_at": now,
                "updated_at": now,
            },
        )
        .returning(ActivityResponse.id)
    )
    response_id = (await db.execute(stmt)).scalar_one()

    # Transactional checklist progress (Decision 5): the student's
    # ``work_item_progress`` for this activity's work_item rides the RESPONSE's
    # OWN commit below — NOT the best-effort evidence block — so progress
    # durability equals response durability. A missing work_item (an unpublished
    # preview / pre-spine activity) is a no-op, never a 500. A single-shot
    # activity submission is ``completed`` on submit unless it arrived late.
    work_item = (
        await db.execute(
            select(WorkItem).where(
                WorkItem.course_id == course_id,
                WorkItem.source_kind == "activity",
                WorkItem.source_id == activity_id,
                WorkItem.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if work_item is not None:
        progress_status = "late" if row_status == "late" else "completed"
        # ``user_id`` is the authenticated caller (endpoint-supplied) — a student
        # can only ever write their own progress row. ``_monotonic`` so a
        # post-close resubmit (derives ``late``) never downgrades an
        # already-``completed`` checklist row.
        await upsert_progress_monotonic(
            db,
            work_item_id=work_item.id,
            user_id=user_id,
            status=progress_status,
        )

    await db.commit()

    # Evidence seam (best-effort) — a failure here must not lose the response.
    # PARTICIPATION-ONLY: emit ONE LearningEvent, NEVER update_concept_mastery.
    try:
        await record_attempt_event(
            db,
            course_id=course_id,
            user_id=user_id,
            source_kind="activity",
            source_id=activity_id,
            stage="during_class",
            value={"format": fmt, "payload": new_payload},
        )
        await db.commit()
    except Exception:  # noqa: BLE001 — non-fatal: response already persisted
        logger.exception(
            "Failed to record activity evidence for activity_id=%s user_id=%s",
            activity_id,
            user_id,
        )
        await db.rollback()

    await _notify_monitor(db, activity_id)

    response = await db.get(ActivityResponse, response_id)
    assert response is not None
    return response
