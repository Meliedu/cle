import pytest

from app.models import Course, InstructorAlert, User


@pytest.mark.asyncio
async def test_instructor_alert_open_dedupe(db_session, test_instructor: User, test_student: User):
    course = Course(
        name="Alert Course",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="DECI-ALR",
    )
    db_session.add(course)
    await db_session.flush()

    db_session.add(
        InstructorAlert(
            course_id=course.id,
            instructor_id=test_instructor.id,
            target_user_id=test_student.id,
            alert_type="student_falling_behind",
            severity="warning",
            title="Lo Yan Wai is 3 deadlines behind",
            reason={"missed": 3},
        )
    )
    await db_session.commit()

    # Second open alert for same (course, type, target) is forbidden by the
    # partial unique index.
    db_session.add(
        InstructorAlert(
            course_id=course.id,
            instructor_id=test_instructor.id,
            target_user_id=test_student.id,
            alert_type="student_falling_behind",
            severity="warning",
            title="dup",
            reason={"missed": 4},
        )
    )
    with pytest.raises(Exception):
        await db_session.commit()
    await db_session.rollback()
