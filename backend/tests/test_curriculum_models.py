import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Course,
    CourseModule,
    CourseMeeting,
    LearningObjective,
    Assignment,
    AssignmentSubmission,
    SyllabusImport,
    User,
)


@pytest.mark.asyncio
async def test_course_module_persists(db_session: AsyncSession, test_instructor: User):
    course = Course(
        name="Test", language="english",
        instructor_id=test_instructor.id, enroll_code="TESTABCD",
    )
    db_session.add(course)
    await db_session.flush()

    module = CourseModule(course_id=course.id, name="Week 1", order_index=1)
    db_session.add(module)
    await db_session.commit()
    await db_session.refresh(module)

    assert module.id is not None
    assert module.deleted_at is None
    assert module.created_at is not None


@pytest.mark.asyncio
async def test_course_meeting_persists(db_session: AsyncSession, test_instructor: User):
    course = Course(
        name="Test", language="english",
        instructor_id=test_instructor.id, enroll_code="TESTABCE",
    )
    db_session.add(course)
    await db_session.flush()

    meeting = CourseMeeting(
        course_id=course.id, meeting_index=1,
        title="Intro", scheduled_at=datetime.now(timezone.utc),
    )
    db_session.add(meeting)
    await db_session.commit()
    await db_session.refresh(meeting)

    assert meeting.status == "planned"
    assert meeting.duration_minutes == 60


@pytest.mark.asyncio
async def test_assignment_with_submission(
    db_session: AsyncSession, test_instructor: User, test_student: User,
):
    course = Course(
        name="Test", language="english",
        instructor_id=test_instructor.id, enroll_code="TESTABCF",
    )
    db_session.add(course)
    await db_session.flush()

    assignment = Assignment(
        course_id=course.id, title="Essay 1", kind="essay",
        due_at=datetime.now(timezone.utc) + timedelta(days=7),
        weight=Decimal("15.00"),
        created_by=test_instructor.id,
    )
    db_session.add(assignment)
    await db_session.flush()

    submission = AssignmentSubmission(
        assignment_id=assignment.id, user_id=test_student.id,
        status="not_started",
    )
    db_session.add(submission)
    await db_session.commit()
    await db_session.refresh(submission)

    assert submission.id is not None
    assert submission.score is None
