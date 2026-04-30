import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import (
    Assignment,
    AssignmentSubmission,
    Concept,
    ConceptMastery,
    ConceptTag,
    Course,
    CourseMeeting,
    Enrollment,
    InstructorAlert,
    QuizAttempt,
    User,
)
from app.services.alerts import evaluate_alerts_for_course


@pytest.mark.asyncio
async def test_no_data_no_alerts(db_session, test_instructor: User):
    course = Course(
        name="Empty",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ALR-EMP",
    )
    db_session.add(course)
    await db_session.commit()
    result = await evaluate_alerts_for_course(db_session, course_id=course.id)
    assert result["alerts_created"] == 0


@pytest.mark.asyncio
async def test_cohort_concept_weakness_alert(
    db_session, test_instructor: User
):
    course = Course(
        name="Weak Cohort",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ALR-WC",
    )
    db_session.add(course)
    await db_session.flush()
    c = Concept(course_id=course.id, name="hard", status="approved")
    db_session.add(c)
    await db_session.flush()
    # 4 students, all weak with confidence
    for i in range(4):
        u = User(email=f"weak-{i}@connect.ust.hk", full_name=f"S{i}", role="student", better_auth_id=f"weak-{i}")
        db_session.add(u)
        await db_session.flush()
        db_session.add(Enrollment(course_id=course.id, user_id=u.id, role="student"))
        db_session.add(
            ConceptMastery(
                user_id=u.id, concept_id=c.id, course_id=course.id,
                alpha=Decimal("1.000"), beta=Decimal("9.000"),
                confidence=Decimal("0.700"),
            )
        )
    await db_session.commit()

    result = await evaluate_alerts_for_course(db_session, course_id=course.id)
    assert result["alerts_created"] >= 1
    rows = (await db_session.execute(
        __import__("sqlalchemy").select(InstructorAlert).where(
            InstructorAlert.alert_type == "cohort_concept_weakness",
            InstructorAlert.course_id == course.id,
        )
    )).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_dedupe_on_open_alert(
    db_session, test_instructor: User
):
    """Re-running the evaluator must not create a second open row for the
    same (course, type, target)."""
    course = Course(
        name="Dedupe",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ALR-DD",
    )
    db_session.add(course)
    await db_session.flush()
    c = Concept(course_id=course.id, name="dup", status="approved")
    db_session.add(c)
    await db_session.flush()
    for i in range(4):
        u = User(email=f"dd-{i}@connect.ust.hk", full_name=f"D{i}", role="student", better_auth_id=f"dd-{i}")
        db_session.add(u)
        await db_session.flush()
        db_session.add(Enrollment(course_id=course.id, user_id=u.id, role="student"))
        db_session.add(
            ConceptMastery(
                user_id=u.id, concept_id=c.id, course_id=course.id,
                alpha=Decimal("1.000"), beta=Decimal("9.000"),
                confidence=Decimal("0.700"),
            )
        )
    await db_session.commit()

    await evaluate_alerts_for_course(db_session, course_id=course.id)
    await evaluate_alerts_for_course(db_session, course_id=course.id)

    rows = (await db_session.execute(
        __import__("sqlalchemy").select(InstructorAlert).where(
            InstructorAlert.alert_type == "cohort_concept_weakness",
            InstructorAlert.course_id == course.id,
            InstructorAlert.status == "open",
        )
    )).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_content_gap_alert(db_session, test_instructor: User):
    course = Course(
        name="Gap",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ALR-GAP",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(Concept(course_id=course.id, name="orphan", status="approved"))
    await db_session.commit()
    result = await evaluate_alerts_for_course(db_session, course_id=course.id)
    rows = (await db_session.execute(
        __import__("sqlalchemy").select(InstructorAlert).where(
            InstructorAlert.alert_type == "content_gap",
            InstructorAlert.course_id == course.id,
        )
    )).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_student_falling_behind_alert(
    db_session, test_instructor: User
):
    """Student with 2+ late submissions in last 14d (by Assignment.due_at) → alert."""
    from datetime import datetime, timedelta, timezone

    course = Course(
        name="Falling behind",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ALR-FB",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    student = User(
        email="fb-1@connect.ust.hk",
        full_name="Fallen",
        role="student",
        better_auth_id="fb-1",
    )
    db_session.add(student)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=student.id, role="student")
    )
    now = datetime.now(timezone.utc)
    # Two recent (within 14d) late assignments due_at-wise.
    for i in range(2):
        a = Assignment(
            course_id=course.id,
            title=f"Past due {i}",
            kind="quiz",
            due_at=now - timedelta(days=3),
            created_by=test_instructor.id,
            is_published=True,
        )
        db_session.add(a)
        await db_session.flush()
        db_session.add(
            AssignmentSubmission(
                assignment_id=a.id,
                user_id=student.id,
                status="late",
            )
        )
    await db_session.commit()

    result = await evaluate_alerts_for_course(db_session, course_id=course.id)
    rows = (await db_session.execute(
        __import__("sqlalchemy").select(InstructorAlert).where(
            InstructorAlert.alert_type == "student_falling_behind",
            InstructorAlert.course_id == course.id,
            InstructorAlert.target_user_id == student.id,
        )
    )).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_missed_deadline_cohort_alert(
    db_session, test_instructor: User
):
    """Assignment >24h overdue with <80% submitted → cohort alert."""
    from datetime import datetime, timedelta, timezone

    course = Course(
        name="Missed deadline",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ALR-MD",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    students = []
    for i in range(5):
        u = User(
            email=f"md-{i}@connect.ust.hk",
            full_name=f"M{i}",
            role="student",
            better_auth_id=f"md-{i}",
        )
        db_session.add(u)
        await db_session.flush()
        db_session.add(
            Enrollment(course_id=course.id, user_id=u.id, role="student")
        )
        students.append(u)
    a = Assignment(
        course_id=course.id,
        title="Way overdue",
        kind="quiz",
        due_at=datetime.now(timezone.utc) - timedelta(days=2),
        created_by=test_instructor.id,
        is_published=True,
    )
    db_session.add(a)
    await db_session.flush()
    # Only 1 of 5 (20%) submitted — 80% threshold breached.
    db_session.add(
        AssignmentSubmission(
            assignment_id=a.id,
            user_id=students[0].id,
            status="submitted",
        )
    )
    await db_session.commit()

    result = await evaluate_alerts_for_course(db_session, course_id=course.id)
    rows = (await db_session.execute(
        __import__("sqlalchemy").select(InstructorAlert).where(
            InstructorAlert.alert_type == "missed_deadline",
            InstructorAlert.course_id == course.id,
        )
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].target_user_id is None  # cohort alert
