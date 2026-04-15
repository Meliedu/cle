import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.task import Task

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5
# Tasks stuck in "running" beyond this threshold (e.g., because the worker
# crashed mid-processing) are reset to "pending" so another attempt can claim
# them. Worth being generous here — document processing with large PDFs and
# embeddings can run for several minutes.
STUCK_TASK_TIMEOUT = timedelta(minutes=30)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _reset_stuck_tasks(session: AsyncSession) -> None:
    """Reclaim tasks whose worker crashed before completion."""
    cutoff = _utcnow() - STUCK_TASK_TIMEOUT
    await session.execute(
        update(Task)
        .where(
            Task.status == "running",
            Task.started_at.is_not(None),
            Task.started_at < cutoff,
        )
        .values(status="pending")
    )
    await session.commit()


async def _reconcile_orphaned_documents(session: AsyncSession) -> None:
    """Tombstone documents that are stuck in 'processing' with no live task.

    Happens when the worker is SIGKILL'd (OOM, forced restart) between
    'task running' and 'task failed' state transitions, or when a task is
    cleared out-of-band. Without this, the UI shows a perpetual spinner
    and re-upload is the user's only recourse.
    """
    from app.models.document import Document

    # A document is orphaned if status='processing' but no task of type
    # process_document referencing it is currently pending or running.
    await session.execute(
        text(
            """
            UPDATE documents
               SET status = 'failed',
                   updated_at = now()
             WHERE status = 'processing'
               AND deleted_at IS NULL
               AND NOT EXISTS (
                   SELECT 1 FROM tasks t
                    WHERE t.task_type = 'process_document'
                      AND (t.payload->>'document_id')::uuid = documents.id
                      AND t.status IN ('pending', 'running')
               )
            """
        )
    )
    await session.commit()


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
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Could not tombstone document %s on failed task", document_id
                )

    await session.commit()


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
    elif task.task_type in {"generate_quiz", "generate_flashcards", "generate_summary"}:
        from app.services.jobs import run_generation_job
        result = await run_generation_job(session, task.task_type, task.payload)
        await session.commit()
        return result
    else:
        raise ValueError(f"Unknown task type: {task.task_type}")


async def worker_loop(shutdown_event: asyncio.Event) -> None:
    logger.info("Task worker started")
    last_stuck_reset = _utcnow() - timedelta(hours=1)

    while not shutdown_event.is_set():
        try:
            # Periodically reset stuck tasks + reconcile orphaned docs.
            if _utcnow() - last_stuck_reset > timedelta(minutes=5):
                try:
                    async with async_session_factory() as reset_session:
                        await _reset_stuck_tasks(reset_session)
                        await _reconcile_orphaned_documents(reset_session)
                except Exception:  # noqa: BLE001
                    logger.exception("Failed to run reconciliation")
                last_stuck_reset = _utcnow()

            # Short-lived claim session so we don't hold a DB connection open
            # during the full processing pipeline.
            async with async_session_factory() as claim_session:
                task = await claim_task(claim_session)

            if task is None:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            task_id = task.id
            logger.info(
                "Processing task %s (type=%s, attempt=%s)",
                task_id, task.task_type, task.attempts,
            )

            # Process and complete in fresh sessions so that pipeline-internal
            # commits (and any rollback they trigger) can't leave the claim
            # session in an undefined state that breaks fail_task.
            try:
                task_result: dict | None = None
                async with async_session_factory() as process_session:
                    reloaded = await process_session.get(Task, task_id)
                    if reloaded is None:
                        # Row vanished between claim and process. There's no row
                        # left to leave "running", but log loudly — this is
                        # unexpected outside of explicit admin deletion.
                        logger.error(
                            "Task %s disappeared after claim; skipping",
                            task_id,
                        )
                        continue
                    task_result = await process_task(process_session, reloaded)

                async with async_session_factory() as complete_session:
                    await complete_task(complete_session, task_id, task_result)
                logger.info("Task %s completed", task_id)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Task %s failed", task_id)
                try:
                    async with async_session_factory() as fail_session:
                        await fail_task(fail_session, task_id, str(exc))
                except Exception:  # noqa: BLE001
                    logger.exception("fail_task itself failed for %s", task_id)

        except Exception:  # noqa: BLE001
            logger.exception("Worker loop error")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    logger.info("Task worker shutting down")
