"""Coefficient retune stub — filled in Task 17."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


async def retune_action_coefficients(
    db: AsyncSession, *, window_days: int
) -> dict:
    return {"window_days": window_days, "stub": True}
