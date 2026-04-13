import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.task import Task

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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


async def complete_task(session: AsyncSession, task_id) -> None:
    result = await session.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        return
    task.status = "completed"
    task.completed_at = _utcnow()
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
            from app.models.document import Document
            doc_result = await session.execute(
                select(Document).where(Document.id == document_id)
            )
            doc = doc_result.scalar_one_or_none()
            if doc:
                doc.status = "failed"

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
        from uuid import UUID

        from app.services.recalibrator import run_recalibration_job
        course_id = task.payload.get("course_id")
        content_type = task.payload.get("content_type")
        if not course_id or not content_type:
            raise ValueError("Missing course_id or content_type in recalibration payload")
        await run_recalibration_job(session, UUID(course_id), content_type)
    else:
        raise ValueError(f"Unknown task type: {task.task_type}")


async def worker_loop(shutdown_event: asyncio.Event) -> None:
    logger.info("Task worker started")
    while not shutdown_event.is_set():
        try:
            # Use a short-lived session just to claim the task, so we don't
            # hold a DB connection open during the full processing pipeline.
            async with async_session_factory() as claim_session:
                task = await claim_task(claim_session)

            if task is None:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            logger.info(
                "Processing task %s (type=%s, attempt=%s)",
                task.id, task.task_type, task.attempts,
            )

            # Fresh session for the work itself.
            async with async_session_factory() as work_session:
                try:
                    await process_task(work_session, task)
                    await complete_task(work_session, task.id)
                    logger.info("Task %s completed", task.id)
                except Exception as e:
                    logger.exception("Task %s failed", task.id)
                    await work_session.rollback()
                    async with async_session_factory() as fail_session:
                        await fail_task(fail_session, task.id, str(e))
        except Exception:
            logger.exception("Worker loop error")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    logger.info("Task worker shutting down")
