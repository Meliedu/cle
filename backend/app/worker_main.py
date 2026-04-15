"""Standalone worker entrypoint.

Runs the document-processing worker + Canvas sync scheduler without the
FastAPI app. Deployed as its own Railway service so a parser/embedder OOM
can't take down the API.

Start command: `python -m app.worker_main`
"""

from __future__ import annotations

import asyncio
import logging
import signal

from app.services.canvas_sync import run_scheduler as run_canvas_scheduler
from app.services.worker import worker_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
for _noisy in ("botocore", "boto3", "urllib3", "s3transfer", "httpx", "httpcore"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger("app.worker_main")


async def _run() -> None:
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _request_shutdown() -> None:
        if not shutdown_event.is_set():
            logger.info("Shutdown signal received")
            shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except NotImplementedError:
            # Windows / restricted envs — fall back to default handling.
            pass

    logger.info("Standalone worker starting")
    tasks = [
        asyncio.create_task(worker_loop(shutdown_event), name="worker_loop"),
        asyncio.create_task(run_canvas_scheduler(shutdown_event), name="canvas_sync"),
    ]
    await shutdown_event.wait()
    for task in tasks:
        task.cancel()
    for task in tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass
    logger.info("Standalone worker stopped")


if __name__ == "__main__":
    asyncio.run(_run())
