"""Canvas LMS integration endpoints — import course files from Canvas."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_instructor
from app.models.integration import CanvasIntegration
from app.models.user import User
from app.schemas.common import APIResponse

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
    # Check if already connected
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
        canvas_base_url=body.canvas_base_url,
        access_token_encrypted=body.access_token,  # TODO: encrypt before storing
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

    from app.services.canvas import CanvasClient

    client = CanvasClient(
        integration.canvas_base_url,
        integration.access_token_encrypted or "",
    )
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
