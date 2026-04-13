"""Canvas LMS integration endpoints — import course files from Canvas."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._helpers import verify_enrollment
from app.api.deps import get_db, require_instructor
from app.models.integration import CanvasIntegration
from app.models.user import User
from app.schemas.common import APIResponse
from app.services.crypto import decrypt_secret, encrypt_secret
from app.services.url_safety import validate_canvas_base_url

router = APIRouter(prefix="/courses/{course_id}/canvas", tags=["canvas"])


class CanvasConnectRequest(BaseModel):
    canvas_base_url: str
    canvas_course_id: str
    access_token: str


class CanvasImportRequest(BaseModel):
    file_ids: list[str]


@router.post("/connect", response_model=APIResponse[None], status_code=201)
async def connect_canvas(
    course_id: uuid.UUID,
    body: CanvasConnectRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    """Connect a Meli course to a Canvas course."""
    await verify_enrollment(db, course_id, user.id)

    try:
        normalized_url = validate_canvas_base_url(body.canvas_base_url)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )

    if not body.access_token.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="access_token is required"
        )

    existing = await db.execute(
        select(CanvasIntegration).where(
            CanvasIntegration.course_id == course_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Canvas already connected for this course",
        )

    integration = CanvasIntegration(
        course_id=course_id,
        canvas_course_id=body.canvas_course_id,
        canvas_base_url=normalized_url,
        access_token_encrypted=encrypt_secret(body.access_token),
    )
    db.add(integration)
    await db.commit()
    return APIResponse(success=True, data=None)


@router.get("/files", response_model=APIResponse[list])
async def list_canvas_files(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    """List files available in the connected Canvas course."""
    await verify_enrollment(db, course_id, user.id)

    result = await db.execute(
        select(CanvasIntegration).where(
            CanvasIntegration.course_id == course_id
        )
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Canvas not connected for this course",
        )

    try:
        validate_canvas_base_url(integration.canvas_base_url)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Stored Canvas URL is no longer permitted: {exc}",
        )

    if not integration.access_token_encrypted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Canvas integration is missing access token",
        )
    try:
        access_token = decrypt_secret(integration.access_token_encrypted)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Canvas access token cannot be decrypted",
        )

    from app.services.canvas import CanvasClient

    client = CanvasClient(integration.canvas_base_url, access_token)
    try:
        files = await client.list_course_files(integration.canvas_course_id)
        return APIResponse(success=True, data=files)
    finally:
        await client.close()


@router.post("/import", response_model=APIResponse[None])
async def import_canvas_files(
    course_id: uuid.UUID,
    body: CanvasImportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    """Import selected files from Canvas into Meli.

    Flow: download from Canvas → upload to R2 → create document record → create processing task.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Canvas file import not yet implemented",
    )
