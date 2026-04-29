import uuid
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models import Concept, ConceptTag
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.concept import ConceptResponse

router = APIRouter(prefix="/concept-tags", tags=["concepts"])

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
    """Return the concepts tagged on a single target. Read-open to any
    authenticated user — concepts are not sensitive course data."""
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
    return APIResponse(
        success=True, data=[ConceptResponse.model_validate(c) for c in rows]
    )
