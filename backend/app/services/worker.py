import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.task import Task

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5


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
        task.started_at = datetime.utcnow()
        await session.commit()
        await session.refresh(task)
    return task


async def complete_task(session: AsyncSession, task: Task) -> None:
    task.status = "completed"
    task.completed_at = datetime.utcnow()
    await session.commit()


async def fail_task(session: AsyncSession, task: Task, error: str) -> None:
    task.status = "failed" if task.attempts >= task.max_attempts else "pending"
    task.error_message = error
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
    else:
        raise ValueError(f"Unknown task type: {task.task_type}")


async def worker_loop(shutdown_event: asyncio.Event) -> None:
    logger.info("Task worker started")
    while not shutdown_event.is_set():
        try:
            async with async_session_factory() as session:
                task = await claim_task(session)
                if task:
                    logger.info(f"Processing task {task.id} (type={task.task_type}, attempt={task.attempts})")
                    try:
                        await process_task(session, task)
                        await complete_task(session, task)
                        logger.info(f"Task {task.id} completed")
                    except Exception as e:
                        logger.error(f"Task {task.id} failed: {e}")
                        await fail_task(session, task, str(e))
                else:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
        except Exception as e:
            logger.error(f"Worker error: {e}")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    logger.info("Task worker shutting down")
