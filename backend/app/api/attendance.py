"""Attendance router (P3 T9): teacher QR launch (token signing + gate).

``POST /checkpoints/{id}/launch`` is owner-guarded (mirrors the ownership helper
in ``api/checkpoints.py``). It gates + signs a QR launch via
``services/checkpoint_qr.py`` and returns the signed, window-bound token. The
gate refusal surfaces as the typed ``QR_NOT_AVAILABLE`` code (§3.4) the mobile
flow switches on. The T10 scan endpoint (``/attend/{token}``) lands in this same
router.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._helpers import verify_enrollment as _verify_enrollment
from app.api.checkpoints import _owned_checkpoint
from app.api.deps import require_instructor, require_student
from app.database import get_db
from app.models.attendance import AttendanceRecord
from app.models.checkpoint import Checkpoint
from app.models.course import Course, Enrollment
from app.models.curriculum import CourseMeeting
from app.models.user import User
from app.schemas.attendance import (
    AttendanceOverrideRequest,
    AttendanceOverrideResponse,
    AttendanceRoster,
    AttendanceRosterEntry,
    LaunchRequest,
    LaunchResponse,
    ScanResponse,
)
from app.schemas.common import APIResponse
from app.services.checkpoint_attendance import (
    CheckpointNotLaunchable,
    LaunchClosed,
    record_scan,
    resolve_active_launch,
)
from app.services.checkpoint_qr import (
    LaunchTokenInvalid,
    QRNotAvailable,
    launch_checkpoint,
)

router = APIRouter(prefix="/checkpoints", tags=["attendance"])

# A SECOND, prefix-less router so the scan lands at the top-level
# ``/api/attend/{token}`` path (the ``/api`` prefix is applied by
# ``app.api.__init__``). The rate-limit regex ``^/api/attend/[^/]+$`` matches
# this exact mounted path.
attend_router = APIRouter(tags=["attendance"])

# Teacher roster + override (P3 T11) live on top-level meeting-/record-scoped
# paths (``/api/meetings/{id}/attendance``, ``/api/attendance/{id}``) — NOT the
# course-nested ``meetings`` router — so the panel addresses a meeting/record by
# its own id. Owner enforcement is done in-handler via the meeting's course.
meeting_router = APIRouter(prefix="/meetings", tags=["attendance"])
record_router = APIRouter(prefix="/attendance", tags=["attendance"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _owned_meeting(
    meeting_id: uuid.UUID, user: User, db: AsyncSession
) -> CourseMeeting:
    """Resolve a meeting the authenticated instructor owns (404 otherwise).

    Mirrors ``_owned_checkpoint`` — a non-owner (or a missing / soft-deleted
    meeting / course) is a 404 so course existence is never leaked.
    """
    meeting = await db.get(CourseMeeting, meeting_id)
    if meeting is None or meeting.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    course = await db.get(Course, meeting.course_id)
    if (
        course is None
        or course.deleted_at is not None
        or course.instructor_id != user.id
    ):
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meeting


def _append_override_action(
    meeting: CourseMeeting,
    record: AttendanceRecord,
    *,
    from_status: str,
    reason: str,
    actor_id: uuid.UUID,
) -> None:
    """Append an append-only override audit entry (mirrors T5's
    ``_append_review_action`` shape).

    The real ``review_actions`` table (``models/evidence.py``) is hard-bound to a
    ``learning_note_id`` with an ``action_type`` CHECK that has no attendance
    verbs, so — exactly as T5 did for checkpoint transitions — the audit trail is
    appended to a JSON column: here ``course_meetings.post_meeting_summary
    ['review_actions']``. A fresh dict/list is assigned so SQLAlchemy flags the
    JSONB column dirty (in-place mutation would go undetected).
    """
    summary = dict(meeting.post_meeting_summary or {})
    actions = list(summary.get("review_actions", []))
    actions.append(
        {
            "action": "attendance_override",
            "attendance_id": str(record.id),
            "user_id": str(record.user_id),
            "from": from_status,
            "to": record.status,
            "reason": reason,
            "actor_id": str(actor_id),
            "at": _utcnow().isoformat(),
        }
    )
    summary["review_actions"] = actions
    meeting.post_meeting_summary = summary


@router.post(
    "/{checkpoint_id}/launch",
    response_model=APIResponse[LaunchResponse],
    status_code=201,
)
async def launch_checkpoint_qr(
    checkpoint_id: uuid.UUID,
    body: LaunchRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[LaunchResponse]:
    """Mint (or rotate) a checkpoint's QR launch. Owner-guarded (404 otherwise).

    Refuses with ``QR_NOT_AVAILABLE`` (409) when the checkpoint is not
    ``published``/``live`` + session-bound + ``qr_enabled`` + within window, or
    when a live launch already exists and ``rotate`` was not requested.
    """
    cp = await _owned_checkpoint(checkpoint_id, user, db)
    rotate = bool(body and body.rotate)
    try:
        launch = await launch_checkpoint(
            db, checkpoint=cp, launched_by=user.id, rotate=rotate
        )
    except QRNotAvailable as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return APIResponse(success=True, data=LaunchResponse.model_validate(launch))


@attend_router.post(
    "/attend/{token}",
    response_model=APIResponse[ScanResponse],
)
async def scan_attendance(
    token: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_student),
) -> APIResponse[ScanResponse]:
    """Record a QR attendance scan and route the student into the checkpoint.

    Validates the launch token (signature + ``exp``) and its still-``active``
    launch row, requires the scanning student to be actively enrolled in the
    checkpoint's course, then idempotently upserts a single ``attendance_records``
    row (``source='qr'``, ``status=present|late``). A second scan is a 200 no-op
    (single-use per ``(meeting_id, user_id)``). Returns the checkpoint intro
    route (S034). Typed 4xx: ``LAUNCH_TOKEN_INVALID`` (401),
    ``LAUNCH_CLOSED`` (409).

    Attendance is participation ONLY — it never emits mastery / learning_event.
    """
    try:
        launch, _claims = await resolve_active_launch(db, token)
    except LaunchTokenInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "LAUNCH_TOKEN_INVALID",
                "message": "This QR code is invalid or has expired.",
            },
        ) from exc
    except LaunchClosed as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    checkpoint = await db.get(Checkpoint, launch.checkpoint_id)
    if checkpoint is None or checkpoint.deleted_at is not None:
        # The launch outlived its checkpoint (soft-deleted) — treat as closed.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "LAUNCH_CLOSED",
                "message": "This QR launch is no longer active.",
            },
        )

    # Enrollment-scoped (active only) — mirrors checkpoint_responses. 403 for a
    # non-enrolled / pending / rejected student.
    await _verify_enrollment(db, checkpoint.course_id, user.id)

    try:
        record = await record_scan(
            db, launch=launch, checkpoint=checkpoint, user_id=user.id
        )
    except CheckpointNotLaunchable as exc:
        # Scan-time re-check (P7 B11): the checkpoint left published/live under a
        # stale active launch — refuse with the typed code, no attendance written.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return APIResponse(
        success=True,
        data=ScanResponse(
            attendance_id=record.id,
            meeting_id=record.meeting_id,
            checkpoint_id=checkpoint.id,
            status=record.status,
            source=record.source,
            checked_in_at=record.checked_in_at,
            intro_route=f"/api/checkpoints/{checkpoint.id}/intro",
        ),
    )


# ----- teacher roster result (P3 T11, S037/T019) -----

# Roster status bucket order — every active student lands in exactly one.
_STATUS_KEYS = ("present", "late", "excused", "absent")


@meeting_router.get(
    "/{meeting_id}/attendance",
    response_model=APIResponse[AttendanceRoster],
)
async def get_meeting_attendance(
    meeting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[AttendanceRoster]:
    """Attendance roster for a meeting's course (owner-guarded; 404 non-owner).

    Every *active-enrolled student* (Enrollment status=active, role=student)
    appears exactly once. ``absent`` is DERIVED: a student with no
    ``attendance_records`` row for this meeting is reported ``absent`` (with a
    null ``attendance_id``). Instructors and pending rows never appear.

    Attendance is participation only — this read never touches mastery.
    """
    meeting = await _owned_meeting(meeting_id, user, db)

    # Active student roster (the denominator — mirrors checkpoints.py results).
    roster_rows = (
        await db.execute(
            select(Enrollment.user_id, User.full_name, User.email)
            .join(User, User.id == Enrollment.user_id)
            .where(
                Enrollment.course_id == meeting.course_id,
                Enrollment.status == "active",
                Enrollment.role == "student",
            )
            .order_by(User.full_name, User.email)
        )
    ).all()

    records = (
        await db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.meeting_id == meeting.id
            )
        )
    ).scalars().all()
    by_user = {rec.user_id: rec for rec in records}

    entries: list[AttendanceRosterEntry] = []
    counts = {key: 0 for key in _STATUS_KEYS}
    for user_id, full_name, email in roster_rows:
        rec = by_user.get(user_id)
        if rec is None:
            status_value = "absent"
            entries.append(
                AttendanceRosterEntry(
                    user_id=user_id,
                    full_name=full_name,
                    email=email,
                    status="absent",
                )
            )
        else:
            status_value = rec.status
            entries.append(
                AttendanceRosterEntry(
                    user_id=user_id,
                    full_name=full_name,
                    email=email,
                    status=rec.status,  # type: ignore[arg-type]
                    attendance_id=rec.id,
                    source=rec.source,
                    override_reason=rec.override_reason,
                    override_by=rec.override_by,
                    checked_in_at=rec.checked_in_at,
                )
            )
        counts[status_value] = counts.get(status_value, 0) + 1

    return APIResponse(
        success=True,
        data=AttendanceRoster(
            meeting_id=meeting.id,
            course_id=meeting.course_id,
            present_count=counts["present"],
            late_count=counts["late"],
            excused_count=counts["excused"],
            absent_count=counts["absent"],
            entries=entries,
        ),
    )


# ----- teacher manual override (P3 T11) -----


@record_router.patch(
    "/{attendance_id}",
    response_model=APIResponse[AttendanceOverrideResponse],
)
async def override_attendance(
    attendance_id: uuid.UUID,
    body: AttendanceOverrideRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[AttendanceOverrideResponse]:
    """Manually override one attendance record (owner-guarded; 404 non-owner).

    Sets ``status`` + a REQUIRED ``override_reason`` (422 if missing/blank at the
    schema boundary), stamps ``override_by`` = current user and
    ``source='manual_override'``, and appends an append-only audit entry to the
    meeting's ``post_meeting_summary['review_actions']`` (the real
    ``review_actions`` table can't hold attendance verbs — see T5).

    Attendance is participation only — an override NEVER emits mastery or a
    learning_event.
    """
    record = await db.get(AttendanceRecord, attendance_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    # Ownership via the record's meeting → course (404 on non-owner).
    meeting = await _owned_meeting(record.meeting_id, user, db)

    from_status = record.status
    record.status = body.status
    record.source = "manual_override"
    record.override_reason = body.override_reason
    record.override_by = user.id

    _append_override_action(
        meeting,
        record,
        from_status=from_status,
        reason=body.override_reason,
        actor_id=user.id,
    )

    await db.commit()
    await db.refresh(record)
    return APIResponse(
        success=True,
        data=AttendanceOverrideResponse(
            attendance_id=record.id,
            meeting_id=record.meeting_id,
            user_id=record.user_id,
            status=record.status,
            source=record.source,
            override_reason=record.override_reason,
            override_by=record.override_by,
            checked_in_at=record.checked_in_at,
        ),
    )
