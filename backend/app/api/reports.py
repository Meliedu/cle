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

from app.api._helpers import verify_enrollment
from app.api.deps import get_owned_course, require_instructor, require_student
from app.database import get_db
from app.models.course import Course
from app.models.evidence import LearningNote
from app.models.report import Report
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.report import (
    EvidenceAppendixItem,
    ReportExportResponse,
    ReportResponse,
    ReportShareSettings,
    ReportShareSettingsResponse,
    ReportUpdate,
)
from app.services.audit import record_audit_event
from app.services.worker import _utcnow, enqueue_draft_reports

router = APIRouter(prefix="/courses/{course_id}/reports", tags=["reports"])
# Per-report routes are NOT nested under a course — a report id is globally
# unique, so ownership is resolved from the report's own course (Decision 2).
report_item_router = APIRouter(prefix="/reports", tags=["reports"])
# Student-facing read side (B7): the caller reads ONLY their OWN delivered
# reports. Owner-isolation RLS keys on ``user_id`` in production; these endpoints
# ALSO filter ``user_id`` explicitly (defense-in-depth, since a superuser test /
# migration seam can bypass RLS) and restrict to ``audience='student'`` +
# ``status='sent'`` so pre-send draft content is NEVER exposed (Core §0.2).
me_router = APIRouter(prefix="/users/me", tags=["reports"])

_VALID_PERIODS = ("weekly", "end_term")

# A report's typed ``body`` is only editable while it is still a ``draft`` — once
# reviewed/sent it is frozen (edits would desync the reviewed/sent evidence).
_EDITABLE_STATUSES = {"draft"}

# Only reviewed / instructor-edited notes may surface in an export appendix — an
# unreviewed id that leaked into ``evidence_refs`` is filtered out defensively so
# no unreviewed content ever reaches an export (Core §0.2, Decision 1).
_APPENDIX_STATUSES = ("reviewed", "edited")

# Where the export-share flags live. B6 adds NO migration, so the flags are
# persisted under a reserved ``share_settings`` key inside the report's ``body``
# JSONB (operational metadata, kept separate from the drafted content sections).
_SHARE_SETTINGS_KEY = "share_settings"


def _require_sendable(report: Report) -> None:
    """The §3.4 "report can send" gate (Decision 3).

    Send/export are refused (409 ``REPORT_NOT_REVIEWED``) unless the report has
    been reviewed AND carries evidence — a report NEVER leaves review without
    reviewed evidence refs behind it.
    """
    if report.status != "reviewed" or not report.evidence_refs:
        raise _conflict(
            "REPORT_NOT_REVIEWED",
            "A report can only be sent or exported once it is reviewed and has "
            "evidence refs.",
        )


def _read_share_settings(report: Report) -> ReportShareSettings:
    """Resolve a report's stored export-share flags (defaults when unset)."""
    raw = (report.body or {}).get(_SHARE_SETTINGS_KEY)
    if isinstance(raw, dict):
        return ReportShareSettings.model_validate(raw)
    return ReportShareSettings()


async def _resolve_appendix(
    report: Report, db: AsyncSession
) -> list[EvidenceAppendixItem]:
    """Resolve ``evidence_refs`` → reviewed ``LearningNote`` rows only.

    Filters to ``review_status IN ('reviewed','edited')`` — an unreviewed id that
    leaked into ``evidence_refs`` is excluded (defensive; Core §0.2).
    """
    if not report.evidence_refs:
        return []
    stmt = select(LearningNote).where(
        LearningNote.id.in_(report.evidence_refs),
        LearningNote.review_status.in_(_APPENDIX_STATUSES),
    )
    notes = (await db.execute(stmt)).scalars().all()
    return [EvidenceAppendixItem.model_validate(n) for n in notes]


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


@report_item_router.post(
    "/{report_id}/send", response_model=APIResponse[ReportResponse]
)
async def send_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[ReportResponse]:
    """``reviewed`` → ``sent`` (Decision 3).

    GATED: refuses 409 ``REPORT_NOT_REVIEWED`` unless the report is ``reviewed``
    AND has non-empty ``evidence_refs``. On success sets ``sent_at`` and appends
    an append-only ``audit_events`` (``report.send``) row atomically with the
    transition (the student delivery state, S069, then flips to "sent").
    """
    report = await _get_owned_report(report_id, user, db)
    _require_sendable(report)
    report.status = "sent"
    report.sent_at = _utcnow()
    await record_audit_event(
        db,
        course_id=report.course_id,
        actor_id=user.id,
        event_type="report.send",
        target_kind="report",
        target_id=report.id,
    )
    await db.commit()
    await db.refresh(report)
    return APIResponse(success=True, data=ReportResponse.model_validate(report))


@report_item_router.post(
    "/{report_id}/export", response_model=APIResponse[ReportExportResponse]
)
async def export_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[ReportExportResponse]:
    """Export a reviewed report with its reviewed-evidence appendix (Decision 3).

    Same gate as ``/send`` (409 ``REPORT_NOT_REVIEWED``). Appends an entry to the
    report's ``export_history`` JSONB and an append-only ``audit_events``
    (``report.export``) row, then returns the export payload. The evidence
    appendix resolves ``evidence_refs`` → reviewed notes ONLY — an unreviewed id
    is filtered out defensively so no unreviewed content is ever exported.
    """
    report = await _get_owned_report(report_id, user, db)
    _require_sendable(report)

    exported_at = _utcnow()
    appendix = await _resolve_appendix(report, db)

    # Immutable append: reassign a fresh list so SQLAlchemy flags the JSONB dirty
    # (append-only export log — mirrors how B5 reassigns ``report.body``).
    entry = {
        "exported_at": exported_at.isoformat(),
        "actor_id": str(user.id),
        "evidence_count": len(appendix),
    }
    report.export_history = [*(report.export_history or []), entry]

    await record_audit_event(
        db,
        course_id=report.course_id,
        actor_id=user.id,
        event_type="report.export",
        target_kind="report",
        target_id=report.id,
        metadata={"evidence_count": len(appendix)},
    )
    await db.commit()
    await db.refresh(report)

    payload = ReportExportResponse(
        report=ReportResponse.model_validate(report),
        evidence_appendix=appendix,
        share_settings=_read_share_settings(report),
        exported_at=exported_at,
    )
    return APIResponse(success=True, data=payload)


@report_item_router.patch(
    "/{report_id}/share-settings",
    response_model=APIResponse[ReportShareSettingsResponse],
)
async def update_share_settings(
    report_id: uuid.UUID,
    settings: ReportShareSettings,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[ReportShareSettingsResponse]:
    """Persist a report's export-share flags (owner-guarded via its course).

    Stored under ``body['share_settings']`` (B6 adds no migration). Share flags
    are operational metadata, so they are settable regardless of report status
    (unlike the frozen content sections) — an immutable dict reassign flags the
    JSONB dirty.
    """
    report = await _get_owned_report(report_id, user, db)
    report.body = {**(report.body or {}), _SHARE_SETTINGS_KEY: settings.model_dump()}
    await db.commit()
    await db.refresh(report)
    return APIResponse(
        success=True,
        data=ReportShareSettingsResponse(
            report_id=report.id,
            share_settings=_read_share_settings(report),
        ),
    )


# ---------------------------------------------------------------------------
# Student read side (B7) — own delivered reports only (delivery state S069).
# ---------------------------------------------------------------------------
# The archive shell shows only ``status='sent'`` rows: a report that is still
# ``draft`` / ``reviewed`` is INVISIBLE to the student (the delivery state is
# "not yet sent" — never draft content). A report id is never trusted to imply
# access — every read re-filters on the caller's ``user_id``.
_STUDENT_REPORT_NOT_FOUND = "Report not found"


@me_router.get(
    "/courses/{course_id}/reports",
    response_model=APIResponse[list[ReportResponse]],
)
async def list_my_reports(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_student),
) -> APIResponse[list[ReportResponse]]:
    """The caller's delivered report archive for a course (student, own rows only).

    Enrollment-scoped (``verify_enrollment`` — active enrollment only, 403
    otherwise). Returns ONLY the caller's ``audience='student'`` AND
    ``status='sent'`` reports, newest first — a ``draft`` / ``reviewed`` report is
    never returned (no pre-send draft content ever reaches the student, Core
    §0.2). A student with nothing delivered gets an empty list (archive shell).
    """
    await verify_enrollment(db, course_id, user.id)

    stmt = (
        select(Report)
        .where(
            Report.course_id == course_id,
            Report.user_id == user.id,
            Report.audience == "student",
            Report.status == "sent",
        )
        .order_by(Report.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return APIResponse(
        success=True,
        data=[ReportResponse.model_validate(r) for r in rows],
    )


@me_router.get(
    "/reports/{report_id}", response_model=APIResponse[ReportResponse]
)
async def get_my_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_student),
) -> APIResponse[ReportResponse]:
    """One of the caller's OWN delivered reports (student).

    404 (never 403) unless the report exists, is owned by the caller
    (``user_id`` == caller), is student-audience, AND is ``sent`` — an unsent
    (draft/reviewed) own report and another student's report are both 404 so no
    existence or pre-send content is ever leaked (Core §0.2, Decision 3).
    """
    report = await db.get(Report, report_id)
    if (
        report is None
        or report.user_id != user.id
        or report.audience != "student"
        or report.status != "sent"
    ):
        raise HTTPException(
            status_code=404, detail=_STUDENT_REPORT_NOT_FOUND
        )
    # Defense-in-depth (matches insights.get_signal / review.get_follow_up_detail):
    # a non-active (dropped/rejected/pending) owner loses access to their OWN row.
    # 403 only ever fires for the caller's own report, so it leaks nothing.
    await verify_enrollment(db, report.course_id, user.id)
    return APIResponse(success=True, data=ReportResponse.model_validate(report))
