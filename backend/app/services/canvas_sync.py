"""Daily Canvas → Meli sync scheduler.

Polls active CanvasIntegration rows whose roster has not been synced in the
last 24 hours, runs roster diff + file scan, and writes CanvasSyncEvent rows.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

from app.database import async_session_factory
from app.models import CanvasIntegration, CanvasSyncEvent, Document
from app.services import canvas_client as canvas_client_svc
from app.services.canvas_roster import sync_roster

logger = logging.getLogger(__name__)


SCHEDULER_POLL_SECONDS = 300  # 5 minutes
SYNC_INTERVAL_HOURS = 24


async def sync_integration(db, integration: CanvasIntegration) -> None:
    """Run a single integration's roster diff + file scan and log events.

    ``CanvasNotConnected`` causes the integration to be marked
    ``sync_status='disconnected'`` (the linker revoked their Canvas
    connection). ``CanvasReauthRequired`` and any other unexpected error are
    logged as ``error`` events but do not flip status — a re-auth is a
    user-fixable transient state.
    """
    try:
        client = await canvas_client_svc.get_client_for_user(
            db, integration.connected_by_user_id
        )
    except canvas_client_svc.CanvasNotConnected:
        integration.sync_status = "disconnected"
        db.add(
            CanvasSyncEvent(
                course_id=integration.course_id,
                event_type="error",
                payload={"code": "canvas_not_connected"},
            )
        )
        await db.commit()
        return
    except canvas_client_svc.CanvasReauthRequired:
        db.add(
            CanvasSyncEvent(
                course_id=integration.course_id,
                event_type="error",
                payload={"code": "canvas_reauth_required"},
            )
        )
        await db.commit()
        return

    now = datetime.now(timezone.utc)

    # Roster diff
    try:
        diff = await sync_roster(
            db,
            client,
            integration.course_id,
            integration.canvas_course_id,
            send_invite_emails=False,
            preserve_user_ids={integration.connected_by_user_id},
        )
        db.add(
            CanvasSyncEvent(
                course_id=integration.course_id,
                event_type="roster_diff",
                payload={
                    "added": diff.added,
                    "unchanged": diff.unchanged,
                    "dropped": diff.dropped,
                    "pending": diff.pending,
                    "skipped_off_domain": diff.skipped_off_domain,
                },
            )
        )
        integration.last_roster_sync_at = now
        await db.commit()
    except Exception:  # noqa: BLE001 - we want to log + continue
        logger.exception("Roster sync failed for integration %s", integration.id)
        # Never write raw exception text to CanvasSyncEvent.payload — it's
        # exposed to instructors via the sync-events endpoint and can leak
        # stack frames, IDs, or internal hostnames. Store a stable code +
        # a generic human message only.
        db.add(
            CanvasSyncEvent(
                course_id=integration.course_id,
                event_type="error",
                payload={
                    "stage": "roster_diff",
                    "code": "internal_error",
                    "message": "Roster sync failed. Please try again later.",
                },
            )
        )
        await db.commit()

    # File scan — count Canvas files vs already-imported, no auto-import.
    try:
        files = await client.list_course_files(integration.canvas_course_id)
        imported_ids = (
            await db.execute(
                select(Document.canvas_file_id).where(
                    Document.course_id == integration.course_id,
                    Document.canvas_file_id.is_not(None),
                )
            )
        ).scalars().all()
        already = {str(i) for i in imported_ids}
        canvas_ids = {str(f["id"]) for f in files}
        new_in_canvas = canvas_ids - already
        db.add(
            CanvasSyncEvent(
                course_id=integration.course_id,
                event_type="file_scan",
                payload={
                    "canvas_total": len(canvas_ids),
                    "already_imported": len(canvas_ids & already),
                    "new_available": len(new_in_canvas),
                },
            )
        )
        integration.last_file_scan_at = now
        await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("File scan failed for integration %s", integration.id)
        db.add(
            CanvasSyncEvent(
                course_id=integration.course_id,
                event_type="error",
                payload={
                    "stage": "file_scan",
                    "code": "internal_error",
                    "message": "File scan failed. Please try again later.",
                },
            )
        )
        await db.commit()


async def _claim_due_integration(
    db, exclude: set | None = None
) -> CanvasIntegration | None:
    """Atomically claim one due integration.

    ``SELECT ... FOR UPDATE SKIP LOCKED`` ensures concurrent workers (or
    concurrent scheduler iterations within one worker) process disjoint
    sets — a row already locked elsewhere is invisible to the next caller.

    The ``exclude`` set tracks integrations the caller has already
    processed in the current scheduler pass. Without it, a sync that
    errors out — and therefore doesn't advance ``last_roster_sync_at`` —
    would be re-claimed on the next iteration of the same pass and
    retried in a tight loop. Tracking processed IDs in memory preserves
    the original retry-on-error semantics: failures retry every
    ``SCHEDULER_POLL_SECONDS`` (5 min), not every cadence interval (24 h).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=SYNC_INTERVAL_HOURS)
    stmt = (
        select(CanvasIntegration)
        .where(
            CanvasIntegration.sync_status == "active",
            or_(
                CanvasIntegration.last_roster_sync_at.is_(None),
                CanvasIntegration.last_roster_sync_at < cutoff,
            ),
        )
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if exclude:
        stmt = stmt.where(CanvasIntegration.id.notin_(exclude))
    row = (await db.execute(stmt)).scalar_one_or_none()
    return row


async def run_scheduler(shutdown_event: asyncio.Event | None = None) -> None:
    """Long-running scheduler loop. Cancellable via task.cancel()."""
    logger.info("Canvas sync scheduler started")
    while True:
        try:
            async with async_session_factory() as session:
                # Per-pass processed set so an erroring sync (which doesn't
                # bump last_roster_sync_at) isn't re-claimed within the
                # same pass. Cleared at the next pass — failures retry on
                # the next 5-minute scheduler poll.
                processed: set = set()
                while True:
                    integration = await _claim_due_integration(
                        session, exclude=processed
                    )
                    if integration is None:
                        break
                    processed.add(integration.id)
                    try:
                        await sync_integration(session, integration)
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "sync_integration crashed for %s", integration.id
                        )
        except asyncio.CancelledError:
            logger.info("Canvas sync scheduler cancelled")
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Canvas sync scheduler iteration failed")

        try:
            if shutdown_event is not None:
                await asyncio.wait_for(
                    shutdown_event.wait(), timeout=SCHEDULER_POLL_SECONDS
                )
                if shutdown_event.is_set():
                    return
            else:
                await asyncio.sleep(SCHEDULER_POLL_SECONDS)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            logger.info("Canvas sync scheduler cancelled")
            raise
