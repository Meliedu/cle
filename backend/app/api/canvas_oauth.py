"""Canvas OAuth + top-level (non-course-scoped) Canvas endpoints."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models import CanvasIntegration, CanvasUserCredential, User
from app.schemas.common import APIResponse
from app.services import canvas_client as canvas_client_svc
from app.services import canvas_oauth
from app.services.crypto import encrypt_secret

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/canvas", tags=["canvas-oauth"])


@router.get("/oauth/start", response_model=APIResponse[dict])
async def oauth_start(user: User = Depends(get_current_user)) -> APIResponse[dict]:
    """Return the Canvas authorize URL with a signed state JWT."""
    if not settings.canvas_client_id or not settings.canvas_state_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Canvas integration not configured",
        )
    state = canvas_oauth.encode_state(user.id)
    return APIResponse(
        success=True,
        data={"authorize_url": canvas_oauth.build_authorize_url(state)},
    )


@router.get("/oauth/callback", include_in_schema=False)
async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """OAuth redirect target — exchange code, store credential, redirect to UI."""
    try:
        user_id = canvas_oauth.decode_state(state)
    except canvas_oauth.StateInvalid:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    try:
        token_payload = await canvas_oauth.exchange_code(code)
    except httpx.HTTPError as exc:
        logger.warning("Canvas code exchange failed: %s", exc)
        raise HTTPException(status_code=502, detail="Canvas token exchange failed")

    access = token_payload["access_token"]
    refresh = token_payload["refresh_token"]
    expires_in = int(token_payload.get("expires_in", 3600))
    canvas_user_id = str(token_payload.get("user", {}).get("id", ""))
    if not canvas_user_id:
        raise HTTPException(status_code=502, detail="Canvas did not return user id")

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    now = datetime.now(timezone.utc)

    stmt = (
        pg_insert(CanvasUserCredential)
        .values(
            user_id=user_id,
            canvas_base_url=settings.canvas_base_url,
            canvas_user_id=canvas_user_id,
            access_token_encrypted=encrypt_secret(access),
            refresh_token_encrypted=encrypt_secret(refresh),
            access_token_expires_at=expires_at,
            scopes=settings.canvas_scopes,
            status="active",
        )
        .on_conflict_do_update(
            index_elements=["user_id"],
            set_={
                "canvas_base_url": settings.canvas_base_url,
                "canvas_user_id": canvas_user_id,
                "access_token_encrypted": encrypt_secret(access),
                "refresh_token_encrypted": encrypt_secret(refresh),
                "access_token_expires_at": expires_at,
                "scopes": settings.canvas_scopes,
                "status": "active",
                "updated_at": now,
            },
        )
    )
    await db.execute(stmt)
    await db.commit()

    frontend = settings.frontend_url.rstrip("/") if settings.frontend_url else ""
    return RedirectResponse(
        url=f"{frontend}/dashboard/canvas?connected=1",
        status_code=303,
    )


@router.delete("/connection", response_model=APIResponse[None])
async def disconnect_canvas(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[None]:
    """Revoke this user's Canvas credential and disconnect their integrations."""
    await db.execute(
        delete(CanvasUserCredential).where(CanvasUserCredential.user_id == user.id)
    )
    await db.execute(
        CanvasIntegration.__table__.update()
        .where(CanvasIntegration.connected_by_user_id == user.id)
        .values(sync_status="disconnected")
    )
    await db.commit()
    return APIResponse(success=True, data=None)


@router.get("/courses", response_model=APIResponse[list[dict]])
async def list_canvas_courses(
    role: str = Query("student", pattern="^(student|teacher)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[dict]]:
    """List the caller's Canvas courses for either a teacher or student role.

    For ``role=teacher`` the result includes both Teacher- and TA-enrolled
    courses, deduplicated by Canvas id. Each row is annotated with the
    matching Meli course id when one already exists for the same
    (canvas_base_url, canvas_course_id) pair.
    """
    if role == "teacher" and user.role != "instructor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Instructor access required",
        )

    try:
        client = await canvas_client_svc.get_client_for_user(db, user.id)
    except canvas_client_svc.CanvasNotConnected:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "canvas_not_connected"},
        )
    except canvas_client_svc.CanvasReauthRequired:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "canvas_reauth_required"},
        )

    enrollment_type = "teacher" if role == "teacher" else "student"
    courses = await client.list_my_courses(enrollment_type)

    if role == "teacher":
        ta_courses = await client.list_my_courses("ta")
        seen_ids = {c["id"] for c in courses}
        courses.extend(c for c in ta_courses if c["id"] not in seen_ids)

    canvas_ids = [str(c["id"]) for c in courses]
    if canvas_ids:
        rows = (
            await db.execute(
                select(CanvasIntegration).where(
                    CanvasIntegration.canvas_course_id.in_(canvas_ids),
                    CanvasIntegration.canvas_base_url == client._cred.canvas_base_url,
                    CanvasIntegration.sync_status != "disconnected",
                )
            )
        ).scalars().all()
        linked = {row.canvas_course_id: str(row.course_id) for row in rows}
    else:
        linked = {}

    return APIResponse(
        success=True,
        data=[
            {
                "canvas_course_id": str(c["id"]),
                "name": c.get("name"),
                "course_code": c.get("course_code"),
                "already_linked_meli_course_id": linked.get(str(c["id"])),
            }
            for c in courses
        ],
    )


@router.get("/connection", response_model=APIResponse[dict])
async def get_connection_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Return the caller's Canvas connection state."""
    row = (
        await db.execute(
            select(CanvasUserCredential).where(
                CanvasUserCredential.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return APIResponse(success=True, data={"connected": False})
    return APIResponse(
        success=True,
        data={
            "connected": True,
            "canvas_base_url": row.canvas_base_url,
            "canvas_user_id": row.canvas_user_id,
            "status": row.status,
        },
    )
