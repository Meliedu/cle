import logging

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Enrollment, PendingEnrollment
from app.models.user import User
from app.services.auth import detect_role_from_email, verify_jwt

logger = logging.getLogger(__name__)


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )

    token = auth_header.split(" ", 1)[1]

    try:
        verified = verify_jwt(token)
    except Exception as exc:
        kid = None
        try:
            kid = jwt.get_unverified_header(token).get("kid")
        except Exception:
            pass
        logger.warning(
            "JWT verification failed: exc_class=%s kid=%s source_ip=%s",
            exc.__class__.__name__,
            kid,
            request.client.host if request.client else "-",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    claims = verified.claims
    auth_user_id = claims.get("sub")
    email = (claims.get("email") or "").strip()

    if not auth_user_id or not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
        )

    result = await db.execute(
        select(User).where(User.better_auth_id == auth_user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        try:
            role = detect_role_from_email(email)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email domain not allowed",
            )

        # Race-safe upsert: concurrent first-login requests both pass the
        # SELECT above and would otherwise both attempt an INSERT. ON CONFLICT
        # DO NOTHING collapses the duplicate; we then re-SELECT to get the
        # winning row.
        stmt = (
            insert(User)
            .values(
                better_auth_id=auth_user_id,
                email=email,
                full_name=claims.get("name"),
                role=role,
                avatar_url=claims.get("picture") or claims.get("image"),
            )
            .on_conflict_do_nothing(index_elements=["better_auth_id"])
        )
        await db.execute(stmt)
        await db.commit()

        result = await db.execute(
            select(User).where(User.better_auth_id == auth_user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="User provisioning failed",
            )

    # Re-sync stored email + re-derive role from the JWT on every request so
    # that revoked / domain-changed / role-elevated identities cannot keep
    # using a cached session.
    current_jwt_email = (claims.get("email") or "").strip().lower()
    if current_jwt_email:
        try:
            derived_role = detect_role_from_email(current_jwt_email)
        except ValueError:
            pass  # email domain not in allowlist — keep stored role
        else:
            mutated = False
            if user.role != derived_role:
                logger.warning(
                    "Role drift detected for user_id=%s: stored=%s "
                    "jwt_derived=%s — updating stored role",
                    user.id,
                    user.role,
                    derived_role,
                )
                user.role = derived_role
                mutated = True
            if user.email.lower() != current_jwt_email:
                user.email = current_jwt_email
                mutated = True
            if mutated:
                await db.commit()
                await db.refresh(user)

    # Claim any PendingEnrollment rows pre-provisioned for this email by a
    # Canvas roster sync. Runs on every authenticated request — cheap (indexed
    # email lookup) and safe because rows are deleted as they're claimed.
    pending_rows = (
        await db.execute(
            select(PendingEnrollment).where(
                PendingEnrollment.email == user.email.lower()
            )
        )
    ).scalars().all()
    if pending_rows:
        for row in pending_rows:
            db.add(
                Enrollment(
                    course_id=row.course_id, user_id=user.id, role=row.role
                )
            )
            await db.delete(row)
        try:
            await db.commit()
        except Exception:
            # If the user already has an Enrollment row for any of these
            # courses (race or duplicate claim), just roll back — the pending
            # rows will be revisited on a later request.
            await db.rollback()

    await db.execute(
        text("SELECT set_config('app.current_user_id', :uid, false)").bindparams(uid=str(user.id))
    )
    return user


async def require_instructor(user: User = Depends(get_current_user)) -> User:
    if user.role != "instructor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Instructor access required",
        )
    return user


async def require_student(user: User = Depends(get_current_user)) -> User:
    if user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student access required",
        )
    return user
