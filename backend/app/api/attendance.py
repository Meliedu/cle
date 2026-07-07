"""Attendance router (P3 T9): teacher QR launch (token signing + gate).

``POST /checkpoints/{id}/launch`` is owner-guarded (mirrors the ownership helper
in ``api/checkpoints.py``). It gates + signs a QR launch via
``services/checkpoint_qr.py`` and returns the signed, window-bound token. The
gate refusal surfaces as the typed ``QR_NOT_AVAILABLE`` code (§3.4) the mobile
flow switches on. The T10 scan endpoint (``/attend/{token}``) lands in this same
router.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._helpers import verify_enrollment as _verify_enrollment
from app.api.checkpoints import _owned_checkpoint
from app.api.deps import require_instructor, require_student
from app.database import get_db
from app.models.checkpoint import Checkpoint
from app.models.user import User
from app.schemas.attendance import LaunchRequest, LaunchResponse, ScanResponse
from app.schemas.common import APIResponse
from app.services.checkpoint_attendance import (
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

    record = await record_scan(
        db, launch=launch, checkpoint=checkpoint, user_id=user.id
    )
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
