import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_owned_course
from app.models import (
    Assignment,
    Course,
    CourseMeeting,
    Enrollment,
    User,
    WorkItem,
    WorkItemProgress,
)
from app.schemas.common import APIResponse
from app.schemas.curriculum import (
    CourseMeetingCreate,
    CourseMeetingResponse,
    CourseMeetingUpdate,
    MeetingReleaseStateRequest,
)

router = APIRouter(prefix="/courses/{course_id}", tags=["curriculum"])

MAX_CALENDAR_DAYS = 366

# release_state visibility axis (Decision 2). Legal transitions only — a
# terminal ``archived`` and no jumping straight from locked to completed.
# locked<->released is reversible (unrelease a session); released->completed
# marks it taught-and-visible; completed->archived retires it.
_RELEASE_TRANSITIONS: dict[str, set[str]] = {
    "locked": {"released"},
    "released": {"completed", "locked"},
    "completed": {"archived"},
    "archived": set(),
}


async def _accessible_course(
    course_id: uuid.UUID, user: User, db: AsyncSession
) -> Course:
    """Resolve a course accessible to an enrolled student OR the owning instructor."""
    result = await db.execute(
        select(Course).join(Enrollment, Enrollment.course_id == Course.id).where(
            Course.id == course_id,
            Enrollment.user_id == user.id,
            Enrollment.status == "active",
            Course.deleted_at.is_(None),
        )
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        )
    return course


@router.post("/meetings", response_model=APIResponse[CourseMeetingResponse], status_code=201)
async def create_meeting(
    body: CourseMeetingCreate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[CourseMeetingResponse]:
    meeting = CourseMeeting(course_id=course.id, **body.model_dump())
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
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[list[CourseMeetingResponse]]:
    result = await db.execute(
        select(CourseMeeting)
        .where(CourseMeeting.course_id == course.id, CourseMeeting.deleted_at.is_(None))
        .order_by(CourseMeeting.scheduled_at)
    )
    meetings = result.scalars().all()
    return APIResponse(
        success=True,
        data=[CourseMeetingResponse.model_validate(m) for m in meetings],
    )


@router.put("/meetings/{meeting_id}", response_model=APIResponse[CourseMeetingResponse])
async def update_meeting(
    meeting_id: uuid.UUID,
    body: CourseMeetingUpdate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[CourseMeetingResponse]:
    result = await db.execute(
        select(CourseMeeting).where(
            CourseMeeting.id == meeting_id,
            CourseMeeting.course_id == course.id,
            CourseMeeting.deleted_at.is_(None),
        )
    )
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(meeting, field, value)
    # Fix 9: return 409 on meeting_index conflict instead of letting it crash with 500
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


@router.patch(
    "/meetings/{meeting_id}/release-state",
    response_model=APIResponse[CourseMeetingResponse],
)
async def set_release_state(
    meeting_id: uuid.UUID,
    body: MeetingReleaseStateRequest,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[CourseMeetingResponse]:
    """Transition a meeting's ``release_state`` (student visibility axis) and,
    optionally, set its ``topic_summary`` (schedule-and-venue step, T018).

    Instructor + ownership enforced via ``get_owned_course`` (404 on non-owner).
    Only the legal transitions in ``_RELEASE_TRANSITIONS`` are allowed; anything
    else returns a typed 409 the UI maps.
    """
    result = await db.execute(
        select(CourseMeeting).where(
            CourseMeeting.id == meeting_id,
            CourseMeeting.course_id == course.id,
            CourseMeeting.deleted_at.is_(None),
        )
    )
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found"
        )

    target = body.release_state
    if target not in _RELEASE_TRANSITIONS.get(meeting.release_state, set()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "ILLEGAL_RELEASE_TRANSITION",
                "message": (
                    f"Illegal release_state transition "
                    f"{meeting.release_state}->{target}"
                ),
            },
        )

    meeting.release_state = target
    if body.topic_summary is not None:
        meeting.topic_summary = body.topic_summary
    await db.commit()
    await db.refresh(meeting)
    return APIResponse(success=True, data=CourseMeetingResponse.model_validate(meeting))


@router.delete("/meetings/{meeting_id}", response_model=APIResponse[None])
async def delete_meeting(
    meeting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[None]:
    result = await db.execute(
        select(CourseMeeting).where(
            CourseMeeting.id == meeting_id,
            CourseMeeting.course_id == course.id,
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
    user: User = Depends(get_current_user),
) -> APIResponse[list[dict]]:
    """Return meetings + assignments in [from_date, to_date) as a flat event list.

    Fix 2: Accessible to enrolled students (sees only published assignments) and
    the course instructor (sees all assignments). Non-enrolled users get 404.
    Fix 11: Date range capped at 366 days.
    """
    # Fix 2: enrollment check — instructor or enrolled student
    course = await _accessible_course(course_id, user, db)

    if from_date >= to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="from_date must be before to_date",
        )
    # Fix 11: cap date range
    if (to_date - from_date).days > MAX_CALENDAR_DAYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Date range exceeds 366 days",
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

    # Fix 2: students only see published assignments; instructors see all
    assignment_filter = [
        Assignment.course_id == course_id,
        Assignment.deleted_at.is_(None),
        Assignment.due_at >= from_date,
        Assignment.due_at < to_date,
    ]
    is_instructor = user.id == course.instructor_id
    if not is_instructor:
        assignment_filter.append(Assignment.is_published.is_(True))

    assignments = (
        await db.execute(select(Assignment).where(*assignment_filter))
    ).scalars().all()

    # P4 B7 (Decision 5): merge a THIRD source — course work_items whose
    # ``due_at`` OR ``close_at`` falls in [from_date, to_date). The event ``at``
    # uses ``due_at`` when present, else ``close_at``. A student gets their OWN
    # ``work_item_progress.status`` overlaid (owner-scoped).
    #
    # ``visible_from`` release gate (P7 B11, Decision 9.1): an item with a FUTURE
    # ``visible_from`` is not yet released and is hidden here too (kept in lock-step
    # with the checklist); a past or NULL ``visible_from`` shows.
    now = datetime.now(timezone.utc)
    in_window = lambda col: (col >= from_date) & (col < to_date)  # noqa: E731
    work_items = (
        await db.execute(
            select(WorkItem).where(
                WorkItem.course_id == course_id,
                WorkItem.deleted_at.is_(None),
                or_(in_window(WorkItem.due_at), in_window(WorkItem.close_at)),
                or_(
                    WorkItem.visible_from.is_(None),
                    WorkItem.visible_from <= now,
                ),
            )
        )
    ).scalars().all()

    # Owner-scoped progress overlay: only the calling student's own rows.
    progress_by_item: dict[uuid.UUID, str] = {}
    if not is_instructor and work_items:
        progress_rows = (
            await db.execute(
                select(WorkItemProgress).where(
                    WorkItemProgress.user_id == user.id,
                    WorkItemProgress.work_item_id.in_([w.id for w in work_items]),
                )
            )
        ).scalars().all()
        progress_by_item = {p.work_item_id: p.status for p in progress_rows}

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
    for w in work_items:
        event_at = w.due_at if w.due_at is not None else w.close_at
        event = {
            "id": str(w.id),
            "kind": "work_item",
            "title": w.title,
            "at": event_at.isoformat(),
            "source_kind": w.source_kind,
            "required": w.required,
        }
        # Student-only: overlay this student's own progress (default pending).
        if not is_instructor:
            event["status"] = progress_by_item.get(w.id, "pending")
        events.append(event)
    events.sort(key=lambda e: e["at"])
    return APIResponse(success=True, data=events)
