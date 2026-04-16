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


@event.listens_for(engine.sync_engine, "checkout")
def _reset_rls_context(dbapi_conn, connection_record, connection_proxy):
    """Reset the per-request RLS GUC on every pool checkout so that
    ``app.current_user_id`` cannot leak from a prior request whose transaction
    committed the value at the session level."""
    cursor = dbapi_conn.cursor()
    try:
        cursor.execute("SELECT set_config('app.current_user_id', '', false)")
    finally:
        cursor.close()


async def get_db():
    # `async with` already handles close() on exit — no explicit finally needed.
    async with async_session_factory() as session:
        yield session
