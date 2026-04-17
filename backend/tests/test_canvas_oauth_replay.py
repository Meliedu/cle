"""Postgres-backed nonce replay protection for Canvas OAuth state tokens."""

import pytest

from app.services.canvas_oauth import _consume_nonce


@pytest.mark.asyncio
async def test_nonce_cannot_be_consumed_twice(db_session):
    assert await _consume_nonce(db_session, "nonce-abc", 9999999999) is True
    assert await _consume_nonce(db_session, "nonce-abc", 9999999999) is False


@pytest.mark.asyncio
async def test_different_nonces_both_consumed(db_session):
    assert await _consume_nonce(db_session, "nonce-xyz", 9999999999) is True
    assert await _consume_nonce(db_session, "nonce-pqr", 9999999999) is True
