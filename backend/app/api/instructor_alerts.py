import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_owned_course, require_instructor
from app.models import InstructorAlert
from app.models.course import Course
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.decision import (
    AlertStatus,
    InstructorAlertResponse,
    InstructorAlertUpdate,
)

router = APIRouter(tags=["instructor-alerts"])


@router.get(
    "/courses/{course_id}/alerts",
    response_model=APIResponse[list[InstructorAlertResponse]],
)
async def list_alerts(
    status: AlertStatus = Query(default="open"),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[list[InstructorAlertResponse]]:
    rows = (
        await db.execute(
            select(InstructorAlert)
            .where(
                InstructorAlert.course_id == course.id,
                InstructorAlert.status == status,
            )
            .order_by(InstructorAlert.severity.desc(), InstructorAlert.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return APIResponse(
        success=True,
        data=[InstructorAlertResponse.model_validate(r) for r in rows],
    )


@router.patch(
    "/courses/{course_id}/alerts/{alert_id}",
    response_model=APIResponse[InstructorAlertResponse],
)
async def update_alert(
    alert_id: uuid.UUID,
    body: InstructorAlertUpdate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
    actor: User = Depends(require_instructor),
) -> APIResponse[InstructorAlertResponse]:
    row = (
        await db.execute(
            select(InstructorAlert).where(
                InstructorAlert.id == alert_id,
                InstructorAlert.course_id == course.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    row.status = body.status
    row.resolved_at = datetime.now(timezone.utc)
    row.resolved_by = actor.id
    await db.commit()
    await db.refresh(row)
    return APIResponse(success=True, data=InstructorAlertResponse.model_validate(row))
