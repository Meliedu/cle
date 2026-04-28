import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_instructor
from app.models import Assignment, Course, CourseMeeting, User
from app.schemas.common import APIResponse
from app.schemas.curriculum import (
    CourseMeetingCreate,
    CourseMeetingResponse,
    CourseMeetingUpdate,
)

router = APIRouter(prefix="/courses/{course_id}", tags=["curriculum"])


async def _own_course(
    course_id: uuid.UUID, user: User, db: AsyncSession
) -> Course:
    result = await db.execute(
        select(Course).where(
            Course.id == course_id,
            Course.instructor_id == user.id,
            Course.deleted_at.is_(None),
        )
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


@router.post("/meetings", response_model=APIResponse[CourseMeetingResponse], status_code=201)
async def create_meeting(
    course_id: uuid.UUID,
    body: CourseMeetingCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[CourseMeetingResponse]:
    await _own_course(course_id, user, db)
    meeting = CourseMeeting(course_id=course_id, **body.model_dump())
    db.add(meeting)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="meeting_index already used in this course",
        )
    await db.refresh(meeting)
    return APIResponse(success=True, data=CourseMeetingResponse.model_validate(meeting))


@router.get("/meetings", response_model=APIResponse[list[CourseMeetingResponse]])
async def list_meetings(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[list[CourseMeetingResponse]]:
    await _own_course(course_id, user, db)
    result = await db.execute(
        select(CourseMeeting)
        .where(CourseMeeting.course_id == course_id, CourseMeeting.deleted_at.is_(None))
        .order_by(CourseMeeting.scheduled_at)
    )
    meetings = result.scalars().all()
    return APIResponse(
        success=True,
        data=[CourseMeetingResponse.model_validate(m) for m in meetings],
    )


@router.put("/meetings/{meeting_id}", response_model=APIResponse[CourseMeetingResponse])
async def update_meeting(
    course_id: uuid.UUID,
    meeting_id: uuid.UUID,
    body: CourseMeetingUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[CourseMeetingResponse]:
    await _own_course(course_id, user, db)
    result = await db.execute(
        select(CourseMeeting).where(
            CourseMeeting.id == meeting_id,
            CourseMeeting.course_id == course_id,
            CourseMeeting.deleted_at.is_(None),
        )
    )
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(meeting, field, value)
    await db.commit()
    await db.refresh(meeting)
    return APIResponse(success=True, data=CourseMeetingResponse.model_validate(meeting))


@router.delete("/meetings/{meeting_id}", response_model=APIResponse[None])
async def delete_meeting(
    course_id: uuid.UUID,
    meeting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[None]:
    await _own_course(course_id, user, db)
    result = await db.execute(
        select(CourseMeeting).where(
            CourseMeeting.id == meeting_id,
            CourseMeeting.course_id == course_id,
            CourseMeeting.deleted_at.is_(None),
        )
    )
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    meeting.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return APIResponse(success=True, data=None)


@router.get("/calendar", response_model=APIResponse[list[dict]])
async def calendar_feed(
    course_id: uuid.UUID,
    from_date: datetime = Query(...),
    to_date: datetime = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[list[dict]]:
    """Return meetings + published assignments in [from_date, to_date) as a flat event list."""
    await _own_course(course_id, user, db)
    if from_date >= to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="from_date must be before to_date",
        )

    meetings = (
        await db.execute(
            select(CourseMeeting).where(
                CourseMeeting.course_id == course_id,
                CourseMeeting.deleted_at.is_(None),
                CourseMeeting.scheduled_at >= from_date,
                CourseMeeting.scheduled_at < to_date,
            )
        )
    ).scalars().all()

    assignments = (
        await db.execute(
            select(Assignment).where(
                Assignment.course_id == course_id,
                Assignment.deleted_at.is_(None),
                Assignment.is_published.is_(True),
                Assignment.due_at >= from_date,
                Assignment.due_at < to_date,
            )
        )
    ).scalars().all()

    events: list[dict] = []
    for m in meetings:
        events.append({
            "id": str(m.id),
            "kind": "meeting",
            "title": m.title or f"Meeting {m.meeting_index}",
            "at": m.scheduled_at.isoformat(),
            "duration_minutes": m.duration_minutes,
            "location": m.location,
            "status": m.status,
        })
    for a in assignments:
        events.append({
            "id": str(a.id),
            "kind": "assignment",
            "title": a.title,
            "at": a.due_at.isoformat(),
            "assignment_kind": a.kind,
            "weight": float(a.weight) if a.weight is not None else None,
        })
    events.sort(key=lambda e: e["at"])
    return APIResponse(success=True, data=events)
