import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models import ActionOutcome, Course, Enrollment, NextAction, User
from app.schemas.common import APIResponse
from app.schemas.decision import NextActionClickResponse, NextActionResponse
from app.services.next_actions import (
    get_or_recompute_next_actions,
    record_serve,
)

router = APIRouter(tags=["next-actions"])


async def _check_access(
    db: AsyncSession, user: User, course_id: uuid.UUID
) -> Course:
    """Enrollment OR ownership; 404 otherwise (mirrors mastery.py)."""
    course = (
        await db.execute(
            select(Course).where(
                Course.id == course_id, Course.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.instructor_id == user.id:
        return course
    enrolled = (
        await db.execute(
            select(Enrollment).where(
                Enrollment.user_id == user.id,
                Enrollment.course_id == course_id,
            )
        )
    ).scalar_one_or_none()
    if enrolled is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.get(
    "/users/me/courses/{course_id}/next-actions",
    response_model=APIResponse[list[NextActionResponse]],
)
async def list_next_actions(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[list[NextActionResponse]]:
    await _check_access(db, user, course_id)
    rows = await get_or_recompute_next_actions(
        db, user_id=user.id, course_id=course_id
    )
    served = await record_serve(db, [r.id for r in rows])

    # Telemetry: one observational action_outcomes row per served row.
    # Race-idempotent via the partial unique index
    # ``uq_action_outcomes_next_action_id`` (WHERE next_action_id IS NOT NULL).
    # The previous SELECT-then-INSERT could let two concurrent Today-page
    # requests both observe "no row exists" and both insert, inflating
    # served/clicked/completed counts in A/B summaries.
    if served:
        stmt = pg_insert(ActionOutcome).values([
            {
                "next_action_id": r.id,
                "user_id": r.user_id,
                "course_id": r.course_id,
                "action_type": r.action_type,
                "target_kind": r.target_kind,
                "target_id": r.target_id,
                "engine_variant": r.engine_variant,
                "served_at": r.served_at,
            }
            for r in served
        ]).on_conflict_do_nothing(
            index_elements=["next_action_id"],
            index_where=text("next_action_id IS NOT NULL"),
        )
        await db.execute(stmt)
        await db.commit()

    # If mode resolved to 'off' the list is empty; record a single off-arm
    # observational row so the A/B query has data on both sides. Cap to one
    # sentinel row per (user, course, calendar day) so off-arm students
    # polling the Today page don't inflate the A/B dataset.
    if not served:
        from app.services.engine_mode import resolve_engine_mode
        variant = await resolve_engine_mode(
            db, user_id=user.id, course_id=course_id
        )
        if variant == "off":
            today_cutoff = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            existing = (
                await db.execute(
                    select(ActionOutcome.id)
                    .where(
                        ActionOutcome.user_id == user.id,
                        ActionOutcome.course_id == course_id,
                        ActionOutcome.engine_variant == "off",
                        ActionOutcome.served_at >= today_cutoff,
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if existing is None:
                db.add(
                    ActionOutcome(
                        user_id=user.id,
                        course_id=course_id,
                        action_type="do_quiz",  # placeholder action_type for off-arm
                        engine_variant="off",
                        served_at=datetime.now(timezone.utc),
                    )
                )
                await db.commit()

    return APIResponse(
        success=True,
        data=[NextActionResponse.model_validate(r) for r in served],
    )


@router.post(
    "/next-actions/{action_id}/click",
    response_model=APIResponse[NextActionClickResponse],
)
async def click_next_action(
    action_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[NextActionClickResponse]:
    row = (
        await db.execute(
            select(NextAction).where(
                NextAction.id == action_id, NextAction.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Next action not found")

    now = datetime.now(timezone.utc)
    if row.clicked_at is None:
        row.clicked_at = now
    await db.execute(
        update(ActionOutcome)
        .where(ActionOutcome.next_action_id == action_id)
        .values(clicked=True)
    )
    await db.commit()

    return APIResponse(
        success=True,
        data=NextActionClickResponse(
            id=row.id,
            clicked_at=row.clicked_at,
            target_kind=row.target_kind,
            target_id=row.target_id,
        ),
    )
