import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_owned_course, require_instructor
from app.models.course import Course, Enrollment
from app.models.score import ScoreCategory
from app.models.user import User
from app.pilot import get_pilot_profile
from app.schemas.common import APIResponse, PaginatedResponse, PaginationMeta
from app.schemas.course import (
    CourseCreate,
    CourseResponse,
    CourseUpdate,
    EnrollByCodeRequest,
    EnrollByCodeResult,
    JoinRequestOut,
    RosterEntryOut,
)
from app.services.setup import SetupGateError, assert_course_open

# Avoid ambiguous chars (0/O, 1/I/L). Uppercase so codes are easy to dictate.
_ENROLL_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_ENROLL_CODE_LENGTH = 8


def _generate_enroll_code() -> str:
    return "".join(
        secrets.choice(_ENROLL_CODE_ALPHABET) for _ in range(_ENROLL_CODE_LENGTH)
    )


def _normalize_enroll_code(raw: str) -> str:
    return "".join(ch for ch in raw.upper() if ch.isalnum())

router = APIRouter(prefix="/courses", tags=["courses"])


@router.post("", response_model=APIResponse[CourseResponse], status_code=201)
async def create_course(
    body: CourseCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    # Retry a handful of times on the astronomically unlikely code collision.
    for _ in range(5):
        course = Course(
            name=body.name,
            code=body.code,
            description=body.description,
            language=body.language,
            semester=body.semester,
            settings=body.settings,
            instructor_id=user.id,
            enroll_code=_generate_enroll_code(),
        )
        db.add(course)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            continue

        enrollment = Enrollment(
            course_id=course.id, user_id=user.id, role="instructor", status="active"
        )
        db.add(enrollment)

        # Seed the pilot's default score categories (T024 score-policy step).
        for i, cat in enumerate(get_pilot_profile().score_category_defaults):
            db.add(
                ScoreCategory(
                    course_id=course.id,
                    name=cat.name,
                    weight=cat.weight,
                    sort=i,
                )
            )

        await db.commit()
        await db.refresh(course)
        return APIResponse(success=True, data=CourseResponse.model_validate(course))

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Could not allocate enrollment code, please retry",
    )


@router.get("", response_model=PaginatedResponse[CourseResponse])
async def list_courses(
    page: int = 1,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if page < 1 or limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pagination: page >= 1, 1 <= limit <= 100",
        )

    base = (
        select(Course)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .where(
            Enrollment.user_id == user.id,
            Enrollment.status == "active",
            Course.deleted_at.is_(None),
        )
    )

    count_result = await db.execute(
        select(func.count()).select_from(base.subquery())
    )
    total = int(count_result.scalar() or 0)

    result = await db.execute(
        base.order_by(Course.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    courses = result.scalars().all()
    pages = (total + limit - 1) // limit if total else 0
    return PaginatedResponse(
        success=True,
        data=[CourseResponse.model_validate(c) for c in courses],
        meta=PaginationMeta(total=total, page=page, limit=limit, pages=pages),
    )


@router.get("/{course_id}", response_model=APIResponse[CourseResponse])
async def get_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Active enrollment required: a ``pending`` student (awaiting approval on a
    # ``code_plus_approval`` course) must not read the workspace yet.
    enrollment = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == course_id,
            Enrollment.user_id == user.id,
            Enrollment.status == "active",
        )
    )
    if not enrollment.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.deleted_at.is_(None))
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    return APIResponse(success=True, data=CourseResponse.model_validate(course))


@router.put("/{course_id}", response_model=APIResponse[CourseResponse])
async def update_course(
    course_id: uuid.UUID,
    body: CourseUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(Course).where(
            Course.id == course_id,
            Course.instructor_id == user.id,
            Course.deleted_at.is_(None),
        )
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(course, field, value)

    await db.commit()
    await db.refresh(course)
    return APIResponse(success=True, data=CourseResponse.model_validate(course))


@router.delete("/{course_id}", response_model=APIResponse[None])
async def delete_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(Course).where(
            Course.id == course_id,
            Course.instructor_id == user.id,
            Course.deleted_at.is_(None),
        )
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    course.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return APIResponse(success=True, data=None)


@router.post(
    "/enroll-by-code",
    response_model=APIResponse[EnrollByCodeResult],
    status_code=201,
)
async def enroll_by_code(
    body: EnrollByCodeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Terminal student join action (Decision 1 + Decision 3).

    Gate order: normalize/validate format → resolve course (404, no existence
    leak) → code active? (``JOIN_CODE_INACTIVE``) → course open?
    (``assert_course_open`` → ``SETUP_NOT_OPEN``) → already enrolled?
    (idempotent, returns existing status) → create enrollment with status from
    ``join_mode`` (``code`` → ``active`` = instant join; ``code_plus_approval``
    → ``pending`` = awaits teacher approval).
    """
    code = _normalize_enroll_code(body.enroll_code)
    if len(code) != _ENROLL_CODE_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid enrollment code format",
        )

    result = await db.execute(
        select(Course).where(
            Course.enroll_code == code, Course.deleted_at.is_(None)
        )
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No course found for that code",
        )

    # Code-state gate before existence/openness so a deactivated code can't be
    # used to probe join outcomes.
    if not course.enroll_code_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "JOIN_CODE_INACTIVE",
                "message": "This join code is no longer active.",
            },
        )

    # Setup gate (Decision 3): students cannot join until the teacher published.
    try:
        assert_course_open(course)
    except SetupGateError as exc:  # SETUP_NOT_OPEN
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": exc.message},
        )

    existing = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == course.id, Enrollment.user_id == user.id
        )
    )
    existing_row = existing.scalar_one_or_none()
    if existing_row:
        # Idempotent: already have an enrollment row (any status) → return it so
        # the funnel routes on the current status rather than duplicating.
        return APIResponse(
            success=True,
            data=EnrollByCodeResult(
                course=CourseResponse.model_validate(course),
                enrollment_status=existing_row.status,
            ),
        )

    # join_mode maps to the initial enrollment status (Decision 1).
    new_status = "pending" if course.join_mode == "code_plus_approval" else "active"
    db.add(
        Enrollment(
            course_id=course.id, user_id=user.id, role=user.role, status=new_status
        )
    )
    try:
        await db.commit()
    except IntegrityError:
        # Race: a concurrent request created the enrollment first. Re-fetch and
        # return its status idempotently (unique(course_id, user_id)).
        await db.rollback()
        raced = (
            await db.execute(
                select(Enrollment).where(
                    Enrollment.course_id == course.id,
                    Enrollment.user_id == user.id,
                )
            )
        ).scalar_one()
        return APIResponse(
            success=True,
            data=EnrollByCodeResult(
                course=CourseResponse.model_validate(course),
                enrollment_status=raced.status,
            ),
        )
    return APIResponse(
        success=True,
        data=EnrollByCodeResult(
            course=CourseResponse.model_validate(course),
            enrollment_status=new_status,
        ),
    )


@router.post(
    "/{course_id}/enroll-code/rotate",
    response_model=APIResponse[CourseResponse],
)
async def rotate_enroll_code(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
):
    """Mint a fresh, unique enrollment code and (re)activate joining (T025).

    Rotating invalidates the previous code (it will no longer resolve via
    ``enroll-by-code``) and always leaves the course open to joins, so this
    doubles as the "reactivate with a new code" action after a deactivate.
    """
    for _ in range(5):
        course.enroll_code = _generate_enroll_code()
        course.enroll_code_active = True
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            continue
        await db.refresh(course)
        return APIResponse(success=True, data=CourseResponse.model_validate(course))

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Could not allocate enrollment code, please retry",
    )


@router.post(
    "/{course_id}/enroll-code/deactivate",
    response_model=APIResponse[CourseResponse],
)
async def deactivate_enroll_code(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
):
    """Stop accepting joins on the current code without discarding it (T025).

    The code string is preserved so the teacher can still reveal it or rotate
    to a fresh one later. The P2 join flow reads ``enroll_code_active`` to
    refuse joins; here we only flip the column.
    """
    course.enroll_code_active = False
    await db.commit()
    await db.refresh(course)
    return APIResponse(success=True, data=CourseResponse.model_validate(course))


@router.post("/{course_id}/enroll", response_model=APIResponse[None], status_code=201)
async def enroll_in_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.deleted_at.is_(None))
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    existing = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == course_id, Enrollment.user_id == user.id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already enrolled")

    enrollment = Enrollment(course_id=course_id, user_id=user.id, role=user.role)
    db.add(enrollment)
    await db.commit()
    return APIResponse(success=True, data=None)


def _join_request_out(enrollment: Enrollment, user: User) -> JoinRequestOut:
    return JoinRequestOut(
        enrollment_id=enrollment.id,
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        requested_at=enrollment.enrolled_at,
        status=enrollment.status,
    )


async def _decide_join_request(
    db: AsyncSession, course: Course, enrollment_id: uuid.UUID, new_status: str
) -> APIResponse[JoinRequestOut]:
    """Approve (-> active) or deny (-> rejected) a pending join request.

    Only ``pending`` rows are actionable — an already-decided row yields 409
    ``NOT_PENDING`` so a double-approve/deny is surfaced rather than silently
    reapplied.
    """
    row = (
        await db.execute(
            select(Enrollment, User)
            .join(User, User.id == Enrollment.user_id)
            .where(
                Enrollment.id == enrollment_id,
                Enrollment.course_id == course.id,
            )
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Join request not found"
        )
    enrollment, user = row
    if enrollment.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "NOT_PENDING",
                "message": f"Join request is already '{enrollment.status}'.",
            },
        )
    enrollment.status = new_status
    await db.commit()
    await db.refresh(enrollment)
    return APIResponse(success=True, data=_join_request_out(enrollment, user))


@router.get(
    "/{course_id}/join-requests",
    response_model=APIResponse[list[JoinRequestOut]],
)
async def list_join_requests(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
):
    """List pending enrollments awaiting the owning instructor's approval (T033)."""
    rows = (
        await db.execute(
            select(Enrollment, User)
            .join(User, User.id == Enrollment.user_id)
            .where(
                Enrollment.course_id == course.id,
                Enrollment.status == "pending",
            )
            .order_by(Enrollment.enrolled_at.asc())
        )
    ).all()
    return APIResponse(
        success=True, data=[_join_request_out(e, u) for e, u in rows]
    )


@router.post(
    "/{course_id}/join-requests/{enrollment_id}/approve",
    response_model=APIResponse[JoinRequestOut],
)
async def approve_join_request(
    enrollment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
):
    return await _decide_join_request(db, course, enrollment_id, "active")


@router.post(
    "/{course_id}/join-requests/{enrollment_id}/deny",
    response_model=APIResponse[JoinRequestOut],
)
async def deny_join_request(
    enrollment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
):
    return await _decide_join_request(db, course, enrollment_id, "rejected")


@router.get(
    "/{course_id}/roster",
    response_model=APIResponse[list[RosterEntryOut]],
)
async def list_roster(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
):
    """List active enrollments (students + instructors) for the class roster (T032)."""
    rows = (
        await db.execute(
            select(Enrollment, User)
            .join(User, User.id == Enrollment.user_id)
            .where(
                Enrollment.course_id == course.id,
                Enrollment.status == "active",
            )
            .order_by(Enrollment.enrolled_at.asc())
        )
    ).all()
    return APIResponse(
        success=True,
        data=[
            RosterEntryOut(
                enrollment_id=e.id,
                user_id=u.id,
                full_name=u.full_name,
                email=u.email,
                role=e.role,
                enrolled_at=e.enrolled_at,
                status=e.status,
            )
            for e, u in rows
        ],
    )
