import logging

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.auth import detect_role_from_email, verify_clerk_token

logger = logging.getLogger(__name__)


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    auth_header = request.headers.get("Authorization")
    logger.info("Auth header for %s: %s", request.url.path, "present" if auth_header else "MISSING")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )

    token = auth_header.split(" ", 1)[1]

    try:
        claims = verify_clerk_token(token)
    except Exception as e:
        logger.error("JWT verification failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    clerk_id = claims.get("sub")
    email = claims.get("email", "")

    if not clerk_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
        )

    result = await db.execute(select(User).where(User.clerk_id == clerk_id))
    user = result.scalar_one_or_none()

    if user is None:
        try:
            role = detect_role_from_email(email)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email domain not allowed",
            )

        user = User(
            clerk_id=clerk_id,
            email=email,
            full_name=claims.get("name"),
            role=role,
            avatar_url=claims.get("image_url"),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

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
