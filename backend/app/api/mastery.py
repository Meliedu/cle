import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_owned_course
from app.models import Concept, ConceptMastery, Enrollment
from app.models.course import Course
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.concept import CohortMasteryRow, MasteryResponse

router = APIRouter(tags=["mastery"])


@router.get(
    "/users/me/courses/{course_id}/mastery",
    response_model=APIResponse[list[MasteryResponse]],
)
async def my_mastery_for_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[list[MasteryResponse]]:
    # Enrollment guard
    enrolled = (
        await db.execute(
            select(Enrollment).where(
                Enrollment.user_id == user.id,
                Enrollment.course_id == course_id,
            )
        )
    ).scalar_one_or_none()
    is_owner = (
        await db.execute(
            select(Course).where(
                Course.id == course_id,
                Course.instructor_id == user.id,
                Course.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if enrolled is None and is_owner is None:
        raise HTTPException(status_code=404, detail="Course not found")

    rows = (
        await db.execute(
            select(ConceptMastery, Concept.name)
            .join(Concept, Concept.id == ConceptMastery.concept_id)
            .where(
                ConceptMastery.user_id == user.id,
                ConceptMastery.course_id == course_id,
                Concept.deleted_at.is_(None),
            )
            .order_by(Concept.name)
        )
    ).all()
    return APIResponse(
        success=True,
        data=[
            MasteryResponse(
                concept_id=m.concept_id,
                concept_name=name,
                course_id=m.course_id,
                alpha=m.alpha,
                beta=m.beta,
                mastery_score=m.mastery_score,
                confidence=m.confidence,
                attempt_count=m.attempt_count,
                last_attempt_at=m.last_attempt_at,
                last_decay_at=m.last_decay_at,
                updated_at=m.updated_at,
            )
            for m, name in rows
        ],
    )


@router.get(
    "/courses/{course_id}/mastery",
    response_model=APIResponse[list[CohortMasteryRow]],
)
async def cohort_mastery(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[list[CohortMasteryRow]]:
    """Per-concept cohort summary (instructor-only)."""
    stmt = (
        select(
            Concept.id.label("concept_id"),
            Concept.name.label("concept_name"),
            func.avg(ConceptMastery.mastery_score).label("avg_mastery"),
            func.count()
            .filter(
                (ConceptMastery.mastery_score < 0.5)
                & (ConceptMastery.confidence >= 0.5)
            )
            .label("weak_students"),
            func.count(ConceptMastery.user_id).label("total"),
        )
        .select_from(Concept)
        .outerjoin(
            ConceptMastery, ConceptMastery.concept_id == Concept.id
        )
        .where(
            Concept.course_id == course.id,
            Concept.deleted_at.is_(None),
            Concept.canonical_id.is_(None),
        )
        .group_by(Concept.id, Concept.name)
        .order_by(func.coalesce(func.avg(ConceptMastery.mastery_score), 0).asc())
    )
    rows = (await db.execute(stmt)).all()
    return APIResponse(
        success=True,
        data=[
            CohortMasteryRow(
                concept_id=r.concept_id,
                concept_name=r.concept_name,
                avg_mastery=float(r.avg_mastery) if r.avg_mastery is not None else None,
                weak_students=r.weak_students or 0,
                total_students_with_evidence=r.total or 0,
            )
            for r in rows
        ],
    )
