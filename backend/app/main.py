import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config import settings
from app.middleware import AuthMiddleware, RateLimitMiddleware
from app.services.worker import worker_loop

logging.basicConfig(level=logging.INFO)


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

# Auth is handled by FastAPI dependency injection (get_current_user in deps.py).
# Rate limiting only applies to /api/rag/* endpoints.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
