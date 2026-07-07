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

from app.api.checkpoints import _owned_checkpoint
from app.api.deps import require_instructor
from app.database import get_db
from app.models.user import User
from app.schemas.attendance import LaunchRequest, LaunchResponse
from app.schemas.common import APIResponse
from app.services.checkpoint_qr import QRNotAvailable, launch_checkpoint

router = APIRouter(prefix="/checkpoints", tags=["attendance"])


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
