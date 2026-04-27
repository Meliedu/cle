"""Internal endpoints called by trusted local services.

Today: only the Better Auth Next.js app calls these — the
`databaseHooks.user.create.after` hook (sign-up linkage) and the
`user.deleteUser.beforeDelete` hook (account deletion) in
`frontend/src/lib/auth.ts`.

Authentication is a shared static secret in the `X-Internal-Auth` header,
matched against `settings.better_auth_internal_secret`. These routes are
NOT user-facing and must NEVER be exposed to the public internet.
"""

import hmac
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.course import Course
from app.models.document import Document
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.user import LinkUserRequest, LinkUserResponse
from app.services.auth import detect_role_from_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


def _verify_internal_secret(
    x_internal_auth: Annotated[str | None, Header(alias="X-Internal-Auth")] = None,
) -> None:
    expected = settings.better_auth_internal_secret
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal endpoint not configured",
        )
    if not x_internal_auth or not hmac.compare_digest(x_internal_auth, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal credentials",
        )


@router.post(
    "/users/link",
    response_model=APIResponse[LinkUserResponse],
    dependencies=[Depends(_verify_internal_secret)],
)
async def link_better_auth_user(
    payload: LinkUserRequest,
    db: AsyncSession = Depends(get_db),
):
    """Idempotently associate a Better Auth user id with our local users row.

    Resolution order:
      1. If a public.users row exists for this email, set its better_auth_id
         (this is the migration / re-link path — preserves the local UUID and
         every FK that points at it).
      2. Otherwise, create a new public.users row with the role derived from
         the email domain (this is the genuinely-new-user path).

    Returns the local user id and role so the frontend signup flow can route
    the user to the right post-signup destination.
    """
    email = payload.email.strip().lower()

    try:
        role = detect_role_from_email(email)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email domain not allowed",
        )

    existing = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()

    if existing is not None:
        # Existing row — link it. Refuse to clobber a different better_auth_id
        # already set on the row (would mean two Better Auth users want the
        # same local user, which should not happen given email uniqueness).
        if (
            existing.better_auth_id
            and existing.better_auth_id != payload.better_auth_id
        ):
            logger.error(
                "users.link: better_auth_id mismatch for email=%s "
                "stored=%s incoming=%s",
                email,
                existing.better_auth_id,
                payload.better_auth_id,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User already linked to a different Better Auth account",
            )

        existing.better_auth_id = payload.better_auth_id
        if payload.full_name and existing.full_name != payload.full_name:
            existing.full_name = payload.full_name
        if payload.avatar_url and existing.avatar_url != payload.avatar_url:
            existing.avatar_url = payload.avatar_url
        await db.commit()
        await db.refresh(existing)
        return APIResponse(
            success=True,
            data=LinkUserResponse(user_id=existing.id, role=existing.role),
        )

    # New user — create with derived role.
    new_user = User(
        better_auth_id=payload.better_auth_id,
        email=email,
        full_name=payload.full_name,
        role=role,
        avatar_url=payload.avatar_url,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return APIResponse(
        success=True,
        data=LinkUserResponse(user_id=new_user.id, role=new_user.role),
    )


class DeleteUserRequest(BaseModel):
    better_auth_id: str = Field(min_length=1, max_length=255)


class DeleteUserResponse(BaseModel):
    user_id: str
    deleted: bool


@router.post(
    "/users/delete",
    response_model=APIResponse[DeleteUserResponse],
    dependencies=[Depends(_verify_internal_secret)],
)
async def delete_better_auth_user(
    payload: DeleteUserRequest,
    db: AsyncSession = Depends(get_db),
):
    """Hard-delete the local users row linked to a Better Auth user id.

    Refuses the deletion if the user still owns content that does not have
    ON DELETE CASCADE — specifically courses (instructor-owned classrooms)
    and documents (uploaded materials). Those carry shared/educational
    value and must be transferred or removed first; auto-cascading them on
    a self-serve account deletion would silently orphan whole classrooms.

    Returns 200 with a uniform success-shape when the row was deleted *or*
    when no row exists locally (so Better Auth's beforeDelete hook can
    proceed in either case). The "row didn't exist" distinction is logged
    server-side only — the response intentionally doesn't expose it so a
    caller with the internal secret can't probe for the existence of a
    given better_auth_id. Returns 409 ``HAS_INSTRUCTOR_CONTENT`` when the
    user still owns content that doesn't cascade.
    """
    user = (
        await db.execute(
            select(User).where(User.better_auth_id == payload.better_auth_id)
        )
    ).scalar_one_or_none()

    if user is None:
        logger.info(
            "users/delete no-op for better_auth_id=%s (no public.users row)",
            payload.better_auth_id,
        )
        return APIResponse(
            success=True,
            data=DeleteUserResponse(user_id=payload.better_auth_id, deleted=True),
        )

    # Block deletion when the row owns content that doesn't cascade. The
    # frontend surfaces this as a structured error so the UI can guide the
    # user to clean up first.
    course_count = await db.scalar(
        select(func.count())
        .select_from(Course)
        .where(Course.instructor_id == user.id)
    )
    document_count = await db.scalar(
        select(func.count())
        .select_from(Document)
        .where(Document.uploaded_by == user.id)
    )

    if course_count or document_count:
        logger.info(
            "users/delete blocked for user_id=%s courses=%s documents=%s",
            user.id,
            course_count,
            document_count,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "HAS_INSTRUCTOR_CONTENT",
                "message": (
                    "This account still owns "
                    f"{course_count or 0} course(s) and {document_count or 0} "
                    "document(s). Transfer or delete them first, or contact "
                    "support to retire the account."
                ),
                "courses": int(course_count or 0),
                "documents": int(document_count or 0),
            },
        )

    user_id_str = str(user.id)
    await db.delete(user)
    await db.commit()
    logger.info("users/delete completed for user_id=%s", user_id_str)
    return APIResponse(
        success=True,
        data=DeleteUserResponse(user_id=user_id_str, deleted=True),
    )
