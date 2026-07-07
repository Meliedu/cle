"""Model/constraint tests for ``work_item_progress`` (P4 Task B2).

``work_item_progress`` is the student-owned per-item state row table (Decision
2). Its RLS owner-isolation policy is proven separately under ``meli_app`` in
B10; here we cover only the ORM columns, defaults and CHECK/UNIQUE constraints
via ``Base.metadata.create_all`` in the disposable test DB (``db_session``).

Owner = ``user_id``. One progress row per ``(work_item_id, user_id)`` — a state
transition upserts in place. ``status`` ships the full spec §4.6 lifecycle
(``pending|in_progress|submitted|late|missed|completed|follow_up_assigned``).
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError

from app.models.course import Course
from app.models.work_item import WorkItem, WorkItemProgress


@pytest_asyncio.fixture
async def seed_work_item(db_session, test_instructor):
    course = Course(
        name="LANG1512",
        language="zh",
        instructor_id=test_instructor.id,
        enroll_code="WIPR" + uuid.uuid4().hex[:4].upper(),
    )
    db_session.add(course)
    await db_session.flush()
    item = WorkItem(
        course_id=course.id,
        source_kind="checkpoint",
        source_id=uuid.uuid4(),
        title="Session 1 checkpoint",
        created_by=test_instructor.id,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


@pytest.mark.asyncio
async def test_progress_create_and_defaults(db_session, seed_work_item, test_student):
    item = seed_work_item
    p = WorkItemProgress(
        work_item_id=item.id,
        user_id=test_student.id,
        status="pending",
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    assert p.id is not None
    assert isinstance(p.id, uuid.UUID)
    assert p.status == "pending"
    assert p.created_at is not None
    assert p.updated_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        "pending",
        "in_progress",
        "submitted",
        "late",
        "missed",
        "completed",
        "follow_up_assigned",
    ],
)
async def test_progress_status_accepts_full_lifecycle(
    db_session, seed_work_item, test_student, status
):
    item = seed_work_item
    p = WorkItemProgress(
        work_item_id=item.id,
        user_id=test_student.id,
        status=status,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    assert p.status == status


@pytest.mark.asyncio
async def test_progress_bad_status_rejected(db_session, seed_work_item, test_student):
    item = seed_work_item
    db_session.add(
        WorkItemProgress(
            work_item_id=item.id,
            user_id=test_student.id,
            status="nonsense",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_progress_unique_work_item_user(
    db_session, seed_work_item, test_student
):
    item = seed_work_item
    db_session.add(
        WorkItemProgress(
            work_item_id=item.id,
            user_id=test_student.id,
            status="pending",
        )
    )
    await db_session.flush()
    db_session.add(
        WorkItemProgress(
            work_item_id=item.id,
            user_id=test_student.id,
            status="in_progress",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
