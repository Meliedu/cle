"""P4 B9: the ``mark_missed_work_items`` cron.

``mark_missed_work_items(session)`` sweeps every ``required`` work_item whose
deadline (``close_at``, falling back to ``due_at``) is past and flips the
``work_item_progress`` of each ACTIVELY-enrolled student who has not already
``completed``/``submitted`` (or otherwise reached a terminal state) to
``missed``. Students with NO progress row on a now-past-due required item get a
fresh ``missed`` row created (a never-started item is a missed item).

Interpretation notes (Decision recorded in B9):
- The deadline is ``close_at`` when present, else ``due_at``. An item with
  neither is never missed.
- Terminal / protected statuses that the cron never overwrites:
  ``completed``, ``submitted``, ``missed``, ``late``, ``follow_up_assigned``.
  A ``late`` row is a submission that arrived late — it is NOT missed.
  Only ``pending``/``in_progress`` rows are flippable.
- Only ``role='student'`` enrollments with ``status='active'`` are marked;
  ``pending``/``rejected`` enrollments are ignored.
- Non-``required`` items are never touched.
- Idempotent: a second run finds nothing to change and returns ``0``.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.models.course import Course, Enrollment
from app.models.work_item import WorkItem, WorkItemProgress
from app.services.work_items import mark_missed_work_items


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _make_course(db: AsyncSession, owner: User, code: str) -> Course:
    course = Course(
        name="Missed Cron Test",
        language="english",
        instructor_id=owner.id,
        enroll_code=code,
    )
    db.add(course)
    await db.flush()
    return course


async def _make_student(db: AsyncSession, suffix: str) -> User:
    student = User(
        better_auth_id=f"missed_stu_{suffix}",
        email=f"missed_stu_{suffix}@connect.ust.hk",
        full_name=f"Student {suffix}",
        role="student",
    )
    db.add(student)
    await db.flush()
    return student


async def _enroll(
    db: AsyncSession, course: Course, student: User, *, status: str = "active"
) -> Enrollment:
    enr = Enrollment(
        course_id=course.id, user_id=student.id, role="student", status=status
    )
    db.add(enr)
    await db.flush()
    return enr


async def _make_item(
    db: AsyncSession,
    course: Course,
    owner: User,
    *,
    required: bool = True,
    close_at: datetime | None = None,
    due_at: datetime | None = None,
) -> WorkItem:
    item = WorkItem(
        course_id=course.id,
        source_kind="checkpoint",
        source_id=uuid.uuid4(),
        title="cp",
        required=required,
        score_bearing=False,
        close_at=close_at,
        due_at=due_at,
        created_by=owner.id,
    )
    db.add(item)
    await db.flush()
    return item


async def _progress(
    db: AsyncSession, item: WorkItem, student: User, status: str
) -> WorkItemProgress:
    row = WorkItemProgress(work_item_id=item.id, user_id=student.id, status=status)
    db.add(row)
    await db.flush()
    return row


async def _status_of(
    db: AsyncSession, item: WorkItem, student: User
) -> str | None:
    row = (
        await db.execute(
            select(WorkItemProgress).where(
                WorkItemProgress.work_item_id == item.id,
                WorkItemProgress.user_id == student.id,
            )
        )
    ).scalar_one_or_none()
    return row.status if row is not None else None


@pytest.mark.asyncio
async def test_creates_missed_for_no_progress_student(
    db_session: AsyncSession, logged_in_user: User
):
    course = await _make_course(db_session, logged_in_user, "MISS001")
    student = await _make_student(db_session, "a")
    await _enroll(db_session, course, student)
    item = await _make_item(
        db_session, course, logged_in_user, close_at=_now() - timedelta(hours=1)
    )
    await db_session.commit()

    n = await mark_missed_work_items(db_session)
    assert n == 1
    assert await _status_of(db_session, item, student) == "missed"


@pytest.mark.asyncio
async def test_flips_pending_and_in_progress(
    db_session: AsyncSession, logged_in_user: User
):
    course = await _make_course(db_session, logged_in_user, "MISS002")
    s_pending = await _make_student(db_session, "p")
    s_prog = await _make_student(db_session, "ip")
    await _enroll(db_session, course, s_pending)
    await _enroll(db_session, course, s_prog)
    item = await _make_item(
        db_session, course, logged_in_user, close_at=_now() - timedelta(hours=1)
    )
    await _progress(db_session, item, s_pending, "pending")
    await _progress(db_session, item, s_prog, "in_progress")
    await db_session.commit()

    n = await mark_missed_work_items(db_session)
    assert n == 2
    assert await _status_of(db_session, item, s_pending) == "missed"
    assert await _status_of(db_session, item, s_prog) == "missed"


@pytest.mark.asyncio
async def test_never_touches_terminal_statuses(
    db_session: AsyncSession, logged_in_user: User
):
    course = await _make_course(db_session, logged_in_user, "MISS003")
    item = await _make_item(
        db_session, course, logged_in_user, close_at=_now() - timedelta(hours=1)
    )
    protected = {}
    for status in ("completed", "submitted", "missed", "late", "follow_up_assigned"):
        stu = await _make_student(db_session, f"t_{status}")
        await _enroll(db_session, course, stu)
        await _progress(db_session, item, stu, status)
        protected[status] = stu
    await db_session.commit()

    n = await mark_missed_work_items(db_session)
    assert n == 0
    for status, stu in protected.items():
        assert await _status_of(db_session, item, stu) == status


@pytest.mark.asyncio
async def test_ignores_non_required_items(
    db_session: AsyncSession, logged_in_user: User
):
    course = await _make_course(db_session, logged_in_user, "MISS004")
    student = await _make_student(db_session, "nr")
    await _enroll(db_session, course, student)
    item = await _make_item(
        db_session,
        course,
        logged_in_user,
        required=False,
        close_at=_now() - timedelta(hours=1),
    )
    await db_session.commit()

    n = await mark_missed_work_items(db_session)
    assert n == 0
    assert await _status_of(db_session, item, student) is None


@pytest.mark.asyncio
async def test_ignores_future_and_dateless_items(
    db_session: AsyncSession, logged_in_user: User
):
    course = await _make_course(db_session, logged_in_user, "MISS005")
    student = await _make_student(db_session, "fut")
    await _enroll(db_session, course, student)
    future = await _make_item(
        db_session, course, logged_in_user, close_at=_now() + timedelta(hours=1)
    )
    dateless = await _make_item(db_session, course, logged_in_user)
    await db_session.commit()

    n = await mark_missed_work_items(db_session)
    assert n == 0
    assert await _status_of(db_session, future, student) is None
    assert await _status_of(db_session, dateless, student) is None


@pytest.mark.asyncio
async def test_due_at_fallback_when_no_close_at(
    db_session: AsyncSession, logged_in_user: User
):
    course = await _make_course(db_session, logged_in_user, "MISS006")
    student = await _make_student(db_session, "due")
    await _enroll(db_session, course, student)
    item = await _make_item(
        db_session, course, logged_in_user, due_at=_now() - timedelta(hours=1)
    )
    await db_session.commit()

    n = await mark_missed_work_items(db_session)
    assert n == 1
    assert await _status_of(db_session, item, student) == "missed"


@pytest.mark.asyncio
async def test_only_active_enrollments(
    db_session: AsyncSession, logged_in_user: User
):
    course = await _make_course(db_session, logged_in_user, "MISS007")
    active = await _make_student(db_session, "act")
    pending = await _make_student(db_session, "pend")
    rejected = await _make_student(db_session, "rej")
    await _enroll(db_session, course, active, status="active")
    await _enroll(db_session, course, pending, status="pending")
    await _enroll(db_session, course, rejected, status="rejected")
    item = await _make_item(
        db_session, course, logged_in_user, close_at=_now() - timedelta(hours=1)
    )
    await db_session.commit()

    n = await mark_missed_work_items(db_session)
    assert n == 1
    assert await _status_of(db_session, item, active) == "missed"
    assert await _status_of(db_session, item, pending) is None
    assert await _status_of(db_session, item, rejected) is None


@pytest.mark.asyncio
async def test_idempotent_second_run_noops(
    db_session: AsyncSession, logged_in_user: User
):
    course = await _make_course(db_session, logged_in_user, "MISS008")
    student = await _make_student(db_session, "idem")
    await _enroll(db_session, course, student)
    item = await _make_item(
        db_session, course, logged_in_user, close_at=_now() - timedelta(hours=1)
    )
    await db_session.commit()

    first = await mark_missed_work_items(db_session)
    assert first == 1
    second = await mark_missed_work_items(db_session)
    assert second == 0
    assert await _status_of(db_session, item, student) == "missed"
