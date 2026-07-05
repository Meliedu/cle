"""Integration tests for the nightly HLR-style mastery decay sweep.

These tests exercise ``decay_due_mastery_rows`` end-to-end against the
real test DB to confirm:

1. Rows whose ``last_decay_at`` watermark is older than the cutoff actually
   shrink toward the prior (``α=β=1``).
2. Running the sweep twice in quick succession is a no-op the second time
   — the watermark advances to ``now`` after the first pass so the
   ``last_decay_at < cutoff`` filter excludes those rows next round.

The pure ``hlr_decay_step`` math is covered by unit tests in
``test_mastery_service.py``; these focus on the DB-mutation contract.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.services.mastery import decay_due_mastery_rows


@pytest.mark.asyncio
async def test_decay_shrinks_rows_older_than_24h(db_session, test_instructor):
    from app.models import Concept, ConceptMastery, Course

    course = Course(
        instructor_id=test_instructor.id,
        name="C",
        language="english",
        enroll_code="DC001",
    )
    db_session.add(course)
    await db_session.commit()
    c = Concept(
        course_id=course.id,
        name="X",
        status="approved",
        instructor_curated=True,
    )
    db_session.add(c)
    await db_session.commit()

    # Row has α=11, β=2 (heavily updated 30 days ago, never decayed since).
    far_ago = datetime.now(timezone.utc) - timedelta(days=30)
    row = ConceptMastery(
        user_id=test_instructor.id,
        concept_id=c.id,
        course_id=course.id,
        alpha=Decimal("11.000"),
        beta=Decimal("2.000"),
        confidence=Decimal("0.500"),
        attempt_count=12,
        last_attempt_at=far_ago,
        last_decay_at=far_ago,
        updated_at=far_ago,
    )
    db_session.add(row)
    await db_session.commit()

    touched = await decay_due_mastery_rows(db_session, half_life_days=14)
    assert touched == 1

    # Refresh the ORM instance via the async ``refresh`` API rather than the
    # sync ``expire_all`` — under the shared async session, expired-attribute
    # lazy loads trip ``MissingGreenlet`` (same class of fix as Task 9).
    await db_session.refresh(row)
    # 30 days @ τ=14 → decay ≈ 2^(-30/14) ≈ 0.226
    # excess α = 10 → new α excess ≈ 2.26 → α ≈ 3.26
    assert float(row.alpha) < 5.0
    assert float(row.alpha) > 1.0


@pytest.mark.asyncio
async def test_decay_idempotent_within_day(db_session, test_instructor):
    """Running decay twice within an hour must be a no-op the second run."""
    from app.models import Concept, ConceptMastery, Course

    course = Course(
        instructor_id=test_instructor.id,
        name="C",
        language="english",
        enroll_code="DC002",
    )
    db_session.add(course)
    await db_session.commit()
    c = Concept(
        course_id=course.id,
        name="X",
        status="approved",
        instructor_curated=True,
    )
    db_session.add(c)
    await db_session.commit()

    far_ago = datetime.now(timezone.utc) - timedelta(days=30)
    db_session.add(
        ConceptMastery(
            user_id=test_instructor.id,
            concept_id=c.id,
            course_id=course.id,
            alpha=Decimal("11.000"),
            beta=Decimal("2.000"),
            confidence=Decimal("0.500"),
            attempt_count=12,
            last_attempt_at=far_ago,
            last_decay_at=far_ago,
            updated_at=far_ago,
        )
    )
    await db_session.commit()

    n1 = await decay_due_mastery_rows(db_session)
    n2 = await decay_due_mastery_rows(db_session)
    assert n1 == 1
    assert n2 == 0  # second pass: last_decay_at is now < cutoff
