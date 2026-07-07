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

from app.api.deps import get_current_user, get_owned_course, require_instructor
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
    CheckpointPublishRequest,
    CheckpointResponse,
    CheckpointScheduleRequest,
    CheckpointWithCardsResponse,
)
from app.schemas.common import APIResponse
from app.services.checkpoints import IllegalTransition, assert_transition

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
                # Spec typed-error taxonomy (§3.4): the FE switches on
                # SETUP_INCOMPLETE | SETUP_NOT_OPEN | FINAL_CARD_FIXED |
                # REVIEW_REQUIRED, so this must be REVIEW_REQUIRED.
                "code": "REVIEW_REQUIRED",
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
    # Ensure onupdate-managed columns (updated_at) are populated before
    # serialization — a prior card edit in the same session expires them.
    await db.refresh(cp)
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
        # No un-remove branch: removing soft-deletes (deleted_at), and
        # _load_card 404s on deleted_at, so a removed card can never be edited
        # back. Un-remove is a P3 concern once card history is exposed.
        for field in ("prompt", "document_id", "chunk_id", "objective_id", "removed_note"):
            if field in fields:
                setattr(card, field, fields[field])

    _bump_editing(cp)
    await db.commit()
    await db.refresh(card)  # pull the onupdate-refreshed updated_at
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
    await db.refresh(card)  # pull the server-generated created_at/updated_at
    return APIResponse(success=True, data=CheckpointCardResponse.model_validate(card))


# ----- publish path: approve / schedule / publish / close (P3 T5) -----
#
# Every state change routes through ``assert_transition`` (the T1 service — the
# single source of truth for legal edges, Decision 1). T1's map deliberately
# forbids skip-edges: ``draft→approved`` and ``published→closed`` are illegal, so
# ``approve`` walks ``draft→teacher_editing→approved`` and ``close`` walks
# ``published→live→closed`` — one asserted step at a time.
#
# ``review_actions`` audit note: the repo's ``review_actions`` table
# (``models/evidence.py``) is the reviewed-evidence loop's append-only log and is
# hard-bound to a ``learning_note_id`` with an ``action_type`` CHECK that has no
# checkpoint verbs, so it cannot hold publish-path transitions. T5 is scoped to
# the router (no migration), so the transition audit trail is appended to
# ``checkpoint.generation_meta['review_actions']`` — an immutable-style list of
# ``{action, from, to, actor_id, at}`` entries.


def _review_required(message: str) -> HTTPException:
    """A typed ``REVIEW_REQUIRED`` gate refusal (§3.4), HTTP 409."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "REVIEW_REQUIRED", "message": message},
    )


def _apply_transition(cp: Checkpoint, *targets: str) -> None:
    """Walk ``cp.status`` through each target, asserting every edge via T1.

    Any illegal edge raises ``IllegalTransition`` which the caller maps to a
    ``REVIEW_REQUIRED`` 409.
    """
    for target in targets:
        assert_transition(cp.status, target)
        cp.status = target


def _append_review_action(
    cp: Checkpoint, action: str, from_status: str, actor_id: uuid.UUID
) -> None:
    """Append an audit entry to ``generation_meta['review_actions']``.

    Immutable update: a fresh dict/list is assigned so SQLAlchemy flags the
    JSONB column dirty (in-place mutation would not be detected).
    """
    meta = dict(cp.generation_meta or {})
    actions = list(meta.get("review_actions", []))
    actions.append(
        {
            "action": action,
            "from": from_status,
            "to": cp.status,
            "actor_id": str(actor_id),
            "at": _utcnow().isoformat(),
        }
    )
    meta["review_actions"] = actions
    cp.generation_meta = meta


@router.post("/{checkpoint_id}/approve", response_model=APIResponse[CheckpointResponse])
async def approve_checkpoint(
    checkpoint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[CheckpointResponse]:
    """``draft``/``teacher_editing`` → ``approved`` (§4.2).

    Gate: at least one non-removed ``review_point`` card AND the fixed
    ``final_comments`` card must be present, else ``REVIEW_REQUIRED``.
    """
    cp = await _owned_checkpoint(checkpoint_id, user, db)
    from_status = cp.status

    cards = await _load_cards(db, cp.id)
    review_points = [
        c for c in cards if c.kind == "review_point" and not c.removed
    ]
    finals = [c for c in cards if c.kind == "final_comments"]
    if not review_points or not finals:
        raise _review_required(
            "A checkpoint needs at least one review point and the final "
            "comments card before it can be approved."
        )

    try:
        # draft→approved is a skip-edge (illegal in T1); walk via teacher_editing.
        if cp.status == "draft":
            _apply_transition(cp, "teacher_editing", "approved")
        else:
            _apply_transition(cp, "approved")
    except IllegalTransition as exc:
        raise _review_required(exc.message) from exc

    _append_review_action(cp, "approve", from_status, user.id)
    await db.commit()
    await db.refresh(cp)
    return APIResponse(success=True, data=CheckpointResponse.model_validate(cp))


@router.post("/{checkpoint_id}/schedule", response_model=APIResponse[CheckpointResponse])
async def schedule_checkpoint(
    checkpoint_id: uuid.UUID,
    body: CheckpointScheduleRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[CheckpointResponse]:
    """``approved`` → ``scheduled`` (§4.2).

    Gate: ``release_at`` and ``close_rule`` must be set (from the body, falling
    back to any values already on the checkpoint), else ``REVIEW_REQUIRED``.
    """
    cp = await _owned_checkpoint(checkpoint_id, user, db)
    from_status = cp.status

    if body.release_at is not None:
        cp.release_at = body.release_at
    if body.close_at is not None:
        cp.close_at = body.close_at
    if body.close_rule is not None:
        cp.close_rule = body.close_rule

    if cp.release_at is None or cp.close_rule is None:
        raise _review_required(
            "A release time and close rule are required to schedule a checkpoint."
        )

    try:
        _apply_transition(cp, "scheduled")
    except IllegalTransition as exc:
        raise _review_required(exc.message) from exc

    _append_review_action(cp, "schedule", from_status, user.id)
    await db.commit()
    await db.refresh(cp)
    return APIResponse(success=True, data=CheckpointResponse.model_validate(cp))


@router.post("/{checkpoint_id}/publish", response_model=APIResponse[CheckpointResponse])
async def publish_checkpoint(
    checkpoint_id: uuid.UUID,
    body: CheckpointPublishRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[CheckpointResponse]:
    """``approved``/``scheduled`` → ``published`` (§4.2).

    Gate (all required, else ``REVIEW_REQUIRED``): a session relation
    (``meeting_id``), release timing (``release_at``) and a close rule
    (``close_rule``). Illegal source states are refused by ``assert_transition``.
    """
    cp = await _owned_checkpoint(checkpoint_id, user, db)
    from_status = cp.status

    if body is not None:
        if body.release_at is not None:
            cp.release_at = body.release_at
        if body.close_at is not None:
            cp.close_at = body.close_at
        if body.close_rule is not None:
            cp.close_rule = body.close_rule

    if cp.meeting_id is None:
        raise _review_required(
            "A checkpoint must be attached to a session before it can be published."
        )
    if cp.release_at is None or cp.close_rule is None:
        raise _review_required(
            "A release time and close rule are required to publish a checkpoint."
        )

    try:
        _apply_transition(cp, "published")
    except IllegalTransition as exc:
        raise _review_required(exc.message) from exc

    _append_review_action(cp, "publish", from_status, user.id)
    await db.commit()
    await db.refresh(cp)
    return APIResponse(success=True, data=CheckpointResponse.model_validate(cp))


@router.post("/{checkpoint_id}/close", response_model=APIResponse[CheckpointResponse])
async def close_checkpoint(
    checkpoint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[CheckpointResponse]:
    """``published``/``live`` → ``closed`` (§4.2).

    ``published→closed`` is a skip-edge (illegal in T1), so a publish that never
    went ``live`` is walked ``published→live→closed`` — each step asserted.
    """
    cp = await _owned_checkpoint(checkpoint_id, user, db)
    from_status = cp.status

    try:
        if cp.status == "published":
            _apply_transition(cp, "live", "closed")
        else:
            _apply_transition(cp, "closed")
    except IllegalTransition as exc:
        raise _review_required(exc.message) from exc

    _append_review_action(cp, "close", from_status, user.id)
    await db.commit()
    await db.refresh(cp)
    return APIResponse(success=True, data=CheckpointResponse.model_validate(cp))
