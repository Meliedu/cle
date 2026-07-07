"""Pure-read insights surface (P6 §5).

This router RESHAPES existing evidence rows — it performs NO new mastery math,
no note drafting, no alert evaluation (Decision 1, "no parallel evidence path").
Every number it returns traces to a row another system already wrote.

The student learning profile groups the caller's ``concept_mastery`` rows using
the SAME thresholds ``app/api/mastery.py::cohort_mastery`` applies — it never
recomputes them.
"""
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._helpers import verify_enrollment
from app.api.deps import get_current_user, get_db
from app.models import Concept, ConceptMastery
from app.models.user import User
from app.pilot import get_pilot_profile
from app.schemas.common import APIResponse
from app.schemas.insights import (
    ConceptMasteryEntry,
    LearningProfileGroups,
    LearningProfileResponse,
)

router = APIRouter(tags=["insights"])

# Thresholds mirror ``app/api/mastery.py::cohort_mastery`` EXACTLY — do NOT
# invent new cut points here. A mastery row only counts as evidence once its
# ``confidence >= 0.5``; a counted row is "weak" below 0.5 mastery and "strong"
# at/above it. Rows that have not yet cleared the confidence gate are surfaced
# as "developing" (still accumulating evidence) rather than fabricating a
# strong/weak verdict on thin data.
_MIN_CONFIDENCE = Decimal("0.5")
_WEAK_MASTERY_THRESHOLD = Decimal("0.5")


@router.get(
    "/users/me/courses/{course_id}/insights",
    response_model=APIResponse[LearningProfileResponse],
)
async def my_learning_profile(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[LearningProfileResponse]:
    """The caller's learning profile, reshaped from ``concept_mastery`` (pure read).

    Enrollment-scoped (``verify_enrollment`` — active enrollment only, 403
    otherwise) and limited to the caller's own ``user_id`` rows. A student with
    no confident evidence gets an empty profile with ``has_evidence=false``
    (Decision 6) — the endpoint never fabricates a score.
    """
    await verify_enrollment(db, course_id, user.id)

    rows = (
        await db.execute(
            select(ConceptMastery, Concept.name)
            .join(Concept, Concept.id == ConceptMastery.concept_id)
            .where(
                ConceptMastery.user_id == user.id,
                ConceptMastery.course_id == course_id,
                Concept.deleted_at.is_(None),
                Concept.canonical_id.is_(None),
            )
            .order_by(Concept.name)
        )
    ).all()

    strong: list[ConceptMasteryEntry] = []
    developing: list[ConceptMasteryEntry] = []
    weak: list[ConceptMasteryEntry] = []
    has_evidence = False
    for m, name in rows:
        entry = ConceptMasteryEntry(
            concept_id=m.concept_id,
            concept_name=name,
            mastery_score=m.mastery_score,
            confidence=m.confidence,
            attempt_count=m.attempt_count,
            last_attempt_at=m.last_attempt_at,
        )
        if m.confidence < _MIN_CONFIDENCE:
            developing.append(entry)
        else:
            has_evidence = True
            if m.mastery_score < _WEAK_MASTERY_THRESHOLD:
                weak.append(entry)
            else:
                strong.append(entry)

    profile = LearningProfileResponse(
        course_id=course_id,
        has_evidence=has_evidence,
        concept_count=len(rows),
        groups=LearningProfileGroups(
            strong=strong, developing=developing, weak=weak
        ),
        disclaimer=get_pilot_profile().claim_limits["learning_profile"],
    )
    return APIResponse(success=True, data=profile)
