import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import (
    Assignment,
    AssignmentSubmission,
    Concept,
    ConceptMastery,
    ConceptPrerequisite,
    ConceptTag,
    Course,
    CourseMeeting,
    Enrollment,
    InstructorAlert,
    Quiz,
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


@pytest.mark.asyncio
async def test_student_disengaging_alert(
    db_session, test_instructor: User
):
    """Student with recent=0, prior>0 → per-student disengaging alert."""
    course = Course(
        name="Disengaging",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ALR-DG",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()

    student = User(
        email="dg-1@connect.ust.hk",
        full_name="Disengaging",
        role="student",
        better_auth_id="dg-1",
    )
    db_session.add(student)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=student.id, role="student")
    )

    quiz = Quiz(
        course_id=course.id,
        created_by=test_instructor.id,
        title="Disengage Quiz",
        is_published=True,
    )
    db_session.add(quiz)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    # Two prior attempts (between 7d and 14d ago), zero recent attempts.
    for i in range(2):
        attempt = QuizAttempt(
            quiz_id=quiz.id,
            user_id=student.id,
            answers={},
            created_at=now - timedelta(days=10 + i),
        )
        db_session.add(attempt)
    await db_session.commit()

    await evaluate_alerts_for_course(db_session, course_id=course.id)

    rows = (await db_session.execute(
        __import__("sqlalchemy").select(InstructorAlert).where(
            InstructorAlert.alert_type == "student_disengaging",
            InstructorAlert.course_id == course.id,
            InstructorAlert.target_user_id == student.id,
        )
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].reason["recent"] == 0
    assert rows[0].reason["prior"] == 2


@pytest.mark.asyncio
async def test_low_quiz_participation_alert(
    db_session, test_instructor: User
):
    """Published quiz >7d old, only 1 of 4 enrolled (25%) attempted → cohort alert."""
    course = Course(
        name="Low participation",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ALR-LP",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()

    students = []
    for i in range(4):
        u = User(
            email=f"lp-{i}@connect.ust.hk",
            full_name=f"L{i}",
            role="student",
            better_auth_id=f"lp-{i}",
        )
        db_session.add(u)
        await db_session.flush()
        db_session.add(
            Enrollment(course_id=course.id, user_id=u.id, role="student")
        )
        students.append(u)

    now = datetime.now(timezone.utc)
    quiz = Quiz(
        course_id=course.id,
        created_by=test_instructor.id,
        title="Old Quiz",
        is_published=True,
        created_at=now - timedelta(days=10),
    )
    db_session.add(quiz)
    await db_session.flush()

    # Only 1 of 4 (25%) attempted — below 30% threshold.
    db_session.add(
        QuizAttempt(
            quiz_id=quiz.id,
            user_id=students[0].id,
            answers={},
        )
    )
    await db_session.commit()

    await evaluate_alerts_for_course(db_session, course_id=course.id)

    rows = (await db_session.execute(
        __import__("sqlalchemy").select(InstructorAlert).where(
            InstructorAlert.alert_type == "low_quiz_participation",
            InstructorAlert.course_id == course.id,
        )
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].target_user_id is None  # cohort alert
    assert rows[0].reason["attempters"] == 1
    assert rows[0].reason["enrolled"] == 4


@pytest.mark.asyncio
async def test_prereq_gap_for_upcoming_meeting_alert(
    db_session, test_instructor: User
):
    """Meeting in 48h, prereq weak for 4 of 5 (80%) → cohort alert."""
    course = Course(
        name="Prereq gap",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ALR-PG",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()

    students = []
    for i in range(5):
        u = User(
            email=f"pg-{i}@connect.ust.hk",
            full_name=f"P{i}",
            role="student",
            better_auth_id=f"pg-{i}",
        )
        db_session.add(u)
        await db_session.flush()
        db_session.add(
            Enrollment(course_id=course.id, user_id=u.id, role="student")
        )
        students.append(u)

    # Two concepts: prereq → dependent (covered by upcoming meeting).
    prereq = Concept(course_id=course.id, name="prereq-c", status="approved")
    dependent = Concept(course_id=course.id, name="dependent-c", status="approved")
    db_session.add_all([prereq, dependent])
    await db_session.flush()
    db_session.add(
        ConceptPrerequisite(
            prereq_concept_id=prereq.id,
            dependent_concept_id=dependent.id,
            strength=Decimal("0.80"),
        )
    )

    now = datetime.now(timezone.utc)
    meeting = CourseMeeting(
        course_id=course.id,
        meeting_index=1,
        title="Upcoming",
        scheduled_at=now + timedelta(hours=48),
    )
    db_session.add(meeting)
    await db_session.flush()

    # Tag dependent concept onto the meeting.
    db_session.add(
        ConceptTag(
            concept_id=dependent.id,
            target_kind="meeting",
            target_id=meeting.id,
            weight=Decimal("1.00"),
        )
    )

    # 4 of 5 students weak on the prereq (mastery_score < 0.7 via low alpha/high beta).
    for i in range(4):
        db_session.add(
            ConceptMastery(
                user_id=students[i].id,
                concept_id=prereq.id,
                course_id=course.id,
                alpha=Decimal("1.000"),
                beta=Decimal("9.000"),
                confidence=Decimal("0.500"),
            )
        )
    await db_session.commit()

    await evaluate_alerts_for_course(db_session, course_id=course.id)

    rows = (await db_session.execute(
        __import__("sqlalchemy").select(InstructorAlert).where(
            InstructorAlert.alert_type == "prereq_gap_for_upcoming_meeting",
            InstructorAlert.course_id == course.id,
        )
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].target_user_id is None  # cohort alert
    assert rows[0].reason["weak_n"] == 4
    assert rows[0].reason["enrolled"] == 5
