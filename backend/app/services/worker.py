import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
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


async def _reset_stuck_tasks(session: AsyncSession) -> None:
    """Reclaim tasks whose worker crashed before completion."""
    cutoff = datetime.now(timezone.utc) - STUCK_TASK_TIMEOUT
    await session.execute(
        update(Task)
        .where(Task.status == "running", Task.started_at < cutoff)
        .values(status="pending")
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
        task.started_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(task)
    return task


async def complete_task(session: AsyncSession, task: Task) -> None:
    task.status = "completed"
    task.completed_at = datetime.now(timezone.utc)
    await session.commit()


async def fail_task(session: AsyncSession, task: Task, error: str) -> None:
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

                result = await session.execute(
                    select(Document).where(Document.id == uuid.UUID(document_id))
                )
                doc = result.scalar_one_or_none()
                if doc:
                    doc.status = "failed"
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Could not tombstone document %s on failed task", document_id
                )

    await session.commit()


async def process_task(session: AsyncSession, task: Task) -> None:
    if task.task_type == "process_document":
        from app.services.pipeline import process_document_pipeline
        document_id = task.payload.get("document_id")
        if not document_id:
            raise ValueError("Missing document_id in task payload")
        await process_document_pipeline(session, document_id)
    elif task.task_type == "revision_pool_replenish":
        from app.services.pool import replenish_pool
        await replenish_pool(session, task.payload)
    elif task.task_type == "recalibration":
        from app.services.recalibrator import run_recalibration_job
        course_id = task.payload.get("course_id")
        content_type = task.payload.get("content_type")
        if not course_id or not content_type:
            raise ValueError("Missing course_id or content_type in recalibration payload")
        await run_recalibration_job(session, uuid.UUID(course_id), content_type)
    else:
        raise ValueError(f"Unknown task type: {task.task_type}")


async def worker_loop(shutdown_event: asyncio.Event) -> None:
    logger.info("Task worker started")
    last_stuck_reset = datetime.now(timezone.utc) - timedelta(hours=1)

    while not shutdown_event.is_set():
        try:
            # Periodically reset stuck tasks (every ~5 min).
            if datetime.now(timezone.utc) - last_stuck_reset > timedelta(minutes=5):
                try:
                    async with async_session_factory() as reset_session:
                        await _reset_stuck_tasks(reset_session)
                except Exception:  # noqa: BLE001
                    logger.exception("Failed to reset stuck tasks")
                last_stuck_reset = datetime.now(timezone.utc)

            # Claim a task in its own session so the per-task transaction
            # boundary is well defined.
            task_id = None
            async with async_session_factory() as claim_session:
                task = await claim_task(claim_session)
                if task:
                    task_id = task.id
                    task_type = task.task_type
                    attempts = task.attempts
                    logger.info(
                        f"Processing task {task_id} (type={task_type}, attempt={attempts})"
                    )

            if task_id is None:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            # Process and complete in fresh sessions so that pipeline-internal
            # commits (and any rollback they trigger) can't leave the claim
            # session in an undefined state that breaks fail_task.
            try:
                async with async_session_factory() as process_session:
                    reloaded = await process_session.get(Task, task_id)
                    if reloaded is None:
                        logger.warning("Task %s disappeared mid-flight", task_id)
                        continue
                    await process_task(process_session, reloaded)

                async with async_session_factory() as complete_session:
                    reloaded = await complete_session.get(Task, task_id)
                    if reloaded is not None:
                        await complete_task(complete_session, reloaded)
                logger.info(f"Task {task_id} completed")
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Task {task_id} failed: {exc}")
                try:
                    async with async_session_factory() as fail_session:
                        reloaded = await fail_session.get(Task, task_id)
                        if reloaded is not None:
                            await fail_task(fail_session, reloaded, str(exc))
                except Exception:  # noqa: BLE001
                    logger.exception("fail_task itself failed for %s", task_id)

        except Exception as e:  # noqa: BLE001
            logger.error(f"Worker error: {e}")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    logger.info("Task worker shutting down")
