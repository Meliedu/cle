"""Review Case reframe (CLE §5.4).

Two enhanced alert rules now route their finding to the instructor as a *draft*
``LearningNote`` and link it to the ``InstructorAlert`` via ``linked_note_id``.
The note stays ``review_status='draft'`` until an instructor promotes it —
AI drafts, the instructor decides.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import (
    Assignment,
    AssignmentSubmission,
    Concept,
    ConceptMastery,
    Course,
    Enrollment,
    InstructorAlert,
    LearningNote,
    User,
)
from app.services.alerts import evaluate_alerts_for_course


@pytest.mark.asyncio
async def test_cohort_weakness_drafts_linked_review_case(
    db_session, test_instructor: User
):
    course = Course(
        name="Review Weak Cohort",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="RC-WC",
    )
    db_session.add(course)
    await db_session.flush()
    concept = Concept(course_id=course.id, name="hard-concept", status="approved")
    db_session.add(concept)
    await db_session.flush()

    # 4 students, all weak (mastery 0.1) with confidence ≥ 0.5 → avg < 0.4.
    for i in range(4):
        u = User(
            email=f"rc-weak-{i}@connect.ust.hk",
            full_name=f"RCW{i}",
            role="student",
            better_auth_id=f"rc-weak-{i}",
        )
        db_session.add(u)
        await db_session.flush()
        db_session.add(
            Enrollment(course_id=course.id, user_id=u.id, role="student")
        )
        db_session.add(
            ConceptMastery(
                user_id=u.id,
                concept_id=concept.id,
                course_id=course.id,
                alpha=Decimal("1.000"),
                beta=Decimal("9.000"),
                confidence=Decimal("0.700"),
            )
        )
    await db_session.commit()

    await evaluate_alerts_for_course(db_session, course_id=course.id)

    alert = (
        await db_session.execute(
            select(InstructorAlert).where(
                InstructorAlert.alert_type == "cohort_concept_weakness",
                InstructorAlert.course_id == course.id,
            )
        )
    ).scalar_one()
    assert alert.linked_note_id is not None
    assert alert.target_user_id is None  # cohort alert

    note = (
        await db_session.execute(
            select(LearningNote).where(LearningNote.id == alert.linked_note_id)
        )
    ).scalar_one()
    assert note.review_status == "draft"
    assert note.report_eligibility is False
    assert note.course_id == course.id


@pytest.mark.asyncio
async def test_falling_behind_drafts_linked_review_case(
    db_session, test_instructor: User
):
    course = Course(
        name="Review Falling Behind",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="RC-FB",
    )
    db_session.add(course)
    await db_session.flush()
    student = User(
        email="rc-fb-1@connect.ust.hk",
        full_name="RC Fallen",
        role="student",
        better_auth_id="rc-fb-1",
    )
    db_session.add(student)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=student.id, role="student")
    )

    now = datetime.now(timezone.utc)
    # Two recent (within 14d by due_at) late submissions.
    for i in range(2):
        a = Assignment(
            course_id=course.id,
            title=f"RC past due {i}",
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

    await evaluate_alerts_for_course(db_session, course_id=course.id)

    alert = (
        await db_session.execute(
            select(InstructorAlert).where(
                InstructorAlert.alert_type == "student_falling_behind",
                InstructorAlert.course_id == course.id,
                InstructorAlert.target_user_id == student.id,
            )
        )
    ).scalar_one()
    assert alert.linked_note_id is not None

    note = (
        await db_session.execute(
            select(LearningNote).where(LearningNote.id == alert.linked_note_id)
        )
    ).scalar_one()
    assert note.review_status == "draft"
    assert note.user_id == student.id
