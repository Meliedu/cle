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
from app.api.deps import get_current_user, get_db, get_owned_course
from app.models import (
    Concept,
    ConceptMastery,
    ConceptTag,
    LearningObjective,
)
from app.models.course import Course
from app.models.user import User
from app.pilot import get_pilot_profile
from app.schemas.common import APIResponse
from app.schemas.insights import (
    CohortIloMapEntry,
    CohortIloMapResponse,
    ConceptMasteryEntry,
    IloMapEntry,
    IloMapResponse,
    LearningProfileGroups,
    LearningProfileResponse,
    SkillMapEntry,
    SkillMapResponse,
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


async def _objectives_with_concept_ids(
    db: AsyncSession, course_id: uuid.UUID
) -> list[tuple[LearningObjective, list[uuid.UUID]]]:
    """Shared aggregation seam: each course objective → its tagged concept ids.

    An objective's concepts are the LIVE (non-deleted, non-merged) ``concepts``
    linked via ``concept_tags`` with ``target_kind='objective'`` and
    ``target_id = objective.id``. Pure read — the caller decides whose mastery to
    aggregate (own rows for the student view, the cohort for the teacher view).
    """
    objectives = (
        (
            await db.execute(
                select(LearningObjective)
                .where(
                    LearningObjective.course_id == course_id,
                    LearningObjective.deleted_at.is_(None),
                )
                .order_by(
                    LearningObjective.order_index, LearningObjective.statement
                )
            )
        )
        .scalars()
        .all()
    )

    tag_rows = (
        await db.execute(
            select(ConceptTag.target_id, ConceptTag.concept_id)
            .join(Concept, Concept.id == ConceptTag.concept_id)
            .where(
                ConceptTag.target_kind == "objective",
                Concept.course_id == course_id,
                Concept.deleted_at.is_(None),
                Concept.canonical_id.is_(None),
            )
        )
    ).all()

    concepts_by_objective: dict[uuid.UUID, list[uuid.UUID]] = {}
    for target_id, concept_id in tag_rows:
        concepts_by_objective.setdefault(target_id, []).append(concept_id)

    return [(o, concepts_by_objective.get(o.id, [])) for o in objectives]


@router.get(
    "/users/me/courses/{course_id}/ilo-map",
    response_model=APIResponse[IloMapResponse],
)
async def my_ilo_map(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[IloMapResponse]:
    """The caller's ILO strength map, reshaped from ``concept_mastery`` (pure read).

    One row per course ``learning_objective``; strength is the mean of the
    caller's ``mastery_score`` over the concepts tagged to that objective
    (``concept_tags`` ``target_kind='objective'``). Enrollment-scoped
    (``verify_enrollment`` — active only) and limited to the caller's own rows.
    Objectives with no tagged concept that has caller evidence render
    ``has_evidence=false``, NEVER a fabricated 0 (Decision 7).
    """
    await verify_enrollment(db, course_id, user.id)

    objectives = await _objectives_with_concept_ids(db, course_id)

    mastery_rows = (
        await db.execute(
            select(ConceptMastery.concept_id, ConceptMastery.mastery_score).where(
                ConceptMastery.user_id == user.id,
                ConceptMastery.course_id == course_id,
            )
        )
    ).all()
    mastery_by_concept = {cid: score for cid, score in mastery_rows}

    entries: list[IloMapEntry] = []
    any_evidence = False
    for objective, concept_ids in objectives:
        scores = [
            mastery_by_concept[cid]
            for cid in concept_ids
            if cid in mastery_by_concept
        ]
        has_evidence = bool(scores)
        if has_evidence:
            any_evidence = True
        entries.append(
            IloMapEntry(
                objective_id=objective.id,
                statement=objective.statement,
                bloom_level=objective.bloom_level,
                has_evidence=has_evidence,
                strength=(
                    float(sum(scores) / len(scores)) if has_evidence else None
                ),
                concept_count=len(concept_ids),
                evidence_concept_count=len(scores),
            )
        )

    return APIResponse(
        success=True,
        data=IloMapResponse(
            course_id=course_id, has_evidence=any_evidence, objectives=entries
        ),
    )


@router.get(
    "/courses/{course_id}/ilo-map",
    response_model=APIResponse[CohortIloMapResponse],
)
async def cohort_ilo_map(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[CohortIloMapResponse]:
    """The cohort ILO strength map for an owned course (instructor-only, pure read).

    One row per ``learning_objective``: ``avg_strength`` is the row-level mean
    ``mastery_score`` over every student's mastery on the objective's tagged
    concepts (mirrors ``cohort_mastery``'s ``func.avg``); ``weak_students`` reuses
    the ``cohort_mastery`` weak definition (mastery < 0.5 among confidence >= 0.5),
    counted as DISTINCT weak students. ``get_owned_course`` 404s a non-owner.
    Objectives with no cohort evidence render ``has_evidence=false``, never a 0.
    """
    objectives = await _objectives_with_concept_ids(db, course.id)

    mastery_rows = (
        await db.execute(
            select(
                ConceptMastery.concept_id,
                ConceptMastery.user_id,
                ConceptMastery.mastery_score,
                ConceptMastery.confidence,
            ).where(ConceptMastery.course_id == course.id)
        )
    ).all()

    rows_by_concept: dict[uuid.UUID, list[tuple]] = {}
    for cid, uid, score, confidence in mastery_rows:
        rows_by_concept.setdefault(cid, []).append((uid, score, confidence))

    entries: list[CohortIloMapEntry] = []
    any_evidence = False
    for objective, concept_ids in objectives:
        scores: list = []
        weak_users: set[uuid.UUID] = set()
        evidence_users: set[uuid.UUID] = set()
        for cid in concept_ids:
            for uid, score, confidence in rows_by_concept.get(cid, []):
                scores.append(score)
                evidence_users.add(uid)
                if (
                    score < _WEAK_MASTERY_THRESHOLD
                    and confidence >= _MIN_CONFIDENCE
                ):
                    weak_users.add(uid)
        has_evidence = bool(scores)
        if has_evidence:
            any_evidence = True
        entries.append(
            CohortIloMapEntry(
                objective_id=objective.id,
                statement=objective.statement,
                bloom_level=objective.bloom_level,
                has_evidence=has_evidence,
                avg_strength=(
                    float(sum(scores) / len(scores)) if has_evidence else None
                ),
                weak_students=len(weak_users),
                students_with_evidence=len(evidence_users),
                concept_count=len(concept_ids),
            )
        )

    return APIResponse(
        success=True,
        data=CohortIloMapResponse(
            course_id=course.id, has_evidence=any_evidence, objectives=entries
        ),
    )


@router.get(
    "/users/me/courses/{course_id}/skill-map",
    response_model=APIResponse[SkillMapResponse],
)
async def my_skill_map(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[SkillMapResponse]:
    """The caller's skill-pattern map — HONEST, config-driven (pure read, B6).

    One entry per pilot ``skill_taxonomy`` skill. Decision 5: NO ``skill`` link
    exists anywhere in the schema — ``concept_tags.target_kind`` has
    ``objective``/``checkpoint_card``/… but NOT ``skill``, and no evidence row
    (``concept_mastery``, ``learning_notes``, …) carries a skill dimension. So
    every cell honestly renders the no-evidence state: ``has_evidence=False``
    with ``strength`` and ``sample_size`` both ``None``. This endpoint NEVER
    fabricates a score — it only exposes the config taxonomy so the frontend can
    render the "we don't have skill-level evidence yet" state.

    SEAM TO EXTEND: when a future concept→skill mapping lands (e.g. a ``skill``
    ``target_kind`` on ``concept_tags``, or a skill column on the evidence rows),
    aggregate the caller's ``concept_mastery`` over that mapping HERE and
    populate ``strength``/``sample_size`` + flip ``has_evidence`` — only where
    real evidence exists. Until then, honesty over a fabricated grid.

    Enrollment-scoped (``verify_enrollment`` — active enrollment only, 403
    otherwise) so it matches the rest of the student insights surface.
    """
    await verify_enrollment(db, course_id, user.id)

    taxonomy = get_pilot_profile().skill_taxonomy
    skills = [
        SkillMapEntry(
            skill=skill,
            label=skill.replace("_", " ").capitalize(),
            # Decision 5: no schema link exists — every cell is no-evidence.
            has_evidence=False,
            strength=None,
            sample_size=None,
        )
        for skill in taxonomy
    ]

    return APIResponse(
        success=True,
        data=SkillMapResponse(
            course_id=course_id, has_evidence=False, skills=skills
        ),
    )
