import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import api_router
from app.config import settings
from app.middleware import AuthMiddleware, RateLimitMiddleware
from app.services.canvas_sync import run_scheduler as run_canvas_scheduler
from app.services.worker import worker_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
# Tame noisy third-party loggers that default to INFO.
for _noisy in ("botocore", "boto3", "urllib3", "s3transfer", "httpx", "httpcore"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    shutdown_event = asyncio.Event()
    worker_task = asyncio.create_task(worker_loop(shutdown_event))
    scheduler_task = asyncio.create_task(run_canvas_scheduler(shutdown_event))
    yield
    shutdown_event.set()
    worker_task.cancel()
    scheduler_task.cancel()
    for task in (worker_task, scheduler_task):
        try:
            await task
        except asyncio.CancelledError:
            pass


_is_production = settings.environment == "production"

app = FastAPI(
    title="Meli API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    """Log full traceback server-side, return generic envelope to clients."""
    logger = logging.getLogger("app.errors")
    logger.exception("Unhandled exception: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred.",
            },
        },
    )

# AuthMiddleware does a fast Bearer-token check to reject unauthenticated
# /api/* traffic before it reaches routing/DB. Full JWT verification still
# happens in app.api.deps.get_current_user.
# Rate limiting only applies to /api/rag/* endpoints.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(api_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
