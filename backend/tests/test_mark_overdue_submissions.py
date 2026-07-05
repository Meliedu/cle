from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Assignment, AssignmentSubmission, Course, User,
)
from app.services.worker import mark_overdue_submissions


@pytest.mark.asyncio
async def test_marks_past_due_not_started_as_late(
    db_session: AsyncSession, test_instructor: User, test_student: User,
):
    course = Course(
        name="T", language="english",
        instructor_id=test_instructor.id, enroll_code="MOSCRSE1",
    )
    db_session.add(course)
    await db_session.flush()
    a = Assignment(
        course_id=course.id, title="Old", kind="essay",
        due_at=datetime.now(timezone.utc) - timedelta(days=2),
        is_published=True, created_by=test_instructor.id,
    )
    db_session.add(a)
    await db_session.flush()
    sub = AssignmentSubmission(
        assignment_id=a.id, user_id=test_student.id, status="not_started",
    )
    db_session.add(sub)
    await db_session.commit()

    await mark_overdue_submissions(db_session)

    refreshed = (await db_session.execute(
        select(AssignmentSubmission).where(AssignmentSubmission.id == sub.id)
    )).scalar_one()
    assert refreshed.status == "late"


@pytest.mark.asyncio
async def test_does_not_touch_submitted_or_graded(
    db_session: AsyncSession, test_instructor: User, test_student: User,
):
    course = Course(
        name="T", language="english",
        instructor_id=test_instructor.id, enroll_code="MOSCRSE2",
    )
    db_session.add(course)
    await db_session.flush()
    a = Assignment(
        course_id=course.id, title="Old", kind="essay",
        due_at=datetime.now(timezone.utc) - timedelta(days=2),
        is_published=True, created_by=test_instructor.id,
    )
    db_session.add(a)
    await db_session.flush()
    sub_submitted = AssignmentSubmission(
        assignment_id=a.id, user_id=test_student.id,
        status="submitted",
        submitted_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(sub_submitted)
    await db_session.commit()

    await mark_overdue_submissions(db_session)

    refreshed = (await db_session.execute(
        select(AssignmentSubmission).where(AssignmentSubmission.id == sub_submitted.id)
    )).scalar_one()
    assert refreshed.status == "submitted"
