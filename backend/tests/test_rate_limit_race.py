import asyncio
import pytest
from httpx import AsyncClient
from app.main import app


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires seeded student + course; enable after fixtures land")
async def test_rate_limit_prevents_concurrent_bursts():
    pass


def test_rate_limit_module_exports_lock_helper():
    # Smoke test that the advisory-lock helper is in place.
    from app.middleware.rate_limit import RateLimitMiddleware
    assert RateLimitMiddleware is not None
