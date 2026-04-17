import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_current_user_id_reset_on_checkout(async_engine):
    async with async_engine.connect() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_user_id', 'user-a', false)")
        )
        v = (await conn.execute(text("SHOW app.current_user_id"))).scalar()
        assert v == "user-a"
        # Commit so the GUC persists past the implicit transaction, simulating
        # a real request where the session commits before releasing the
        # connection back to the pool.
        await conn.commit()
    async with async_engine.connect() as conn:
        v = (await conn.execute(text("SHOW app.current_user_id"))).scalar()
        assert v in ("", None)
