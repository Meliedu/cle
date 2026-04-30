"""KST outer-fringe filter.

A concept is in the outer fringe of a (user, course) when every prerequisite
edge with strength >= 0.5 leads to a concept the user has *mastered* — i.e.
``mastery_score >= 0.7 AND confidence >= 0.5`` — and the concept itself does
not meet that bar.

Returns a list of (concept_id, name, current_mastery, current_confidence)
ordered by current mastery ascending so the candidate scorer sees the
weakest-but-ready concepts first.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

OUTER_FRINGE_MASTERY_BAR = Decimal("0.7")
OUTER_FRINGE_CONFIDENCE_BAR = Decimal("0.5")


@dataclass(frozen=True)
class FringeConcept:
    concept_id: uuid.UUID
    name: str
    current_mastery: float        # 0.0 if user has no row yet
    current_confidence: float     # 0.0 if user has no row yet


async def outer_fringe_concepts(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
) -> list[FringeConcept]:
    sql = text(
        """
        WITH user_state AS (
            SELECT concept_id, mastery_score, confidence
              FROM public.concept_mastery
             WHERE user_id = :user_id
               AND course_id = :course_id
        )
        SELECT
            c.id   AS concept_id,
            c.name AS name,
            COALESCE(s.mastery_score, 0)::float8 AS current_mastery,
            COALESCE(s.confidence,    0)::float8 AS current_confidence
          FROM public.concepts c
          LEFT JOIN user_state s ON s.concept_id = c.id
         WHERE c.course_id = :course_id
           AND c.deleted_at IS NULL
           AND c.canonical_id IS NULL
           AND c.status = 'approved'
           AND (
                  COALESCE(s.mastery_score, 0) < :mastery_bar
               OR COALESCE(s.confidence, 0)    < :confidence_bar
           )
           AND NOT EXISTS (
               SELECT 1
                 FROM public.concept_prerequisites p
                 LEFT JOIN user_state ps ON ps.concept_id = p.prereq_concept_id
                WHERE p.dependent_concept_id = c.id
                  AND p.strength >= 0.5
                  AND (
                      COALESCE(ps.mastery_score, 0) < :mastery_bar
                      OR COALESCE(ps.confidence, 0) < :confidence_bar
                  )
           )
         ORDER BY current_mastery ASC, c.name ASC
        """
    )
    rows = await db.execute(
        sql,
        {
            "user_id": user_id,
            "course_id": course_id,
            # Bind Decimal directly — float() would lose representability for
            # 0.7 and risk misclassifying boundary mastery_score = 0.700 rows.
            "mastery_bar": OUTER_FRINGE_MASTERY_BAR,
            "confidence_bar": OUTER_FRINGE_CONFIDENCE_BAR,
        },
    )
    return [
        FringeConcept(
            concept_id=r.concept_id,
            name=r.name,
            current_mastery=float(r.current_mastery),
            current_confidence=float(r.current_confidence),
        )
        for r in rows
    ]
