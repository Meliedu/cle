import pytest

from app.models.course import Course


@pytest.mark.asyncio
async def test_new_course_defaults_setup_columns(db_session, test_instructor):
    course = Course(
        name="LANG1511", language="zh", instructor_id=test_instructor.id,
        enroll_code="ABCD2345",
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    assert course.setup_status == "draft"
    assert course.setup_checklist == {}
    assert course.join_mode == "code"
    assert course.enroll_code_active is True
    # existing gate column untouched
    assert course.context_status == "draft"


@pytest.mark.asyncio
async def test_setup_status_check_constraint(db_session, test_instructor):
    from sqlalchemy.exc import IntegrityError
    course = Course(
        name="bad", language="zh", instructor_id=test_instructor.id,
        enroll_code="EFGH2345", setup_status="nonsense",
    )
    db_session.add(course)
    with pytest.raises(IntegrityError):
        await db_session.commit()
