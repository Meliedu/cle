"""Canvas LMS course-scoped endpoints — file listing/import + roster."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._helpers import verify_enrollment
from app.api.deps import get_db, require_instructor
from app.models import CanvasIntegration, CanvasSyncEvent, Document
from app.models.user import User
from app.schemas.common import APIResponse
from app.services import canvas_client as canvas_client_svc
from app.services import canvas_sync

router = APIRouter(prefix="/courses/{course_id}/canvas", tags=["canvas"])


class CanvasImportRequest(BaseModel):
    file_ids: list[str]


class RosterImportRequest(BaseModel):
    send_invite_emails: bool = False


def _file_to_dto(f: dict) -> dict:
    return {
        "canvas_file_id": str(f["id"]),
        "display_name": f.get("display_name"),
        "size": f.get("size"),
        "content_type": f.get("content-type") or f.get("content_type"),
        "download_url": f.get("url"),
        "updated_at": f.get("updated_at"),
    }


@router.get("/files", response_model=APIResponse[dict])
async def list_canvas_files(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[dict]:
    """Return Canvas files split into available vs already-imported buckets."""
    await verify_enrollment(db, course_id, user.id)

    integration = (
        await db.execute(
            select(CanvasIntegration).where(CanvasIntegration.course_id == course_id)
        )
    ).scalar_one_or_none()
    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Canvas not connected for this course",
        )

    try:
        client = await canvas_client_svc.get_client_for_user(
            db, integration.connected_by_user_id
        )
    except canvas_client_svc.CanvasNotConnected:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "canvas_reauth_required"},
        )
    except canvas_client_svc.CanvasReauthRequired:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "canvas_reauth_required"},
        )

    files = await client.list_course_files(integration.canvas_course_id)

    imported = (
        await db.execute(
            select(Document.canvas_file_id).where(
                Document.course_id == course_id,
                Document.canvas_file_id.is_not(None),
            )
        )
    ).scalars().all()
    imported_ids = {str(i) for i in imported}

    available = [_file_to_dto(f) for f in files if str(f["id"]) not in imported_ids]
    already = [_file_to_dto(f) for f in files if str(f["id"]) in imported_ids]

    return APIResponse(
        success=True,
        data={"available": available, "already_imported": already},
    )


@router.post("/files/import", response_model=APIResponse[dict])
async def import_canvas_files_endpoint(
    course_id: uuid.UUID,
    body: CanvasImportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[dict]:
    """Import selected Canvas files into Meli — download → R2 → enqueue process."""
    await verify_enrollment(db, course_id, user.id)

    integration = (
        await db.execute(
            select(CanvasIntegration).where(CanvasIntegration.course_id == course_id)
        )
    ).scalar_one_or_none()
    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Canvas not connected for this course",
        )

    try:
        client = await canvas_client_svc.get_client_for_user(
            db, integration.connected_by_user_id
        )
    except canvas_client_svc.CanvasNotConnected:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "canvas_reauth_required"},
        )
    except canvas_client_svc.CanvasReauthRequired:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "canvas_reauth_required"},
        )

    from app.services.canvas_files import import_canvas_files

    result = await import_canvas_files(
        db, client, course_id, body.file_ids, uploaded_by=user.id
    )
    return APIResponse(
        success=True,
        data={
            "imported": result.imported,
            "skipped": result.skipped,
            "errors": result.errors,
        },
    )


@router.post("/roster/import", response_model=APIResponse[dict])
async def import_canvas_roster_endpoint(
    course_id: uuid.UUID,
    body: RosterImportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[dict]:
    """Reconcile the Meli course roster against its Canvas counterpart."""
    await verify_enrollment(db, course_id, user.id)

    integration = (
        await db.execute(
            select(CanvasIntegration).where(CanvasIntegration.course_id == course_id)
        )
    ).scalar_one_or_none()
    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Canvas not connected for this course",
        )

    try:
        client = await canvas_client_svc.get_client_for_user(
            db, integration.connected_by_user_id
        )
    except canvas_client_svc.CanvasNotConnected:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "canvas_reauth_required"},
        )
    except canvas_client_svc.CanvasReauthRequired:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "canvas_reauth_required"},
        )

    from app.services.canvas_roster import sync_roster

    diff = await sync_roster(
        db,
        client,
        course_id,
        integration.canvas_course_id,
        body.send_invite_emails,
        preserve_user_ids={integration.connected_by_user_id},
    )
    integration.last_roster_sync_at = datetime.now(timezone.utc)
    await db.commit()

    return APIResponse(
        success=True,
        data={
            "added": diff.added,
            "unchanged": diff.unchanged,
            "dropped": diff.dropped,
            "pending": diff.pending,
            "skipped_off_domain": diff.skipped_off_domain,
            "errors": diff.errors,
        },
    )


@router.post("/sync", response_model=APIResponse[dict])
async def trigger_manual_sync(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[dict]:
    """Run a roster diff + file scan immediately for this course's integration."""
    await verify_enrollment(db, course_id, user.id)

    integration = (
        await db.execute(
            select(CanvasIntegration).where(CanvasIntegration.course_id == course_id)
        )
    ).scalar_one_or_none()
    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Canvas not connected for this course",
        )

    await canvas_sync.sync_integration(db, integration)
    await db.refresh(integration)

    return APIResponse(
        success=True,
        data={
            "sync_status": integration.sync_status,
            "last_roster_sync_at": integration.last_roster_sync_at.isoformat()
            if integration.last_roster_sync_at
            else None,
            "last_file_scan_at": integration.last_file_scan_at.isoformat()
            if integration.last_file_scan_at
            else None,
        },
    )


@router.get("/sync-events", response_model=APIResponse[list[dict]])
async def list_sync_events(
    course_id: uuid.UUID,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
) -> APIResponse[list[dict]]:
    """Return the most recent CanvasSyncEvent rows for a course, newest first."""
    await verify_enrollment(db, course_id, user.id)
    limit = max(1, min(limit, 200))

    rows = (
        await db.execute(
            select(CanvasSyncEvent)
            .where(CanvasSyncEvent.course_id == course_id)
            .order_by(CanvasSyncEvent.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    return APIResponse(
        success=True,
        data=[
            {
                "id": str(row.id),
                "event_type": row.event_type,
                "payload": row.payload,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    )
