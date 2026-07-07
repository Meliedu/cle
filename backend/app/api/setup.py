"""Course-setup wizard router (Task 8): state, analyze/analysis, publish/reopen.

Reuses the Task 4 service layer (``app.services.setup``): step flags live in
``courses.setup_checklist``; ``publish``/``reopen`` drive the course-open gate
(Decision 1). ``SetupGateError.code`` is mapped to a structured ``detail`` the
wizard branches on — ``SETUP_INCOMPLETE``/``SETUP_NOT_OPEN`` → 409,
``UNKNOWN_STEP`` → 422.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_course, require_instructor
from app.database import get_db
from app.models.course import Course
from app.models.evidence import CourseRecordItem
from app.models.task import Task
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.memory import ImportMemoryRequest, ImportMemoryResponse
from app.schemas.setup import (
    SetupAnalysisResponse,
    SetupStateResponse,
    SetupStepUpdate,
)
from app.services.audit import record_audit_event
from app.services.carry_forward_memory import (
    build_import_blocks,
    merge_imported_blocks,
)
from app.services.setup import (
    SETUP_STEP_KEYS,
    SetupGateError,
    missing_steps,
    publish_setup,
    reopen_setup,
    set_step_flag,
)

router = APIRouter(prefix="/courses/{course_id}/setup", tags=["setup"])


def _state(course: Course) -> SetupStateResponse:
    checklist = course.setup_checklist or {}
    return SetupStateResponse(
        setup_status=course.setup_status,
        context_status=course.context_status,
        steps={k: bool(checklist.get(k)) for k in SETUP_STEP_KEYS},
        missing=missing_steps(course),
    )


def _gate_http(exc: SetupGateError) -> HTTPException:
    # SETUP_INCOMPLETE / SETUP_NOT_OPEN are conflict states; UNKNOWN_STEP is a
    # bad step key (client-boundary) → 422.
    status_code = 422 if exc.code == "UNKNOWN_STEP" else 409
    return HTTPException(
        status_code=status_code, detail={"code": exc.code, "message": exc.message}
    )


@router.get("", response_model=APIResponse[SetupStateResponse])
async def get_setup(course: Course = Depends(get_owned_course)):
    return APIResponse(success=True, data=_state(course))


@router.patch("", response_model=APIResponse[SetupStateResponse])
async def patch_setup(
    body: SetupStepUpdate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
):
    try:
        await set_step_flag(db, course, body.step, body.done)
    except SetupGateError as exc:
        raise _gate_http(exc)
    return APIResponse(success=True, data=_state(course))


@router.post("/analyze", response_model=APIResponse[None], status_code=202)
async def analyze(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
):
    db.add(
        Task(
            task_type="analyze_course_setup",
            payload={"course_id": str(course.id)},
            status="pending",
        )
    )
    await db.commit()
    return APIResponse(success=True, data=None)


@router.get("/analysis", response_model=APIResponse[SetupAnalysisResponse])
async def get_analysis(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
):
    # Latest completed analyze task for this course. Task.payload is JSON — use
    # the ->> operator (CLAUDE.md convention), never .astext. The worker stores
    # the handler return under payload['result'] (see worker.complete_task).
    row = (
        await db.execute(
            select(Task)
            .where(
                Task.task_type == "analyze_course_setup",
                Task.payload.op("->>")("course_id") == str(course.id),
                Task.status == "completed",
            )
            .order_by(desc(Task.completed_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    analysis = (row.payload or {}).get("result") if row else None
    return APIResponse(
        success=True,
        data=SetupAnalysisResponse(ready=analysis is not None, analysis=analysis),
    )


@router.post("/publish", response_model=APIResponse[SetupStateResponse])
async def publish(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
):
    try:
        await publish_setup(db, course)
    except SetupGateError as exc:
        raise _gate_http(exc)
    return APIResponse(success=True, data=_state(course))


@router.post(
    "/import-memory", response_model=APIResponse[ImportMemoryResponse]
)
async def import_memory(
    body: ImportMemoryRequest,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
    user: User = Depends(require_instructor),
) -> APIResponse[ImportMemoryResponse]:
    """Import prior-term ``carry_forward`` memory into this course (T023 unstub).

    NOT a publish-gate step (mirrors the P1 stub decision) — it's a standalone
    owner-guarded action. Each item must resolve to one the caller owns whose
    ``decision`` is ``carry_forward``; an undecided / ``reject`` / ``keep`` item is
    refused with 409 ``MEMORY_UNDECIDED`` (Decision 6). Accepted items' reviewed
    instructor summaries (NO student ``user_id``) are copied onto the new course's
    ``setup_checklist`` and threaded into checkpoint-generation grounding; the
    import is audited (``memory.import``).
    """
    items: list[CourseRecordItem] = []
    for item_id in body.item_ids:
        item = await db.get(CourseRecordItem, item_id)
        if item is None:
            raise HTTPException(
                status_code=404, detail="Memory item not found"
            )
        # The source item must belong to a course the caller owns — memory never
        # crosses instructors (Decision 6). 404 (not 403) so existence isn't leaked.
        source = await db.get(Course, item.course_id)
        if (
            source is None
            or source.deleted_at is not None
            or source.instructor_id != user.id
        ):
            raise HTTPException(
                status_code=404, detail="Memory item not found"
            )
        if item.decision != "carry_forward":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "MEMORY_UNDECIDED",
                    "message": (
                        "Only items decided 'carry_forward' can be imported; "
                        f"item {item_id} is '{item.decision or 'undecided'}'."
                    ),
                },
            )
        items.append(item)

    if items:
        course.setup_checklist = merge_imported_blocks(
            course, build_import_blocks(items)
        )
        await record_audit_event(
            db,
            course_id=course.id,
            actor_id=user.id,
            event_type="memory.import",
            target_kind="course",
            target_id=course.id,
            metadata={"item_ids": [str(i.id) for i in items]},
        )
    await db.commit()
    return APIResponse(
        success=True,
        data=ImportMemoryResponse(
            imported_count=len(items),
            imported_item_ids=[i.id for i in items],
        ),
    )


@router.post("/reopen", response_model=APIResponse[SetupStateResponse])
async def reopen(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
):
    await reopen_setup(db, course)
    return APIResponse(success=True, data=_state(course))
