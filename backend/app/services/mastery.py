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

from sqlalchemy import and_, func, select, update
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


async def _ensure_mastery_row(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    concept_id: uuid.UUID,
    course_id: uuid.UUID,
) -> None:
    """Ensure a ``ConceptMastery`` row exists for (user, concept). No-op if
    it already does. Race-safe via ``ON CONFLICT DO NOTHING``."""
    now = datetime.now(timezone.utc)
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
        await _ensure_mastery_row(
            db,
            user_id=user_id,
            concept_id=concept.id,
            course_id=course_id,
        )
        delta_a = Decimal(f"{weight * outcome:.3f}")
        delta_b = Decimal(f"{weight * (1.0 - outcome):.3f}")

        # Atomic increment + confidence recompute in one statement.
        # PG row-level locks during UPDATE serialize concurrent
        # attempt-evidence updates against the same (user, concept) row,
        # so two workers can't both read the same alpha/beta and clobber
        # each other's increment. Each SET expression references the OLD
        # column values, so the formula is self-consistent without us
        # having to lock + read in Python.
        new_a = ConceptMastery.alpha + delta_a
        new_b = ConceptMastery.beta + delta_b
        sum_ab = new_a + new_b
        # confidence = 1 − sqrt(α·β / ((α+β)²·(α+β+1)))
        confidence_expr = 1 - func.sqrt(
            (new_a * new_b) / (sum_ab * sum_ab * (sum_ab + 1))
        )
        update_values: dict = {
            "alpha": new_a,
            "beta": new_b,
            "confidence": confidence_expr,
            "attempt_count": ConceptMastery.attempt_count + 1,
            "last_attempt_at": now,
            "updated_at": now,
        }
        if outcome >= 0.5:
            update_values["last_correct_at"] = now
        if last_seen_meeting_id is not None:
            update_values["last_seen_meeting_id"] = last_seen_meeting_id

        result = await db.execute(
            update(ConceptMastery)
            .where(
                ConceptMastery.user_id == user_id,
                ConceptMastery.concept_id == concept.id,
            )
            .values(**update_values)
            .returning(ConceptMastery.alpha, ConceptMastery.beta)
        )
        new_alpha, new_beta = result.one()

        db.add(
            ConceptMasteryHistory(
                user_id=user_id,
                concept_id=concept.id,
                course_id=course_id,
                alpha=new_alpha,
                beta=new_beta,
                event_type="attempt",
                source_kind=attempt_kind.value,
                source_id=target_id,
                outcome=Decimal(f"{outcome:.3f}"),
                recorded_at=now,
            )
        )
        touched += 1

    # Close open action_outcomes — both the exact-target row AND any
    # concept-level recommendations that map to a concept this attempt
    # touched. The materializer emits ``practice_weakness`` actions with
    # ``target_kind='concept'``, so without the second pass the dominant
    # adaptive recommendation never resolves to ``completed=True`` and
    # A/B telemetry / coefficient retune undercount successful nudges.
    if touched:
        from sqlalchemy import or_ as _or
        from app.models import ActionOutcome

        metric_by_kind = {
            "quiz": "quiz_score",
            "flashcard": "recall",
            "revision": "quiz_score",
            "pronunciation": "completion",
        }
        concept_ids = [
            concept.id for tag, concept in tags if float(tag.weight) > 0
        ]
        await db.execute(
            update(ActionOutcome)
            .where(
                ActionOutcome.user_id == user_id,
                ActionOutcome.completed.is_(False),
                _or(
                    and_(
                        ActionOutcome.target_kind == target_kind,
                        ActionOutcome.target_id == target_id,
                    ),
                    and_(
                        ActionOutcome.target_kind == "concept",
                        ActionOutcome.target_id.in_(concept_ids),
                    ),
                ),
            )
            .values(
                completed=True,
                outcome_metric=metric_by_kind.get(attempt_kind.value, "completion"),
                outcome_score=Decimal(f"{outcome:.3f}"),
                observed_at=now,
            )
        )

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
