import asyncio
import hashlib
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

import sqlalchemy as sa
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.api_usage import ApiUsage
from app.models.cron_run import CronRun
from app.models.task import Task
from app.services.storage import delete_file_safe

logger = logging.getLogger(__name__)

# Redact any URL that embeds credentials (``scheme://user[:pass]@host...``)
# before it reaches tasks.error_message. Previously this only matched
# postgres(ql) URIs, but failures from redis, mongodb, amqp, s3, http, etc.
# can all surface bearer creds the same way. Requiring a userinfo segment
# (``...@host``) keeps the pattern tight so innocuous URLs without
# credentials are left untouched.
_DB_URL_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+\-.]*://[^\s/@]+@\S+")


def _sanitize_error_message(exc: BaseException) -> str:
    """Return a bounded, redacted string suitable for tasks.error_message.

    - Prefixes with the exception class name so failure triage still works.
    - Drops credential-bearing URLs entirely (no password leaks).
    - Truncates to keep the column small and avoid logging blobs of internals.
    """
    raw = str(exc)
    redacted = _DB_URL_RE.sub("<redacted-url>", raw)
    if len(redacted) > 200:
        redacted = redacted[:200]
    return f"{type(exc).__name__}: {redacted}"

POLL_INTERVAL_SECONDS = 5
# Tasks stuck in "running" beyond this threshold (e.g., because the worker
# crashed mid-processing) are reset to "pending" so another attempt can claim
# them. Tuned against real parser timings: Docling on ~30-page PDFs finishes
# in under a minute, chunking + embedding adds another minute at most. A
# 10-minute ceiling catches genuine crashes quickly while still leaving
# headroom for unusually large Canvas imports.
STUCK_TASK_TIMEOUT = timedelta(minutes=10)
# Grace period before a document stuck in ``processing`` without a live task
# is tombstoned. Kept short so the UI's "processing" spinner surfaces real
# problems to instructors quickly; the ``AND NOT EXISTS`` clause on live
# tasks already protects in-flight uploads, so this mostly guards against
# the narrow window between upload-endpoint commit and task enqueue.
ORPHAN_DOC_GRACE = timedelta(minutes=5)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _reset_stuck_tasks(session: AsyncSession) -> None:
    """Reclaim tasks whose worker crashed before completion.

    Tasks that still have retry budget are returned to ``pending`` so another
    worker can claim them. Tasks that have already exhausted ``max_attempts``
    are marked ``failed`` outright — otherwise the next ``claim_task`` would
    skip them (claim filters by ``attempts < max_attempts``) and they would
    oscillate between ``running`` and ``pending`` forever.
    """
    cutoff = _utcnow() - STUCK_TASK_TIMEOUT
    requeued = await session.execute(
        update(Task)
        .where(
            Task.status == "running",
            Task.started_at.is_not(None),
            Task.started_at < cutoff,
            Task.attempts < Task.max_attempts,
        )
        .values(status="pending")
    )
    failed = await session.execute(
        update(Task)
        .where(
            Task.status == "running",
            Task.started_at.is_not(None),
            Task.started_at < cutoff,
            Task.attempts >= Task.max_attempts,
        )
        .values(status="failed")
    )
    await session.commit()
    # Log only when we actually touched rows so the steady-state worker loop
    # stays quiet but stuck-task events surface in logs for triage.
    if requeued.rowcount or failed.rowcount:
        logger.info(
            "Reclaimed stuck tasks: requeued=%d failed=%d (threshold=%sm)",
            requeued.rowcount or 0,
            failed.rowcount or 0,
            int(STUCK_TASK_TIMEOUT.total_seconds() // 60),
        )


async def _reconcile_orphaned_documents(session: AsyncSession) -> None:
    """Tombstone documents that are stuck in 'processing' with no live task.

    Happens when the worker is SIGKILL'd (OOM, forced restart) between
    'task running' and 'task failed' state transitions, or when a task is
    cleared out-of-band. Without this, the UI shows a perpetual spinner
    and re-upload is the user's only recourse.

    We also enforce a grace period: the document upload endpoint commits
    the document row BEFORE uploading to R2 and creating the task row.
    During that window (seconds to tens of seconds for large PDFs) there
    is no task referencing the doc — but it's a valid in-flight upload.
    ``ORPHAN_DOC_GRACE`` is longer than any realistic R2 upload and shorter
    than any tolerable "stuck spinner" experience.
    """
    # Grace in whole seconds so the INTERVAL literal is deterministic.
    grace_seconds = int(ORPHAN_DOC_GRACE.total_seconds())
    # A document is orphaned if status='processing', older than the grace
    # period, and no process_document task referencing it is pending/running.
    result = await session.execute(
        text(
            """
            UPDATE documents
               SET status = 'failed',
                   updated_at = now()
             WHERE status = 'processing'
               AND deleted_at IS NULL
               AND updated_at < now() - make_interval(secs => :grace_seconds)
               AND NOT EXISTS (
                   SELECT 1 FROM tasks t
                    WHERE t.task_type = 'process_document'
                      AND (t.payload->>'document_id')::uuid = documents.id
                      AND t.status IN ('pending', 'running')
               )
         RETURNING r2_key
            """
        ),
        {"grace_seconds": grace_seconds},
    )
    orphan_keys = [row[0] for row in result.fetchall() if row[0]]
    await session.commit()
    # Reclaim R2 storage for the orphans. Best-effort: delete_file_safe
    # swallows errors so a missing key can't undo the DB tombstone.
    for r2_key in orphan_keys:
        await delete_file_safe(r2_key)
    if orphan_keys:
        logger.info(
            "Tombstoned orphaned processing documents: count=%d (grace=%ds)",
            len(orphan_keys),
            grace_seconds,
        )


async def mark_overdue_submissions(session: AsyncSession) -> int:
    """Daily-cron job: flip 'not_started'/'in_progress' rows past their
    assignment's due_at to 'late'. Idempotent."""
    from app.models import Assignment, AssignmentSubmission

    now = _utcnow()
    rows = (
        await session.execute(
            select(AssignmentSubmission, Assignment)
            .join(Assignment, AssignmentSubmission.assignment_id == Assignment.id)
            .where(
                Assignment.due_at < now,
                Assignment.deleted_at.is_(None),
                AssignmentSubmission.status.in_(("not_started", "in_progress")),
            )
        )
    ).all()
    n = 0
    for sub, _asn in rows:
        sub.status = "late"
        n += 1
    if n:
        await session.commit()
        logger.info("Marked %d submissions as late", n)
    return n


async def prune_api_usage() -> int:
    """Delete ``api_usage`` rows older than the rate-limit window (2 h).

    Rate limiting only reads rows from the last hour; keeping a 2-hour
    retention buffer provides slack for clock skew and long-running windows
    while still bounding growth on this high-churn table.
    """
    async with async_session_factory() as session:
        cutoff = _utcnow() - timedelta(hours=2)
        result = await session.execute(
            sa.delete(ApiUsage).where(ApiUsage.created_at < cutoff)
        )
        await session.commit()
        return result.rowcount or 0


async def prune_nonces_and_usage() -> None:
    """Run the hourly cleanup job: api_usage + expired OAuth nonces.

    Wrapped in a broad ``try/except`` so a transient DB error can't kill the
    worker loop — the next hourly tick will retry.
    """
    try:
        # Imported locally to avoid pulling canvas_oauth (+ jwt, httpx) into
        # the worker's import graph for installations that don't use Canvas.
        from app.services.canvas_oauth import prune_expired_nonces

        async with async_session_factory() as session:
            nonces = await prune_expired_nonces(session)
        usage = await prune_api_usage()
        logger.info("Prune: api_usage=%d nonces=%d", usage, nonces)
    except Exception:  # noqa: BLE001
        logger.exception("Prune job failed")


async def claim_task(session: AsyncSession) -> Task | None:
    result = await session.execute(
        select(Task)
        .where(Task.status == "pending", Task.attempts < Task.max_attempts)
        .order_by(Task.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    task = result.scalar_one_or_none()
    if task:
        task.status = "running"
        task.attempts += 1
        task.started_at = _utcnow()
        await session.commit()
        await session.refresh(task)
        # Detach so callers can re-load the task in a fresh session.
        session.expunge(task)
    return task


async def complete_task(
    session: AsyncSession,
    task_id,
    result: dict | None = None,
) -> None:
    result_row = await session.execute(select(Task).where(Task.id == task_id))
    task = result_row.scalar_one_or_none()
    if task is None:
        return
    task.status = "completed"
    task.completed_at = _utcnow()
    if result is not None:
        # Reassign the whole dict so SQLAlchemy sees the JSON column as dirty.
        task.payload = {**(task.payload or {}), "result": result}
    await session.commit()


async def fail_task(session: AsyncSession, task_id, error: str) -> None:
    result = await session.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        return
    permanently_failed = task.attempts >= task.max_attempts
    task.status = "failed" if permanently_failed else "pending"
    task.error_message = error

    orphan_r2_key: str | None = None
    if permanently_failed and task.task_type == "process_document":
        document_id = task.payload.get("document_id")
        if document_id:
            # Wrap document update in its own try/except so a missing or
            # concurrently-modified document can't prevent the task status
            # transition from being persisted.
            try:
                from app.models.document import Document

                doc_id = (
                    uuid.UUID(document_id)
                    if isinstance(document_id, str)
                    else document_id
                )
                doc_result = await session.execute(
                    select(Document).where(Document.id == doc_id)
                )
                doc = doc_result.scalar_one_or_none()
                if doc:
                    doc.status = "failed"
                    # Capture r2_key before commit so we can reclaim storage
                    # once the tombstone is durable. A permanently-failed doc
                    # can't be retried, so the uploaded bytes are dead weight.
                    orphan_r2_key = doc.r2_key
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Could not tombstone document %s on failed task", document_id
                )

    await session.commit()
    if orphan_r2_key:
        await delete_file_safe(orphan_r2_key)


async def process_task(session: AsyncSession, task: Task) -> dict | None:
    """Execute a task. Returns an optional result dict for completed jobs."""
    if task.task_type == "process_document":
        from app.services.pipeline import process_document_pipeline
        document_id = task.payload.get("document_id")
        if not document_id:
            raise ValueError("Missing document_id in task payload")
        await process_document_pipeline(session, document_id)
        return None
    elif task.task_type == "revision_pool_replenish":
        from app.services.pool import replenish_pool
        await replenish_pool(session, task.payload)
        return None
    elif task.task_type == "recalibration":
        from app.services.recalibrator import run_recalibration_job
        course_id = task.payload.get("course_id")
        content_type = task.payload.get("content_type")
        if not course_id or not content_type:
            raise ValueError("Missing course_id or content_type in recalibration payload")
        await run_recalibration_job(session, uuid.UUID(course_id), content_type)
        return None
    elif task.task_type in {
        "generate_quiz",
        "generate_flashcards",
        "generate_pronunciation",
        "generate_summary",
    }:
        from app.services.jobs import run_generation_job
        result = await run_generation_job(session, task.task_type, task.payload)
        await session.commit()
        return result
    elif task.task_type == "parse_syllabus":
        from app.services.jobs import run_parse_syllabus
        result = await run_parse_syllabus(session, task.payload)
        return result
    elif task.task_type == "extract_concept_candidates":
        from app.services.adaptive_jobs import run_extract_concept_candidates
        return await run_extract_concept_candidates(session, task.payload)
    elif task.task_type == "tag_artifact_concepts":
        from app.services.adaptive_jobs import run_tag_artifact_concepts
        return await run_tag_artifact_concepts(session, task.payload)
    elif task.task_type == "update_concept_mastery":
        from app.services.adaptive_jobs import run_update_concept_mastery
        # Inject the task's enqueue time so the handler can dedupe on retry
        # (see I-1 fix). Use a ``_`` prefix to mark the key as system-injected
        # rather than caller-provided. If a stuck-task reset re-runs this
        # Task, the second invocation will see a ConceptMasteryHistory row
        # whose ``recorded_at >= task.created_at`` and skip the update.
        return await run_update_concept_mastery(
            session,
            {**task.payload, "_task_created_at": task.created_at.isoformat()},
        )
    elif task.task_type == "replay_attempt_history":
        # Backfill job: re-applies the last N days of attempts through
        # mastery. Intentionally *not* watermark-idempotent — operators
        # wipe ConceptMastery first if they want a clean slate. Handler
        # commits internally, mirroring the other concept-job handlers.
        from app.services.adaptive_jobs import run_replay_attempt_history
        return await run_replay_attempt_history(session, task.payload)
    elif task.task_type == "evaluate_instructor_alerts":
        from app.services.adaptive_jobs import run_evaluate_instructor_alerts
        return await run_evaluate_instructor_alerts(session, task.payload)
    elif task.task_type == "draft_learning_notes":
        from app.services.adaptive_jobs import run_draft_learning_notes
        return await run_draft_learning_notes(session, task.payload)
    elif task.task_type == "analyze_course_setup":
        # Read-only course-map + missing-source aggregation (setup wizard
        # T019/T028). Result is returned so complete_task stores it under
        # tasks.payload['result'] for GET .../setup/analysis to read back.
        from app.services.setup_analysis import run_analyze_course_setup
        return await run_analyze_course_setup(session, task.payload)
    else:
        raise ValueError(f"Unknown task type: {task.task_type}")


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
# How long before a stale ``last_success_at`` reading allows a kick-off
# even with cadence still nominally not elapsed. Unused — semantics rely on
# cadence comparison alone — kept for documentation symmetry.


def _cron_lock_key(name: str) -> int:
    """Stable 63-bit advisory-lock key for a cron-name. Salted so it can't
    collide with course/concept advisory locks elsewhere in the codebase."""
    h = hashlib.blake2b(digest_size=8)
    h.update(name.encode("utf-8"))
    h.update(b"cron_run")
    return int.from_bytes(h.digest(), "big") & 0x7FFFFFFFFFFFFFFF


async def _claim_and_run_cron(
    name: str,
    cadence: timedelta,
    body: Callable[[], Awaitable[None]],
) -> None:
    """Run ``body()`` if the cron is due; advance ``last_success_at`` only
    after the body returns successfully.

    Acquires a per-name transaction-scoped advisory lock that is held across
    the cadence check, the body run, and the watermark advance. Concurrent
    workers calling the same cron either skip immediately
    (``pg_try_advisory_xact_lock`` returns false) or — once the holder
    commits — see the freshly-bumped watermark and skip on cadence. A
    failure in ``body`` raises through, the surrounding rollback releases
    the lock, and ``last_success_at`` stays where it was so the next tick
    retries instead of waiting a full cadence interval.
    """
    lock_key = _cron_lock_key(name)
    # Lazy seed in its own transaction so a body failure later doesn't
    # roll the seed row back. Subsequent boots see the persisted row.
    async with async_session_factory() as seed_session:
        await seed_session.execute(
            pg_insert(CronRun)
            .values(name=name, last_success_at=_EPOCH)
            .on_conflict_do_nothing(index_elements=["name"])
        )
        await seed_session.commit()

    async with async_session_factory() as s:
        held = (
            await s.execute(
                text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": lock_key}
            )
        ).scalar_one()
        if not held:
            return

        last = (
            await s.execute(
                select(CronRun.last_success_at).where(CronRun.name == name)
            )
        ).scalar_one()
        now = _utcnow()
        if now - last < cadence:
            await s.commit()  # release lock, nothing to do
            return

        body_ok = False
        try:
            await body()
            body_ok = True
        except Exception:  # noqa: BLE001
            logger.exception(
                "Cron %s body failed; watermark NOT advanced", name
            )

        if body_ok:
            await s.execute(
                update(CronRun)
                .where(CronRun.name == name)
                .values(last_success_at=now)
            )
        # Commit either way to release the advisory lock without thrashing
        # the seed row. ``last_success_at`` only moves on success.
        await s.commit()


async def _body_stuck_reset() -> None:
    async with async_session_factory() as session:
        await _reset_stuck_tasks(session)
        await _reconcile_orphaned_documents(session)


async def _body_overdue() -> None:
    async with async_session_factory() as session:
        await mark_overdue_submissions(session)


async def _body_decay() -> None:
    from app.services.mastery import decay_due_mastery_rows

    async with async_session_factory() as session:
        n = await decay_due_mastery_rows(session)
        logger.info("HLR decay touched %d mastery rows", n)


async def _body_alerts_enqueue() -> None:
    from app.models import Course

    async with async_session_factory() as session:
        ids = (
            await session.execute(
                select(Course.id).where(Course.deleted_at.is_(None))
            )
        ).scalars().all()
        for cid in ids:
            session.add(
                Task(
                    task_type="evaluate_instructor_alerts",
                    payload={"course_id": str(cid)},
                    status="pending",
                )
            )
            # Note drafting is batch/periodic (not per-attempt): the hourly
            # alert cron also seeds a draft_learning_notes pass per course so
            # AI drafts are produced off the request path for instructors to
            # review.
            session.add(
                Task(
                    task_type="draft_learning_notes",
                    payload={"course_id": str(cid)},
                    status="pending",
                )
            )
        await session.commit()


async def _process_claimed_task(task: Task) -> None:
    """Process a single claimed task in fresh sessions.

    Process and complete in fresh sessions so pipeline-internal commits
    (and any rollback they trigger) can't leave the claim session in an
    undefined state that would break ``fail_task``.
    """
    task_id = task.id
    logger.info(
        "Processing task %s (type=%s, attempt=%s)",
        task_id, task.task_type, task.attempts,
    )
    try:
        task_result: dict | None = None
        async with async_session_factory() as process_session:
            reloaded = await process_session.get(Task, task_id)
            if reloaded is None:
                # Row vanished between claim and process. There's no row
                # left to leave "running", but log loudly — this is
                # unexpected outside of explicit admin deletion.
                logger.error("Task %s disappeared after claim; skipping", task_id)
                return
            task_result = await process_task(process_session, reloaded)

        async with async_session_factory() as complete_session:
            await complete_task(complete_session, task_id, task_result)
        logger.info("Task %s completed", task_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Task %s failed", task_id)
        try:
            async with async_session_factory() as fail_session:
                await fail_task(
                    fail_session, task_id, _sanitize_error_message(exc)
                )
        except Exception:  # noqa: BLE001
            logger.exception("fail_task itself failed for %s", task_id)


async def _run_cron_ticks() -> None:
    """Run all due cron ticks in canonical order. Each call goes through
    ``_claim_and_run_cron`` which checks ``cron_runs.last_success_at``,
    serializes via advisory lock, and only advances the watermark on
    success. Any single failure is logged but doesn't abort the rest."""
    await _claim_and_run_cron("stuck_reset", timedelta(minutes=5), _body_stuck_reset)
    await _claim_and_run_cron("prune", timedelta(hours=1), prune_nonces_and_usage)
    await _claim_and_run_cron("overdue", timedelta(hours=24), _body_overdue)
    await _claim_and_run_cron("decay", timedelta(hours=24), _body_decay)
    await _claim_and_run_cron("alert", timedelta(hours=1), _body_alerts_enqueue)


async def worker_loop(shutdown_event: asyncio.Event) -> None:
    logger.info("Task worker started")
    while not shutdown_event.is_set():
        try:
            await _run_cron_ticks()
            # Short-lived claim session so we don't hold a DB connection
            # open during the full processing pipeline.
            async with async_session_factory() as claim_session:
                task = await claim_task(claim_session)
            if task is None:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue
            await _process_claimed_task(task)
        except Exception:  # noqa: BLE001
            logger.exception("Worker loop error")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    logger.info("Task worker shutting down")
