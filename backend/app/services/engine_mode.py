"""Resolve effective adaptive-engine mode for a (user, course) pair.

Resolution order:
1. ``engine_overrides`` row → mode ('on'|'off')
2. ``courses.adaptive_engine_mode`` → 'on' | 'off' | 'random_50'
3. random_50 → deterministic hash of (user_id, course_id) → 'on' | 'off'

The deterministic hash uses ``blake2b`` (not Python's ``hash()``, which is
randomised per interpreter and would re-bucket users every restart).
"""
from __future__ import annotations

import hashlib
import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course, EngineOverride

ResolvedMode = Literal["on", "off"]


def _coin_flip_random_50(user_id: uuid.UUID, course_id: uuid.UUID) -> ResolvedMode:
    """Deterministically map (user, course) → 'on' or 'off'.

    Hash input: user_id.bytes (16 bytes) || course_id.bytes (16 bytes).
    Order is a permanent contract — changing it would re-bucket all students
    and corrupt historical action_outcomes cohort assignments.
    """
    h = hashlib.blake2b(digest_size=8)
    h.update(user_id.bytes)
    h.update(course_id.bytes)
    return "on" if int.from_bytes(h.digest(), "big") % 2 == 0 else "off"


async def resolve_engine_mode(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
) -> ResolvedMode:
    override = (
        await db.execute(
            select(EngineOverride.mode).where(
                EngineOverride.user_id == user_id,
                EngineOverride.course_id == course_id,
            )
        )
    ).scalar_one_or_none()
    if override is not None:
        return override  # 'on' | 'off' (CHECK constrains values)

    course_mode = (
        await db.execute(
            select(Course.adaptive_engine_mode).where(Course.id == course_id)
        )
    ).scalar_one_or_none()
    if course_mode is None:
        # Course is NOT NULL on the column, so None means the row is missing.
        # Surface stale/invalid course IDs instead of silently disabling the engine.
        raise ValueError(f"Course {course_id} not found — cannot resolve engine mode")
    if course_mode == "off":
        return "off"
    if course_mode == "on":
        return "on"
    # course_mode == 'random_50'
    return _coin_flip_random_50(user_id, course_id)
