import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_instructor
from app.models import Concept, ConceptTag, Enrollment
from app.models.course import Course
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.concept import ConceptResponse

router = APIRouter(prefix="/concept-tags", tags=["concepts"])

# Relationship Candidate review gate (CLE §5.4): an instructor confirms, edits,
# or archives an AI-suggested concept tag. Only these target states are valid
# review verdicts (the model also allows 'suggested'/'reviewed' for drafts).
TagReviewStatus = Literal["confirmed", "edited", "archived"]


class ConceptTagReviewUpdate(BaseModel):
    review_status: TagReviewStatus
    limitation: str | None = None


class ConceptTagReviewResponse(BaseModel):
    concept_id: uuid.UUID
    target_kind: str
    target_id: uuid.UUID
    review_status: str
    suggestion_source: str | None
    limitation: str | None
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    report_eligibility: bool

    model_config = {"from_attributes": True}

TargetKind = Literal[
    "chunk",
    "question",
    "flashcard_card",
    "pronunciation_item",
    "pool_item",
    "objective",
    "meeting",
    "assignment",
]


@router.get(
    "/{target_kind}/{target_id}",
    response_model=APIResponse[list[ConceptResponse]],
)
async def list_tags_for_target(
    target_kind: TargetKind,
    target_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[list[ConceptResponse]]:
    """Return concepts tagged on a single target.

    Access scoped to the target's course: caller must be enrolled in OR own
    that course. We return 404 when neither holds, masking existence of the
    target id (cross-tenant info disclosure protection).
    """
    rows = (
        await db.execute(
            select(Concept)
            .join(ConceptTag, ConceptTag.concept_id == Concept.id)
            .where(
                ConceptTag.target_kind == target_kind,
                ConceptTag.target_id == target_id,
                Concept.deleted_at.is_(None),
                Concept.canonical_id.is_(None),
            )
            .order_by(Concept.name)
        )
    ).scalars().all()

    if not rows:
        # No tags exist for this target. Return empty list rather than 404
        # because the absence of tags isn't sensitive — many artifacts have
        # no concept tags. The course-scoping check below only fires when
        # tags exist (i.e. when we'd be revealing course state).
        return APIResponse(success=True, data=[])

    course_id = rows[0].course_id

    # Authorization: caller must be enrolled OR own the course.
    enrolled = (
        await db.execute(
            select(Enrollment).where(
                Enrollment.user_id == user.id,
                Enrollment.course_id == course_id,
            )
        )
    ).scalar_one_or_none()
    if enrolled is None:
        owned = (
            await db.execute(
                select(Course).where(
                    Course.id == course_id,
                    Course.instructor_id == user.id,
                    Course.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if owned is None:
            raise HTTPException(status_code=404, detail="Target not found")

    return APIResponse(
        success=True, data=[ConceptResponse.model_validate(c) for c in rows]
    )


@router.patch(
    "/{concept_id}/{target_kind}/{target_id}/review",
    response_model=APIResponse[ConceptTagReviewResponse],
)
async def review_concept_tag(
    concept_id: uuid.UUID,
    target_kind: TargetKind,
    target_id: uuid.UUID,
    body: ConceptTagReviewUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_instructor),
) -> APIResponse[ConceptTagReviewResponse]:
    """Confirm / edit / archive an AI-suggested Relationship Candidate.

    The tag's concept must belong to a course the acting instructor owns; we
    return 404 otherwise (masking existence of out-of-scope tags).
    """
    row = (
        await db.execute(
            select(ConceptTag)
            .join(Concept, Concept.id == ConceptTag.concept_id)
            .join(Course, Course.id == Concept.course_id)
            .where(
                ConceptTag.concept_id == concept_id,
                ConceptTag.target_kind == target_kind,
                ConceptTag.target_id == target_id,
                Concept.deleted_at.is_(None),
                Course.instructor_id == actor.id,
                Course.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Concept tag not found")

    row.review_status = body.review_status
    if body.limitation is not None:
        row.limitation = body.limitation
    row.reviewed_by = actor.id
    row.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)

    return APIResponse(
        success=True, data=ConceptTagReviewResponse.model_validate(row)
    )
