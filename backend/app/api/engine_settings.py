import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_owned_course, require_instructor
from app.models import EngineOverride
from app.models.course import Course
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.decision import (
    EngineOverrideResponse,
    EngineOverrideUpdate,
    EngineSettingsResponse,
    EngineSettingsUpdate,
)

router = APIRouter(tags=["engine-settings"])


@router.get(
    "/courses/{course_id}/engine",
    response_model=APIResponse[EngineSettingsResponse],
)
async def get_engine_settings(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[EngineSettingsResponse]:
    n = (
        await db.execute(
            select(func.count())
            .select_from(EngineOverride)
            .where(EngineOverride.course_id == course.id)
        )
    ).scalar_one()
    return APIResponse(
        success=True,
        data=EngineSettingsResponse(
            course_id=course.id,
            mode=course.adaptive_engine_mode,
            overrides_count=int(n),
        ),
    )


@router.patch(
    "/courses/{course_id}/engine",
    response_model=APIResponse[EngineSettingsResponse],
)
async def patch_engine_settings(
    body: EngineSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[EngineSettingsResponse]:
    course.adaptive_engine_mode = body.mode
    await db.commit()
    await db.refresh(course)
    return await get_engine_settings(db=db, course=course)


@router.put(
    "/courses/{course_id}/engine/overrides/{user_id}",
    response_model=APIResponse[EngineOverrideResponse],
)
async def upsert_engine_override(
    user_id: uuid.UUID,
    body: EngineOverrideUpdate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
    actor: User = Depends(require_instructor),
) -> APIResponse[EngineOverrideResponse]:
    now = datetime.now(timezone.utc)
    stmt = (
        pg_insert(EngineOverride)
        .values(
            user_id=user_id,
            course_id=course.id,
            mode=body.mode,
            set_by=actor.id,
            set_at=now,
        )
        .on_conflict_do_update(
            index_elements=["user_id", "course_id"],
            set_={"mode": body.mode, "set_by": actor.id, "set_at": now},
        )
    )
    await db.execute(stmt)
    await db.commit()
    row = (
        await db.execute(
            select(EngineOverride).where(
                EngineOverride.user_id == user_id,
                EngineOverride.course_id == course.id,
            )
        )
    ).scalar_one()
    return APIResponse(
        success=True, data=EngineOverrideResponse.model_validate(row)
    )


@router.delete(
    "/courses/{course_id}/engine/overrides/{user_id}",
    response_model=APIResponse[dict],
)
async def delete_engine_override(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[dict]:
    result = await db.execute(
        delete(EngineOverride).where(
            EngineOverride.user_id == user_id,
            EngineOverride.course_id == course.id,
        )
    )
    await db.commit()
    return APIResponse(
        success=True, data={"deleted": result.rowcount or 0}
    )
