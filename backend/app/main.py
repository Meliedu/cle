import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config import settings
from app.middleware import AuthMiddleware, RateLimitMiddleware
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
    yield
    shutdown_event.set()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Meli API", version="0.1.0", lifespan=lifespan)

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
