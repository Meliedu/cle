"""Beta-Binomial mastery update + nightly HLR-style decay.

Spec §Mastery math:
- α ← α + w · outcome
- β ← β + w · (1 − outcome)
- confidence = 1 − sqrt(α·β / ((α+β)² · (α+β+1)))
- decay (HLR): decay = 2^(−days/τ); shrink (α, β) toward prior 1.0.
"""
from __future__ import annotations

import enum
import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Concept,
    ConceptMastery,
    ConceptMasteryHistory,
    ConceptTag,
)

logger = logging.getLogger(__name__)

PRIOR = Decimal("1.000")
DEFAULT_HALF_LIFE_DAYS = 14


class AttemptKind(enum.Enum):
    QUIZ = "quiz"
    FLASHCARD = "flashcard"
    REVISION = "revision"
    PRONUNCIATION = "pronunciation"


def compute_confidence(alpha: Decimal, beta: Decimal) -> Decimal:
    a = float(alpha)
    b = float(beta)
    s = a + b
    if s <= 0:
        return Decimal("0.000")
    var = (a * b) / (s * s * (s + 1.0))
    val = 1.0 - math.sqrt(var)
    if val < 0:
        val = 0.0
    if val > 1:
        val = 1.0
    return Decimal(f"{val:.3f}")


async def _get_or_create_mastery(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    concept_id: uuid.UUID,
    course_id: uuid.UUID,
) -> ConceptMastery:
    # Try existing first — fastest path for most attempts.
    row = (
        await db.execute(
            select(ConceptMastery).where(
                ConceptMastery.user_id == user_id,
                ConceptMastery.concept_id == concept_id,
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        return row

    now = datetime.now(timezone.utc)
    # Race-safe upsert: concurrent first-attempt inserts both pass the SELECT
    # above; ON CONFLICT DO NOTHING collapses the duplicate, then we re-SELECT
    # to get the winning row. Avoids IntegrityError aborting the whole txn.
    stmt = (
        pg_insert(ConceptMastery)
        .values(
            user_id=user_id,
            concept_id=concept_id,
            course_id=course_id,
            alpha=PRIOR,
            beta=PRIOR,
            confidence=compute_confidence(PRIOR, PRIOR),
            attempt_count=0,
            last_decay_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(index_elements=["user_id", "concept_id"])
    )
    await db.execute(stmt)
    await db.flush()

    row = (
        await db.execute(
            select(ConceptMastery).where(
                ConceptMastery.user_id == user_id,
                ConceptMastery.concept_id == concept_id,
            )
        )
    ).scalar_one()
    return row


async def apply_attempt_evidence(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    target_kind: str,
    target_id: uuid.UUID,
    attempt_kind: AttemptKind,
    outcome: float,
    last_seen_meeting_id: uuid.UUID | None = None,
) -> int:
    """Update mastery for every concept tagged on this target.

    Returns number of (concept_id) rows touched.
    """
    if not 0.0 <= outcome <= 1.0:
        outcome = max(0.0, min(1.0, outcome))

    tags = (
        await db.execute(
            select(ConceptTag, Concept).join(
                Concept, Concept.id == ConceptTag.concept_id
            ).where(
                ConceptTag.target_kind == target_kind,
                ConceptTag.target_id == target_id,
                Concept.canonical_id.is_(None),
                Concept.deleted_at.is_(None),
                Concept.course_id == course_id,
            )
        )
    ).all()
    if not tags:
        return 0

    now = datetime.now(timezone.utc)
    touched = 0
    for tag, concept in tags:
        weight = float(tag.weight)
        if weight <= 0:
            continue
        row = await _get_or_create_mastery(
            db,
            user_id=user_id,
            concept_id=concept.id,
            course_id=course_id,
        )
        delta_a = Decimal(f"{weight * outcome:.3f}")
        delta_b = Decimal(f"{weight * (1.0 - outcome):.3f}")
        row.alpha = (row.alpha + delta_a).quantize(Decimal("0.001"))
        row.beta = (row.beta + delta_b).quantize(Decimal("0.001"))
        row.confidence = compute_confidence(row.alpha, row.beta)
        row.attempt_count += 1
        row.last_attempt_at = now
        if outcome >= 0.5:
            row.last_correct_at = now
        if last_seen_meeting_id is not None:
            row.last_seen_meeting_id = last_seen_meeting_id
        row.updated_at = now

        db.add(
            ConceptMasteryHistory(
                user_id=user_id,
                concept_id=concept.id,
                course_id=course_id,
                alpha=row.alpha,
                beta=row.beta,
                event_type="attempt",
                source_kind=attempt_kind.value,
                source_id=target_id,
                outcome=Decimal(f"{outcome:.3f}"),
                recorded_at=now,
            )
        )
        touched += 1

    return touched


def hlr_decay_step(
    alpha: Decimal,
    beta: Decimal,
    last_attempt_at: datetime | None,
    now: datetime,
    half_life_days: int = DEFAULT_HALF_LIFE_DAYS,
) -> tuple[Decimal, Decimal]:
    """Return new (alpha, beta) after one decay step. Idempotent same day."""
    if last_attempt_at is None:
        return alpha, beta
    days = max(0.0, (now - last_attempt_at).total_seconds() / 86400.0)
    if days <= 0:
        return alpha, beta
    decay = 2.0 ** (-days / float(half_life_days))
    a_excess = float(alpha) - float(PRIOR)
    b_excess = float(beta) - float(PRIOR)
    new_a = float(PRIOR) + max(0.0, a_excess) * decay
    new_b = float(PRIOR) + max(0.0, b_excess) * decay
    return (
        Decimal(f"{max(float(PRIOR), new_a):.3f}"),
        Decimal(f"{max(float(PRIOR), new_b):.3f}"),
    )


async def decay_due_mastery_rows(
    db: AsyncSession,
    *,
    half_life_days: int = DEFAULT_HALF_LIFE_DAYS,
    batch_size: int = 500,
    older_than_hours: int = 24,
) -> int:
    """Apply HLR-style decay to rows whose ``last_decay_at`` is > 24h old.

    Idempotent: re-running within the same day is a no-op.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
    now = datetime.now(timezone.utc)
    touched = 0
    while True:
        rows = (
            await db.execute(
                select(ConceptMastery)
                .where(ConceptMastery.last_decay_at < cutoff)
                .limit(batch_size)
            )
        ).scalars().all()
        if not rows:
            break
        for row in rows:
            new_a, new_b = hlr_decay_step(
                row.alpha,
                row.beta,
                row.last_attempt_at,
                now,
                half_life_days=half_life_days,
            )
            if new_a != row.alpha or new_b != row.beta:
                row.alpha = new_a
                row.beta = new_b
                row.confidence = compute_confidence(new_a, new_b)
                row.updated_at = now
                db.add(
                    ConceptMasteryHistory(
                        user_id=row.user_id,
                        concept_id=row.concept_id,
                        course_id=row.course_id,
                        alpha=new_a,
                        beta=new_b,
                        event_type="decay",
                        recorded_at=now,
                    )
                )
            row.last_decay_at = now
            touched += 1
        await db.commit()
    return touched
