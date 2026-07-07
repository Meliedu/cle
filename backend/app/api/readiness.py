"""Readiness funnel router (spec §5): student-facing, pre-enrollment.

Endpoints:
- ``POST /courses/{id}/readiness/{phase}`` — persist a survey/ready-check phase
  (or compute the ``recommendation``) via the config-driven readiness service.
- ``GET  /courses/{id}/readiness/summary`` — the student's own completed phases.
- ``GET  /courses/{id}/preview`` — short/deep course preview, gated on a valid
  enroll code; deep preview additionally requires the course to be open.

Visibility is by a valid enroll code OR an existing enrollment — enrollment is
NOT required (that's the point of the funnel). A bad/inactive code yields 404 so
we never leak course existence (S004 invalid-inactive-join-code). All reads/writes
run through the authenticated user's session, so ``readiness_responses`` RLS
(owner isolation on ``app.current_user_id``) scopes rows automatically.
"""
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.course import Course, Enrollment
from app.models.curriculum import CourseMeeting, LearningObjective
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.readiness import (
    CoursePreviewOut,
    ReadinessResponseOut,
    ReadinessSubmit,
    ReadinessSummaryOut,
)
from app.services.readiness import ReadinessError, build_summary, submit_phase
from app.services.setup import SetupGateError, assert_course_open

router = APIRouter(prefix="/courses/{course_id}", tags=["readiness"])


def _norm(raw: str) -> str:
    """Normalize an enroll code the way the join funnel does (upper + alnum)."""
    return "".join(ch for ch in raw.upper() if ch.isalnum())


async def _visible_course(
    course_id: uuid.UUID, code: str | None, user: User, db: AsyncSession
) -> Course:
    """A course the student may see via a valid *active* code OR an enrollment.

    Always 404 (never 403) on a bad/inactive code so course existence is not
    leaked — the funnel renders this as S004 (invalid-inactive-join-code).
    """
    course = (
        await db.execute(
            select(Course).where(
                Course.id == course_id, Course.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if course is None:
        raise HTTPException(404, "Course not found")
    if code and course.enroll_code_active and _norm(code) == course.enroll_code:
        return course
    enrolled = (
        await db.execute(
            select(Enrollment).where(
                Enrollment.course_id == course_id,
                Enrollment.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if enrolled:
        return course
    raise HTTPException(404, "Course not found")


async def _deep_preview_detail(db: AsyncSession, course: Course) -> dict[str, int]:
    """Non-PII teaser for the deep preview: session + objective counts."""
    sessions = (
        await db.execute(
            select(func.count())
            .select_from(CourseMeeting)
            .where(
                CourseMeeting.course_id == course.id,
                CourseMeeting.deleted_at.is_(None),
            )
        )
    ).scalar_one()
    objectives = (
        await db.execute(
            select(func.count())
            .select_from(LearningObjective)
            .where(
                LearningObjective.course_id == course.id,
                LearningObjective.deleted_at.is_(None),
            )
        )
    ).scalar_one()
    return {"sessions": int(sessions), "objectives": int(objectives)}


@router.post("/readiness/{phase}", response_model=APIResponse[ReadinessResponseOut])
async def submit_readiness(
    course_id: uuid.UUID,
    phase: str,
    body: ReadinessSubmit,
    code: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    course = await _visible_course(course_id, code, user, db)
    try:
        row = await submit_phase(
            db, user=user, course=course, phase=phase, answers=body.answers
        )
    except ReadinessError as exc:
        # UNKNOWN_PHASE + INVALID_ANSWERS are both client-input faults; the UI
        # maps the typed ``code`` to funnel copy. 422 = unprocessable input.
        raise HTTPException(
            422, detail={"code": exc.code, "message": exc.message}
        )
    return APIResponse(success=True, data=ReadinessResponseOut.model_validate(row))


@router.get("/readiness/summary", response_model=APIResponse[ReadinessSummaryOut])
async def readiness_summary(
    course_id: uuid.UUID,
    code: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    course = await _visible_course(course_id, code, user, db)
    summary = await build_summary(db, user=user, course=course)
    return APIResponse(success=True, data=ReadinessSummaryOut(**summary))


@router.get("/preview", response_model=APIResponse[CoursePreviewOut])
async def course_preview(
    course_id: uuid.UUID,
    code: str | None = Query(default=None),
    depth: Literal["short", "deep"] = Query(default="short"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    course = await _visible_course(course_id, code, user, db)
    detail = None
    if depth == "deep":
        # Decision 3: a deep preview (S010) is gated behind the same course-open
        # authority as joining — a not-open course surfaces S012, not a teaser.
        try:
            assert_course_open(course)
        except SetupGateError as exc:
            raise HTTPException(
                409, detail={"code": exc.code, "message": exc.message}
            )
        detail = await _deep_preview_detail(db, course)
    return APIResponse(
        success=True,
        data=CoursePreviewOut(
            id=str(course.id),
            name=course.name,
            code=course.code,
            language=course.language,
            description=course.description,
            is_open=course.context_status == "approved",
            join_mode=course.join_mode,
            depth=depth,
            detail=detail,
        ),
    )
