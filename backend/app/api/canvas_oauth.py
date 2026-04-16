"""Canvas OAuth + top-level (non-course-scoped) Canvas endpoints."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse as _urlparse

import httpx
from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Path,
    Query,
    Response,
    status,
)
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.courses import _generate_enroll_code
from app.api.deps import get_current_user, require_instructor
from app.config import settings
from app.database import get_db
from app.models import CanvasIntegration, CanvasUserCredential, PendingEnrollment, User
from app.models.course import Course, Enrollment
from app.schemas.common import APIResponse
from app.services import canvas_client as canvas_client_svc
from app.services import canvas_oauth
from app.services.crypto import encrypt_secret
from app.services.worker import _sanitize_error_message
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/canvas", tags=["canvas-oauth"])

# Evaluate the frontend scheme once at module load. ``settings.frontend_url``
# is validated at startup (url_safety.validate_frontend_url) to be either
# ``https://...`` or ``http://localhost...``, so the cookie's ``Secure`` flag
# tracks the true transport the browser will use — not the abstract
# environment name. Setting ``Secure`` when the frontend is served over
# plain-http localhost would make the cookie undeliverable in dev; leaving
# it off when the frontend is served over https would leak the nonce over
# any plaintext downgrade.
_FRONTEND_SCHEME = _urlparse(settings.frontend_url).scheme


@router.get("/oauth/start")
async def oauth_start(user: User = Depends(get_current_user)) -> JSONResponse:
    """Return the Canvas authorize URL with a signed state JWT.

    Also sets an HttpOnly, SameSite=Lax cookie containing the state nonce.
    The callback handler verifies the cookie against the JWT's embedded
    nonce to bind the OAuth flow to the browser session that started it
    (blocks state-fixation where a leaked state JWT is consumed by a
    different browser).
    """
    if not settings.canvas_client_id or not settings.canvas_state_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Canvas integration not configured",
        )
    state, nonce = canvas_oauth.encode_state(user.id)
    body = APIResponse(
        success=True,
        data={"authorize_url": canvas_oauth.build_authorize_url(state)},
    )
    response = JSONResponse(content=body.model_dump())
    response.set_cookie(
        key=canvas_oauth.STATE_COOKIE_NAME,
        value=nonce,
        max_age=canvas_oauth.STATE_TTL_SECONDS,
        httponly=True,
        secure=_FRONTEND_SCHEME == "https",
        samesite="lax",
        path="/api/canvas/oauth",
    )
    return response


@router.get("/oauth/callback", include_in_schema=False)
async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    canvas_oauth_nonce: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """OAuth redirect target — exchange code, store credential, redirect to UI."""
    if not settings.canvas_state_secret:
        # Never attempt to decode a state JWT with an unset secret — PyJWT
        # would either accept an empty key or raise an opaque error.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Canvas integration not configured: CANVAS_STATE_SECRET is unset",
        )
    try:
        user_id = await canvas_oauth.decode_state(state, canvas_oauth_nonce)
    except canvas_oauth.StateInvalid:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    try:
        token_payload = await canvas_oauth.exchange_code(code)
    except httpx.HTTPError as exc:
        logger.warning(
            "Canvas code exchange failed: %s", _sanitize_error_message(exc)
        )
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

    # settings.frontend_url is validated at startup (see config.py /
    # url_safety.validate_frontend_url): non-empty, https or localhost http,
    # and trailing slash already stripped. We can build the redirect
    # directly without a runtime falsey check.
    redirect = RedirectResponse(
        url=f"{settings.frontend_url}/dashboard/canvas?connected=1",
        status_code=303,
    )
    # Clear the session-binding cookie now that it has been consumed.
    redirect.delete_cookie(
        canvas_oauth.STATE_COOKIE_NAME, path="/api/canvas/oauth"
    )
    return redirect


@router.delete("/connection", response_model=APIResponse[None])
async def disconnect_canvas(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[None]:
    """Revoke this user's Canvas credential and disconnect their integrations.

    We ask Canvas to revoke the refresh token server-side before wiping the
    local credential row. ``revoke_token`` is best-effort and will never
    raise — a Canvas outage must not block the user from disconnecting
    locally. If the credential is already missing or marked invalid,
    ``get_client_for_user`` raises ``CanvasNotConnected`` / ``CanvasReauthRequired``
    and we skip the remote revoke.
    """
    try:
        client = await canvas_client_svc.get_client_for_user(db, user.id)
    except (
        canvas_client_svc.CanvasNotConnected,
        canvas_client_svc.CanvasReauthRequired,
    ):
        client = None
    if client is not None:
        await client.revoke_token()

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


@router.post(
    "/courses/{canvas_course_id}/link", response_model=APIResponse[dict]
)
async def link_canvas_course(
    canvas_course_id: str = Path(..., pattern=r"^\d+$"),
    user: User = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Link a Canvas course to a newly-created Meli course.

    The caller must currently hold a Teacher or TA enrollment on the Canvas
    side. Refuses to relink an already-linked (canvas_base_url, canvas_course_id)
    pair.
    """
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

    enrollments = await client.list_course_enrollments(canvas_course_id)
    cred_canvas_user_id = client._cred.canvas_user_id
    teacher_like = {"TeacherEnrollment", "TaEnrollment"}
    caller_roles = {
        e.get("type")
        for e in enrollments
        if str(e.get("user_id")) == str(cred_canvas_user_id)
    }
    if not (caller_roles & teacher_like):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a teacher or TA on this course",
        )

    existing = (
        await db.execute(
            select(CanvasIntegration).where(
                CanvasIntegration.canvas_course_id == canvas_course_id,
                CanvasIntegration.canvas_base_url == client._cred.canvas_base_url,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Course already linked to Meli",
        )

    canvas_course = await client.get_course(canvas_course_id)

    # Retry on the (vanishingly rare) enroll_code collision.
    meli_course: Course | None = None
    for _ in range(5):
        meli_course = Course(
            name=canvas_course.get("name") or f"Canvas Course {canvas_course_id}",
            code=canvas_course.get("course_code"),
            language="english",
            instructor_id=user.id,
            enroll_code=_generate_enroll_code(),
        )
        db.add(meli_course)
        try:
            await db.flush()
            break
        except IntegrityError:
            await db.rollback()
            meli_course = None
            continue

    if meli_course is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not allocate enrollment code, please retry",
        )

    db.add(
        CanvasIntegration(
            course_id=meli_course.id,
            connected_by_user_id=user.id,
            canvas_course_id=canvas_course_id,
            canvas_base_url=client._cred.canvas_base_url,
            sync_status="active",
        )
    )
    db.add(
        Enrollment(course_id=meli_course.id, user_id=user.id, role="instructor")
    )
    await db.commit()

    return APIResponse(success=True, data={"meli_course_id": str(meli_course.id)})


@router.post(
    "/courses/{canvas_course_id}/join", response_model=APIResponse[dict]
)
async def join_canvas_course(
    canvas_course_id: str = Path(..., pattern=r"^\d+$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Self-service student join via Canvas enrollment.

    The caller must currently hold a ``StudentEnrollment`` on the Canvas
    course. Returns 404 if no instructor has linked the course to Meli yet.
    """
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

    enrollments = await client.list_course_enrollments(canvas_course_id)
    cred_canvas_user_id = client._cred.canvas_user_id
    caller_types = {
        e.get("type")
        for e in enrollments
        if str(e.get("user_id")) == str(cred_canvas_user_id)
    }
    if "StudentEnrollment" not in caller_types:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a student on this Canvas course",
        )

    integration = (
        await db.execute(
            select(CanvasIntegration).where(
                CanvasIntegration.canvas_course_id == canvas_course_id,
                CanvasIntegration.canvas_base_url == client._cred.canvas_base_url,
                CanvasIntegration.sync_status != "disconnected",
            )
        )
    ).scalar_one_or_none()
    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Instructor hasn't enabled Meli for this course",
        )

    existing = (
        await db.execute(
            select(Enrollment).where(
                Enrollment.course_id == integration.course_id,
                Enrollment.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            Enrollment(
                course_id=integration.course_id,
                user_id=user.id,
                role="student",
            )
        )

    # Clean up any matching pre-provisioned pending row.
    await db.execute(
        delete(PendingEnrollment).where(
            PendingEnrollment.course_id == integration.course_id,
            PendingEnrollment.email == user.email.lower(),
        )
    )
    await db.commit()

    return APIResponse(
        success=True, data={"meli_course_id": str(integration.course_id)}
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
