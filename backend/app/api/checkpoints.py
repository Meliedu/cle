"""Checkpoints router (Task 9): teacher generation + DRAFT-only card CRUD.

Decision 3 — P1 writes/exposes ``draft``/``teacher_editing`` states ONLY. There
are deliberately NO publish/approve/schedule/close routes here (those ship P3);
a test asserts they 404. The single ``final_comments`` card is fixed (not
removable); removing a ``review_point`` requires a reason; card edits are only
allowed while the checkpoint is in an editable draft state.

Two routers are exported:
- ``course_router`` under ``/courses/{course_id}/checkpoints`` (generate + list),
  guarded by ``get_owned_course``.
- ``router`` under ``/checkpoints`` (get/delete + card CRUD), guarded by a
  per-checkpoint ownership helper that mirrors ``get_owned_course`` semantics
  (404 on non-owner, never 403, so course existence isn't leaked).
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_owned_course
from app.database import get_db
from app.models.checkpoint import Checkpoint, CheckpointCard
from app.models.course import Course
from app.models.task import Task
from app.models.user import User
from app.schemas.checkpoint import (
    CheckpointCardCreate,
    CheckpointCardResponse,
    CheckpointCardUpdate,
    CheckpointGenerateRequest,
    CheckpointResponse,
    CheckpointWithCardsResponse,
)
from app.schemas.common import APIResponse

# Card mutations (edit/remove/add) are only legal while the teacher is still
# drafting (Decision 3). Any later state is P3 territory and refuses edits.
_EDITABLE_STATUSES = {"draft", "teacher_editing"}

router = APIRouter(prefix="/checkpoints", tags=["checkpoints"])
course_router = APIRouter(prefix="/courses/{course_id}", tags=["checkpoints"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _owned_checkpoint(
    checkpoint_id: uuid.UUID, user: User, db: AsyncSession
) -> Checkpoint:
    """Resolve a checkpoint the authenticated instructor owns (404 otherwise)."""
    cp = await db.get(Checkpoint, checkpoint_id)
    if cp is None or cp.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    course = await db.get(Course, cp.course_id)
    if course is None or course.deleted_at is not None or course.instructor_id != user.id:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    return cp


def _assert_editable(cp: Checkpoint) -> None:
    if cp.status not in _EDITABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CHECKPOINT_NOT_EDITABLE",
                "message": (
                    f"Checkpoint is '{cp.status}'; cards can only be edited while "
                    "it is a draft."
                ),
            },
        )


def _bump_editing(cp: Checkpoint) -> None:
    """A teacher edit moves a fresh ``draft`` into ``teacher_editing`` (§4.2)."""
    if cp.status == "draft":
        cp.status = "teacher_editing"


async def _load_cards(db: AsyncSession, checkpoint_id: uuid.UUID) -> list[CheckpointCard]:
    return list(
        (
            await db.execute(
                select(CheckpointCard)
                .where(
                    CheckpointCard.checkpoint_id == checkpoint_id,
                    CheckpointCard.deleted_at.is_(None),
                )
                .order_by(CheckpointCard.position)
            )
        ).scalars().all()
    )


# ----- generate + list (course-scoped) -----

@course_router.post(
    "/checkpoints/generate", response_model=APIResponse[None], status_code=202
)
async def generate_checkpoints(
    body: CheckpointGenerateRequest,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[None]:
    """Enqueue the grounded ``generate_checkpoints`` job (Task 6). DRAFT-only."""
    payload: dict[str, str | int] = {"course_id": str(course.id)}
    if body.meeting_id is not None:
        payload["meeting_id"] = str(body.meeting_id)
    if body.review_card_count is not None:
        payload["review_card_count"] = body.review_card_count
    db.add(Task(task_type="generate_checkpoints", payload=payload, status="pending"))
    await db.commit()
    return APIResponse(success=True, data=None)


@course_router.get(
    "/checkpoints", response_model=APIResponse[list[CheckpointResponse]]
)
async def list_checkpoints(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[list[CheckpointResponse]]:
    rows = (
        await db.execute(
            select(Checkpoint)
            .where(
                Checkpoint.course_id == course.id,
                Checkpoint.deleted_at.is_(None),
            )
            .order_by(Checkpoint.created_at)
        )
    ).scalars().all()
    return APIResponse(
        success=True,
        data=[CheckpointResponse.model_validate(cp) for cp in rows],
    )


# ----- get / delete (checkpoint-scoped) -----

@router.get("/{checkpoint_id}", response_model=APIResponse[CheckpointWithCardsResponse])
async def get_checkpoint(
    checkpoint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[CheckpointWithCardsResponse]:
    cp = await _owned_checkpoint(checkpoint_id, user, db)
    cards = await _load_cards(db, cp.id)
    data = CheckpointWithCardsResponse.model_validate(cp)
    data.cards = [CheckpointCardResponse.model_validate(c) for c in cards]
    return APIResponse(success=True, data=data)


@router.delete("/{checkpoint_id}", response_model=APIResponse[None])
async def delete_checkpoint(
    checkpoint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[None]:
    cp = await _owned_checkpoint(checkpoint_id, user, db)
    cp.deleted_at = _utcnow()
    await db.commit()
    return APIResponse(success=True, data=None)


# ----- card CRUD (checkpoint-scoped, DRAFT-only) -----

async def _load_card(
    db: AsyncSession, cp: Checkpoint, card_id: uuid.UUID
) -> CheckpointCard:
    card = await db.get(CheckpointCard, card_id)
    if (
        card is None
        or card.deleted_at is not None
        or card.checkpoint_id != cp.id
    ):
        raise HTTPException(status_code=404, detail="Card not found")
    return card


@router.patch(
    "/{checkpoint_id}/cards/{card_id}",
    response_model=APIResponse[CheckpointCardResponse],
)
async def update_card(
    checkpoint_id: uuid.UUID,
    card_id: uuid.UUID,
    body: CheckpointCardUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[CheckpointCardResponse]:
    cp = await _owned_checkpoint(checkpoint_id, user, db)
    _assert_editable(cp)
    card = await _load_card(db, cp, card_id)
    fields = body.model_dump(exclude_unset=True)

    if fields.get("removed") is True:
        # The final_comments card is fixed — it can never be removed (§4.2).
        if card.kind == "final_comments":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "FINAL_CARD_FIXED",
                    "message": "The final comments card cannot be removed.",
                },
            )
        # Removing a review_point requires a categorized reason.
        reason = fields.get("removed_reason") or card.removed_reason
        if not reason:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "REMOVE_REASON_REQUIRED",
                    "message": "A removal reason is required to remove a card.",
                },
            )
        card.removed = True
        card.removed_reason = reason
        if "removed_note" in fields:
            card.removed_note = fields["removed_note"]
        # Soft-remove so the partial unique index / list queries skip it.
        card.deleted_at = _utcnow()
    else:
        for field in ("prompt", "document_id", "chunk_id", "objective_id", "removed_note"):
            if field in fields:
                setattr(card, field, fields[field])
        if fields.get("removed") is False:
            card.removed = False
            card.removed_reason = None

    _bump_editing(cp)
    await db.commit()
    await db.refresh(card)
    await db.refresh(cp)  # repopulate onupdate-expired columns for later reads
    return APIResponse(success=True, data=CheckpointCardResponse.model_validate(card))


@router.post(
    "/{checkpoint_id}/cards",
    response_model=APIResponse[CheckpointCardResponse],
    status_code=201,
)
async def add_card(
    checkpoint_id: uuid.UUID,
    body: CheckpointCardCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[CheckpointCardResponse]:
    cp = await _owned_checkpoint(checkpoint_id, user, db)
    _assert_editable(cp)

    if body.position is not None:
        position = body.position
    else:
        # Append after the current max position among live cards.
        existing = await _load_cards(db, cp.id)
        position = (max((c.position for c in existing), default=-1)) + 1

    # kind is server-forced to review_point — the single final_comments card is
    # fixed and never created via this endpoint (respects the partial unique
    # index uq_checkpoint_cards_one_final).
    card = CheckpointCard(
        checkpoint_id=cp.id,
        position=position,
        kind="review_point",
        prompt=body.prompt,
        document_id=body.document_id,
        chunk_id=body.chunk_id,
        objective_id=body.objective_id,
    )
    db.add(card)
    _bump_editing(cp)
    await db.commit()
    await db.refresh(card)
    await db.refresh(cp)  # repopulate onupdate-expired columns for later reads
    return APIResponse(success=True, data=CheckpointCardResponse.model_validate(card))
