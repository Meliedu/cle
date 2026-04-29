import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_owned_course
from app.models import Concept, ConceptPrerequisite
from app.models.course import Course
from app.schemas.common import APIResponse
from app.schemas.concept import (
    ConceptPrerequisiteCreate,
    ConceptPrerequisiteResponse,
)

router = APIRouter(
    prefix="/courses/{course_id}/concept-prerequisites",
    tags=["concepts"],
)


_CYCLE_CHECK_SQL = text(
    """
    WITH RECURSIVE reachable AS (
        SELECT dependent_concept_id AS node
        FROM concept_prerequisites
        WHERE prereq_concept_id = :new_dependent
        UNION
        SELECT cp.dependent_concept_id
        FROM concept_prerequisites cp
        JOIN reachable r ON cp.prereq_concept_id = r.node
    )
    SELECT 1 FROM reachable WHERE node = :new_prereq LIMIT 1;
    """
)


async def _both_in_course(
    db: AsyncSession, course_id: uuid.UUID, *ids: uuid.UUID
) -> bool:
    rows = (
        await db.execute(
            select(Concept.id).where(
                Concept.id.in_(ids),
                Concept.course_id == course_id,
                Concept.deleted_at.is_(None),
                Concept.canonical_id.is_(None),
            )
        )
    ).scalars().all()
    return len(set(rows)) == len(set(ids))


@router.post(
    "", response_model=APIResponse[ConceptPrerequisiteResponse], status_code=201
)
async def create_prerequisite(
    body: ConceptPrerequisiteCreate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[ConceptPrerequisiteResponse]:
    if body.prereq_concept_id == body.dependent_concept_id:
        raise HTTPException(status_code=400, detail="self-prerequisite not allowed")

    if not await _both_in_course(
        db, course.id, body.prereq_concept_id, body.dependent_concept_id
    ):
        raise HTTPException(
            status_code=400,
            detail="both concepts must belong to the same course",
        )

    # Cycle detection: would adding (prereq → dependent) create a path
    # dependent → ... → prereq?
    existing_path = (
        await db.execute(
            _CYCLE_CHECK_SQL,
            {
                "new_dependent": body.dependent_concept_id,
                "new_prereq": body.prereq_concept_id,
            },
        )
    ).first()
    if existing_path is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="adding this edge would create a cycle",
        )

    edge = ConceptPrerequisite(
        prereq_concept_id=body.prereq_concept_id,
        dependent_concept_id=body.dependent_concept_id,
        strength=body.strength,
        instructor_verified=True,
    )
    db.add(edge)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="prerequisite already exists",
        ) from exc
    await db.refresh(edge)
    return APIResponse(
        success=True,
        data=ConceptPrerequisiteResponse.model_validate(edge),
    )


@router.get("", response_model=APIResponse[list[ConceptPrerequisiteResponse]])
async def list_prerequisites(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[list[ConceptPrerequisiteResponse]]:
    rows = (
        await db.execute(
            select(ConceptPrerequisite)
            .join(Concept, Concept.id == ConceptPrerequisite.dependent_concept_id)
            .where(
                Concept.course_id == course.id,
                Concept.canonical_id.is_(None),
                Concept.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    return APIResponse(
        success=True,
        data=[ConceptPrerequisiteResponse.model_validate(r) for r in rows],
    )


@router.delete(
    "/{prereq_id}/{dependent_id}", response_model=APIResponse[None]
)
async def delete_prerequisite(
    prereq_id: uuid.UUID,
    dependent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[None]:
    if not await _both_in_course(db, course.id, prereq_id, dependent_id):
        raise HTTPException(status_code=404, detail="prerequisite not found")
    result = await db.execute(
        select(ConceptPrerequisite).where(
            ConceptPrerequisite.prereq_concept_id == prereq_id,
            ConceptPrerequisite.dependent_concept_id == dependent_id,
        )
    )
    edge = result.scalar_one_or_none()
    if not edge:
        raise HTTPException(status_code=404, detail="prerequisite not found")
    await db.delete(edge)
    await db.commit()
    return APIResponse(success=True, data=None)
