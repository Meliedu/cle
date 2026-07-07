"""Reports router (P7).

B4 adds the enqueue-only end-term draft trigger. B5 extends THIS file with the
teacher archive / detail / edit / approve endpoints; B6 adds send + export.

Two routers are exported:
- ``router`` under ``/courses/{course_id}/reports`` — course-scoped: the draft
  fan-out trigger (B4) + the archive list (B5), guarded by ``get_owned_course``.
- ``report_item_router`` under ``/reports`` — per-report: detail / edit / approve
  (B5), guarded by ``_get_owned_report`` (resolve report → its course → owner
  check, 404 on mismatch so course/report existence is never leaked — mirrors
  ``checkpoints.py::get_checkpoint_results``).

Drafting stays OFF the request path: the ``/draft`` endpoint only *enqueues*
per-student ``draft_report`` tasks (via ``enqueue_draft_reports``); the worker
composes the report from reviewed notes asynchronously (``run_draft_report``).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_course, require_instructor
from app.database import get_db
from app.models.course import Course
from app.models.report import Report
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.report import ReportResponse, ReportUpdate
from app.services.audit import record_audit_event
from app.services.worker import _utcnow, enqueue_draft_reports

router = APIRouter(prefix="/courses/{course_id}/reports", tags=["reports"])
# Per-report routes are NOT nested under a course — a report id is globally
# unique, so ownership is resolved from the report's own course (Decision 2).
report_item_router = APIRouter(prefix="/reports", tags=["reports"])

_VALID_PERIODS = ("weekly", "end_term")

# A report's typed ``body`` is only editable while it is still a ``draft`` — once
# reviewed/sent it is frozen (edits would desync the reviewed/sent evidence).
_EDITABLE_STATUSES = {"draft"}


async def _get_owned_report(
    report_id: uuid.UUID, user: User, db: AsyncSession
) -> Report:
    """Resolve a report whose course the authenticated instructor owns.

    404 (never 403) on a missing report OR a course the caller doesn't own, so
    report/course existence is never leaked — mirrors ``get_owned_course`` and
    ``checkpoints.py::_owned_checkpoint``.
    """
    report = await db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    course = await db.get(Course, report.course_id)
    if (
        course is None
        or course.deleted_at is not None
        or course.instructor_id != user.id
    ):
        raise HTTPException(status_code=404, detail="Report not found")
    return report


def _conflict(code: str, message: str) -> HTTPException:
    """A typed 409 refusal (§3.4 error-code envelope, mirrors checkpoints)."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": code, "message": message},
    )


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


@router.get("", response_model=APIResponse[list[ReportResponse]])
async def list_reports(
    audience: str | None = Query(None),
    period: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[list[ReportResponse]]:
    """Teacher report archive for a course (owner-guarded).

    Optional ``audience`` / ``period`` / ``status`` query params narrow the list;
    absent filters return every report for the course, newest first. Backed by
    the ``(course_id, audience, period)`` index.
    """
    stmt = select(Report).where(Report.course_id == course.id)
    if audience is not None:
        stmt = stmt.where(Report.audience == audience)
    if period is not None:
        stmt = stmt.where(Report.period == period)
    if status_filter is not None:
        stmt = stmt.where(Report.status == status_filter)
    stmt = stmt.order_by(Report.created_at.desc())

    rows = (await db.execute(stmt)).scalars().all()
    return APIResponse(
        success=True,
        data=[ReportResponse.model_validate(r) for r in rows],
    )


@report_item_router.get("/{report_id}", response_model=APIResponse[ReportResponse])
async def get_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[ReportResponse]:
    """Report detail incl. ``evidence_refs`` (owner-guarded via its course)."""
    report = await _get_owned_report(report_id, user, db)
    return APIResponse(success=True, data=ReportResponse.model_validate(report))


@report_item_router.patch(
    "/{report_id}", response_model=APIResponse[ReportResponse]
)
async def update_report(
    report_id: uuid.UUID,
    body: ReportUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[ReportResponse]:
    """Edit a ``draft`` report's typed ``body`` sections.

    Refuses (409 ``REPORT_NOT_EDITABLE``) once the report has left ``draft`` — a
    reviewed/sent report's body is frozen against its evidence.
    """
    report = await _get_owned_report(report_id, user, db)
    if report.status not in _EDITABLE_STATUSES:
        raise _conflict(
            "REPORT_NOT_EDITABLE",
            f"A report can only be edited while it is a draft (is '{report.status}').",
        )
    # Immutable update: assign a fresh dict so SQLAlchemy flags the JSONB dirty.
    report.body = dict(body.body)
    await db.commit()
    await db.refresh(report)
    return APIResponse(success=True, data=ReportResponse.model_validate(report))


@report_item_router.post(
    "/{report_id}/approve", response_model=APIResponse[ReportResponse]
)
async def approve_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[ReportResponse]:
    """``draft`` → ``reviewed`` (Decision 3).

    Sets ``reviewed_by`` / ``reviewed_at`` and appends an append-only
    ``audit_events`` row (``report.approve``) atomically with the transition.
    Approving anything but a ``draft`` is an illegal transition → 409
    ``REPORT_INVALID_TRANSITION``.
    """
    report = await _get_owned_report(report_id, user, db)
    if report.status != "draft":
        raise _conflict(
            "REPORT_INVALID_TRANSITION",
            f"A report can only be approved from 'draft' (is '{report.status}').",
        )
    report.status = "reviewed"
    report.reviewed_by = user.id
    report.reviewed_at = _utcnow()
    await record_audit_event(
        db,
        course_id=report.course_id,
        actor_id=user.id,
        event_type="report.approve",
        target_kind="report",
        target_id=report.id,
    )
    await db.commit()
    await db.refresh(report)
    return APIResponse(success=True, data=ReportResponse.model_validate(report))
