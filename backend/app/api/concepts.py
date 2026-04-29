import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_owned_course
from app.models import Concept
from app.models.course import Course
from app.models.task import Task
from app.schemas.common import APIResponse
from app.schemas.concept import (
    ConceptCreate,
    ConceptResponse,
    ConceptStatus,
    ConceptUpdate,
)

router = APIRouter(prefix="/courses/{course_id}/concepts", tags=["concepts"])


@router.post("", response_model=APIResponse[ConceptResponse], status_code=201)
async def create_concept(
    body: ConceptCreate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[ConceptResponse]:
    # Instructor-created concepts are approved on insert.
    concept = Concept(
        course_id=course.id,
        name=body.name,
        description=body.description,
        instructor_curated=body.instructor_curated,
        status="approved" if body.instructor_curated else "pending",
    )
    db.add(concept)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        # Unique (course_id, lower(name)) violation
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Concept with this name already exists in course",
        ) from exc
    await db.refresh(concept)
    return APIResponse(success=True, data=ConceptResponse.model_validate(concept))


@router.get("", response_model=APIResponse[list[ConceptResponse]])
async def list_concepts(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
    concept_status: ConceptStatus | None = Query(default=None, alias="status"),
) -> APIResponse[list[ConceptResponse]]:
    stmt = select(Concept).where(
        Concept.course_id == course.id,
        Concept.deleted_at.is_(None),
        # Hide soft-merged concepts from list views; instructors look up via canonical row.
        Concept.canonical_id.is_(None),
    )
    if concept_status is not None:
        stmt = stmt.where(Concept.status == concept_status)
    stmt = stmt.order_by(Concept.name)
    result = await db.execute(stmt)
    return APIResponse(
        success=True,
        data=[ConceptResponse.model_validate(c) for c in result.scalars().all()],
    )


@router.put("/{concept_id}", response_model=APIResponse[ConceptResponse])
async def update_concept(
    concept_id: uuid.UUID,
    body: ConceptUpdate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[ConceptResponse]:
    result = await db.execute(
        select(Concept).where(
            Concept.id == concept_id,
            Concept.course_id == course.id,
            Concept.deleted_at.is_(None),
        )
    )
    concept = result.scalar_one_or_none()
    if not concept:
        raise HTTPException(status_code=404, detail="Concept not found")

    # Cross-course canonical guard.
    if body.canonical_id is not None:
        canon_row = (
            await db.execute(
                select(Concept).where(
                    Concept.id == body.canonical_id,
                    Concept.course_id == course.id,
                    Concept.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not canon_row:
            raise HTTPException(
                status_code=400, detail="canonical_id must reference a concept in the same course"
            )

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(concept, field, value)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Concept name conflict") from exc
    await db.refresh(concept)
    return APIResponse(success=True, data=ConceptResponse.model_validate(concept))


@router.delete("/{concept_id}", response_model=APIResponse[None])
async def delete_concept(
    concept_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[None]:
    result = await db.execute(
        select(Concept).where(
            Concept.id == concept_id,
            Concept.course_id == course.id,
            Concept.deleted_at.is_(None),
        )
    )
    concept = result.scalar_one_or_none()
    if not concept:
        raise HTTPException(status_code=404, detail="Concept not found")
    concept.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return APIResponse(success=True, data=None)


@router.post("/replay", response_model=APIResponse[dict])
async def replay_attempts(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[dict]:
    """Enqueue a 90-day replay of all attempts through Beta-Binomial mastery.

    Replay is a re-prime tool, not a retry — re-running before a previous
    replay completes would double-count evidence (each Task fully re-applies
    the window). Returns 409 if an in-flight replay Task exists for this
    course.

    Operators wanting a clean re-prime should wipe the course's
    ``concept_mastery`` rows before invoking this endpoint — the replay
    handler accumulates evidence on top of any existing priors.
    """
    # Guard against concurrent / double-click replays. Two pending/running
    # Task rows for the same course would each fully re-apply evidence,
    # which is exactly NOT what re-prime semantics call for. ``Task.payload``
    # is a generic JSON column (not JSONB), so use the ``->>`` text accessor
    # via ``op`` for portability across both JSON and JSONB.
    inflight = (
        await db.execute(
            select(Task).where(
                Task.task_type == "replay_attempt_history",
                Task.payload.op("->>")("course_id") == str(course.id),
                or_(Task.status == "pending", Task.status == "running"),
            )
        )
    ).scalar_one_or_none()
    if inflight is not None:
        raise HTTPException(
            status_code=409,
            detail="Replay already in progress for this course",
        )

    db.add(
        Task(
            task_type="replay_attempt_history",
            payload={"course_id": str(course.id), "window_days": 90},
            status="pending",
        )
    )
    await db.commit()
    return APIResponse(success=True, data={"enqueued": True})
