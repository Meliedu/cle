import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_owned_course
from app.models import Concept
from app.models.course import Course
from app.schemas.common import APIResponse
from app.schemas.concept import (
    ConceptClusterDecision,
    ConceptClusterMember,
    ConceptClusterResponse,
)

router = APIRouter(
    prefix="/courses/{course_id}/concept-clusters",
    tags=["concepts"],
)


@router.get("", response_model=APIResponse[list[ConceptClusterResponse]])
async def list_clusters(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[list[ConceptClusterResponse]]:
    rows = (
        await db.execute(
            select(Concept)
            .where(
                Concept.course_id == course.id,
                Concept.deleted_at.is_(None),
                Concept.status == "pending",
                Concept.cluster_id.is_not(None),
            )
            .order_by(Concept.cluster_id, Concept.name)
        )
    ).scalars().all()

    grouped: dict[uuid.UUID, list[Concept]] = defaultdict(list)
    for r in rows:
        grouped[r.cluster_id].append(r)

    out: list[ConceptClusterResponse] = []
    for cluster_id, members in grouped.items():
        # Canonical suggestion: longest name (most specific).
        suggested = sorted(members, key=lambda m: -len(m.name))[0]
        out.append(
            ConceptClusterResponse(
                cluster_id=cluster_id,
                course_id=course.id,
                suggested_name=suggested.name,
                suggested_description=suggested.description,
                members=[
                    ConceptClusterMember(
                        candidate_id=m.id,
                        name=m.name,
                        description=m.description,
                        evidence_chunk_id=m.extracted_from_chunk_id,
                    )
                    for m in members
                ],
                example_chunk_ids=[
                    m.extracted_from_chunk_id for m in members if m.extracted_from_chunk_id
                ],
                status="pending",
            )
        )
    return APIResponse(success=True, data=out)


@router.post(
    "/{cluster_id}/decide",
    response_model=APIResponse[dict],
)
async def decide_cluster(
    cluster_id: uuid.UUID,
    body: ConceptClusterDecision,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[dict]:
    rows = (
        await db.execute(
            select(Concept)
            .where(
                Concept.course_id == course.id,
                Concept.cluster_id == cluster_id,
                Concept.deleted_at.is_(None),
                Concept.status == "pending",
            )
        )
    ).scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail="cluster not found")

    if body.action == "reject":
        for m in rows:
            m.status = "rejected"
            m.cluster_id = None
        await db.commit()
        return APIResponse(success=True, data={"canonical_concept_id": None})

    if body.action == "merge":
        if body.merge_into_concept_id is None:
            raise HTTPException(
                status_code=400, detail="merge_into_concept_id required for merge"
            )
        target = (
            await db.execute(
                select(Concept).where(
                    Concept.id == body.merge_into_concept_id,
                    Concept.course_id == course.id,
                    Concept.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if target is None or target.status != "approved":
            raise HTTPException(
                status_code=400, detail="merge target must be approved concept in this course"
            )
        for m in rows:
            m.status = "merged"
            m.canonical_id = target.id
            m.cluster_id = None
        await db.commit()
        return APIResponse(
            success=True, data={"canonical_concept_id": str(target.id)}
        )

    if body.action in ("approve", "rename"):
        if not body.final_name:
            raise HTTPException(
                status_code=400, detail="final_name required for approve/rename"
            )
        # Pick the longest-named member as canonical (matches list_clusters
        # suggestion). Mark remaining members as merged with canonical_id.
        canon = sorted(rows, key=lambda m: -len(m.name))[0]
        canon.name = body.final_name
        if body.final_description is not None:
            canon.description = body.final_description
        canon.status = "approved"
        canon.instructor_curated = True
        canon.cluster_id = None
        for m in rows:
            if m.id == canon.id:
                continue
            m.status = "merged"
            m.canonical_id = canon.id
            m.cluster_id = None
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(
                status_code=409,
                detail="concept name conflicts with existing approved concept",
            ) from exc
        return APIResponse(
            success=True, data={"canonical_concept_id": str(canon.id)}
        )

    raise HTTPException(status_code=400, detail=f"unknown action: {body.action}")
