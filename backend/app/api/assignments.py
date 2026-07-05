import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_owned_course, require_instructor
from app.models import (
    Assignment, AssignmentSubmission, Course, Enrollment, User,
)
from app.schemas.common import APIResponse
from app.schemas.curriculum import (
    AssignmentCreate, AssignmentResponse, AssignmentSubmissionResponse,
    AssignmentUpdate, SubmissionGrade, SubmissionUpsert,
)

router = APIRouter(prefix="/courses/{course_id}/assignments", tags=["curriculum"])

# Slack to absorb clock skew between client and server. Submissions that
# land within this window after due_at are still treated as on-time.
LATE_GRACE = timedelta(minutes=5)


def _resolve_submission_status(
    requested: str, due_at: datetime | None, now: datetime
) -> str:
    """Server-side derivation of submission state.

    A client-supplied ``submitted`` is downgraded to ``late`` when ``now``
    is past ``due_at + LATE_GRACE``. Without this, a student can POST
    ``status='submitted'`` after the deadline and the row stays on-time —
    the overdue cron only flips ``not_started``/``in_progress`` rows.
    """
    if requested != "submitted" or due_at is None:
        return requested
    return "late" if now > due_at + LATE_GRACE else "submitted"


async def _enrolled(course_id: uuid.UUID, user: User, db: AsyncSession) -> Course:
    """Either enrolled student or course-owning instructor can read."""
    result = await db.execute(
        select(Course).join(Enrollment, Enrollment.course_id == Course.id)
        .where(
            Course.id == course_id,
            Enrollment.user_id == user.id,
            Course.deleted_at.is_(None),
        )
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Course not found")
    return c


@router.post("", response_model=APIResponse[AssignmentResponse], status_code=201)
async def create_assignment(
    body: AssignmentCreate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
):
    a = Assignment(course_id=course.id, created_by=course.instructor_id, **body.model_dump())
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return APIResponse(success=True, data=AssignmentResponse.model_validate(a))


@router.get("", response_model=APIResponse[list[AssignmentResponse]])
async def list_assignments(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    course = await _enrolled(course_id, user, db)
    base = select(Assignment).where(
        Assignment.course_id == course_id,
        Assignment.deleted_at.is_(None),
    )
    if user.id != course.instructor_id:
        base = base.where(Assignment.is_published.is_(True))
    base = base.order_by(Assignment.due_at)
    rows = (await db.execute(base)).scalars().all()
    return APIResponse(
        success=True,
        data=[AssignmentResponse.model_validate(a) for a in rows],
    )


@router.put("/{assignment_id}", response_model=APIResponse[AssignmentResponse])
async def update_assignment(
    assignment_id: uuid.UUID,
    body: AssignmentUpdate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
):
    res = await db.execute(
        select(Assignment).where(
            Assignment.id == assignment_id,
            Assignment.course_id == course.id,
            Assignment.deleted_at.is_(None),
        )
    )
    a = res.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    for f, v in body.model_dump(exclude_unset=True).items():
        setattr(a, f, v)
    await db.commit()
    await db.refresh(a)
    return APIResponse(success=True, data=AssignmentResponse.model_validate(a))


@router.delete("/{assignment_id}", response_model=APIResponse[None])
async def delete_assignment(
    assignment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
):
    res = await db.execute(
        select(Assignment).where(
            Assignment.id == assignment_id,
            Assignment.course_id == course.id,
            Assignment.deleted_at.is_(None),
        )
    )
    a = res.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    a.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return APIResponse(success=True, data=None)


# ----- submissions -----

@router.post(
    "/{assignment_id}/submission",
    response_model=APIResponse[AssignmentSubmissionResponse],
)
async def upsert_my_submission(
    course_id: uuid.UUID,
    assignment_id: uuid.UUID,
    body: SubmissionUpsert,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Student-side: create or update own submission."""
    await _enrolled(course_id, user, db)
    asn = (
        await db.execute(
            select(Assignment).where(
                Assignment.id == assignment_id,
                Assignment.course_id == course_id,
                Assignment.deleted_at.is_(None),
                Assignment.is_published.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not asn:
        raise HTTPException(status_code=404, detail="Assignment not found")

    res = await db.execute(
        select(AssignmentSubmission).where(
            AssignmentSubmission.assignment_id == assignment_id,
            AssignmentSubmission.user_id == user.id,
        )
    )
    sub = res.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    effective_status = _resolve_submission_status(body.status, asn.due_at, now)
    is_terminal_submit = effective_status in ("submitted", "late")
    if sub is None:
        sub = AssignmentSubmission(
            assignment_id=assignment_id, user_id=user.id, status=effective_status,
            submitted_at=now if is_terminal_submit else None,
            submission_payload=body.submission_payload,
        )
        db.add(sub)
    else:
        sub.status = effective_status
        if is_terminal_submit and sub.submitted_at is None:
            sub.submitted_at = now
        if body.submission_payload is not None:
            sub.submission_payload = body.submission_payload
    # Fix 8: handle concurrent upsert race via IntegrityError catch
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # Race: another request already created the row. Re-fetch and apply update.
        res = await db.execute(
            select(AssignmentSubmission).where(
                AssignmentSubmission.assignment_id == assignment_id,
                AssignmentSubmission.user_id == user.id,
            )
        )
        sub = res.scalar_one()
        sub.status = effective_status
        if is_terminal_submit and sub.submitted_at is None:
            sub.submitted_at = now
        if body.submission_payload is not None:
            sub.submission_payload = body.submission_payload
        await db.commit()
    await db.refresh(sub)
    return APIResponse(success=True, data=AssignmentSubmissionResponse.model_validate(sub))


@router.get(
    "/{assignment_id}/submissions",
    response_model=APIResponse[list[AssignmentSubmissionResponse]],
)
async def list_submissions(
    course_id: uuid.UUID,
    assignment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    # Fix 1: verify assignment belongs to this course before listing submissions
    asn = (
        await db.execute(
            select(Assignment).where(
                Assignment.id == assignment_id,
                Assignment.course_id == course_id,
                Assignment.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not asn:
        raise HTTPException(status_code=404, detail="Assignment not found")

    # Verify instructor owns this course (done after assignment check so both
    # conditions must be satisfied simultaneously; 404 avoids leaking info)
    course_check = (
        await db.execute(
            select(Course).where(
                Course.id == course_id,
                Course.instructor_id == user.id,
                Course.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not course_check:
        raise HTTPException(status_code=404, detail="Course not found")

    rows = (
        await db.execute(
            select(AssignmentSubmission).where(
                AssignmentSubmission.assignment_id == assignment_id,
            )
        )
    ).scalars().all()
    return APIResponse(
        success=True,
        data=[AssignmentSubmissionResponse.model_validate(s) for s in rows],
    )


@router.post(
    "/{assignment_id}/submissions/{submission_id}/grade",
    response_model=APIResponse[AssignmentSubmissionResponse],
)
async def grade_submission(
    course_id: uuid.UUID,
    assignment_id: uuid.UUID,
    submission_id: uuid.UUID,
    body: SubmissionGrade,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    # Fix 1: verify assignment belongs to this course before grading
    asn = (
        await db.execute(
            select(Assignment).where(
                Assignment.id == assignment_id,
                Assignment.course_id == course_id,
                Assignment.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not asn:
        raise HTTPException(status_code=404, detail="Assignment not found")

    course_check = (
        await db.execute(
            select(Course).where(
                Course.id == course_id,
                Course.instructor_id == user.id,
                Course.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not course_check:
        raise HTTPException(status_code=404, detail="Course not found")

    sub = (
        await db.execute(
            select(AssignmentSubmission).where(
                AssignmentSubmission.id == submission_id,
                AssignmentSubmission.assignment_id == assignment_id,
            )
        )
    ).scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    sub.score = body.score
    sub.feedback = body.feedback
    sub.status = body.status
    await db.commit()
    await db.refresh(sub)
    return APIResponse(success=True, data=AssignmentSubmissionResponse.model_validate(sub))
