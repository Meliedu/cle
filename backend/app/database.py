from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


def _is_local(url: str) -> bool:
    return "localhost" in url or "127.0.0.1" in url


_engine_kwargs: dict = {
    "pool_size": 5,
    "max_overflow": 5,
    "pool_timeout": 30,
    "pool_pre_ping": True,
    "echo": False,
}

if not _is_local(settings.database_url):
    _engine_kwargs["connect_args"] = {"ssl": "require"}

engine = create_async_engine(settings.database_url, **_engine_kwargs)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _blank_rls_guc(dbapi_conn) -> None:
    """Reset the session-scoped RLS GUC ``app.current_user_id`` to blank.

    ``get_current_user`` sets this GUC with ``set_config(..., false)`` (session
    scope, NOT transaction scope — its multi-commit flow would drop a
    transaction-local value before RLS reads), so a committed value can outlive
    the request on a POOLED physical connection. Blanking it makes any later RLS
    read fail CLOSED: ``current_setting('app.current_user_id', true)::uuid`` on a
    blank GUC raises rather than exposing a prior request's rows.
    """
    cursor = dbapi_conn.cursor()
    try:
        cursor.execute("SELECT set_config('app.current_user_id', '', false)")
    finally:
        cursor.close()


@event.listens_for(engine.sync_engine, "checkout")
def _reset_rls_context(dbapi_conn, connection_record, connection_proxy):
    """Reset the per-request RLS GUC on every pool checkout so that
    ``app.current_user_id`` cannot leak from a prior request whose transaction
    committed the value at the session level. Tracked finding: pooled-connection
    RLS GUC (P2 Task 8)."""
    _blank_rls_guc(dbapi_conn)


@event.listens_for(engine.sync_engine, "checkin")
def _reset_rls_on_checkin(dbapi_conn, connection_record):
    """Symmetric to ``_reset_rls_context``: also blank the RLS GUC when a
    connection RETURNS to the pool, so a request-set value never lingers in an
    idle pooled connection between requests (defense-in-depth, P7 B10 /
    Decision 7). We deliberately keep the GUC SESSION-scoped in ``deps.py`` (not
    transaction-scoped) and reset on BOTH ends of the pool cycle — the correct
    minimal fix for the tracked pooled-connection RLS GUC finding (P2 Task 8)."""
    _blank_rls_guc(dbapi_conn)


async def get_db():
    # `async with` already handles close() on exit — no explicit finally needed.
    async with async_session_factory() as session:
        yield session
