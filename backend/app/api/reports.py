"""Reports router (P7).

B4 adds the enqueue-only end-term draft trigger. B5/B6 extend THIS file with the
teacher archive / detail / edit / approve / send + export endpoints — keep new
routes on the same ``router`` (and add ``reports_me_router`` for the student read
side in B7).

Drafting stays OFF the request path: this endpoint only *enqueues* per-student
``draft_report`` tasks (via ``enqueue_draft_reports``); the worker composes the
report from reviewed notes asynchronously (``run_draft_report``).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_course
from app.database import get_db
from app.models.course import Course
from app.schemas.common import APIResponse
from app.services.worker import _utcnow, enqueue_draft_reports

router = APIRouter(prefix="/courses/{course_id}/reports", tags=["reports"])

_VALID_PERIODS = ("weekly", "end_term")


@router.post("/draft", response_model=APIResponse[None], status_code=202)
async def draft_reports(
    period: str = Query("end_term"),
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
):
    """Owner-triggered draft fan-out. Enqueue-only.

    ``period`` selects the window: ``end_term`` (default) drafts an end-of-term
    report per active student; ``weekly`` is also accepted for an ad-hoc weekly
    pass. Idempotent per ``(course, user, period)`` via the enqueue dedupe.
    """
    if period not in _VALID_PERIODS:
        raise HTTPException(
            status_code=422,
            detail=f"period must be one of {_VALID_PERIODS}",
        )
    await enqueue_draft_reports(
        db, course_ids=[course.id], period=period, now=_utcnow()
    )
    await db.commit()
    return APIResponse(success=True, data=None)
