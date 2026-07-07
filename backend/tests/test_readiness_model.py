import pytest
from sqlalchemy.exc import IntegrityError

from app.models.course import Course
from app.models.readiness import ReadinessResponse


async def _course(db_session, instructor):
    c = Course(name="LANG1511", language="zh", instructor_id=instructor.id, enroll_code="ABCD2345")
    db_session.add(c)
    await db_session.flush()
    return c


@pytest.mark.asyncio
async def test_readiness_defaults(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)
    r = ReadinessResponse(
        user_id=test_student.id, course_id=c.id, phase="eligibility_survey",
        answers={"prior_study": "1-3 years"},
    )
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)
    assert r.status == "in_progress"
    assert r.result == {}


@pytest.mark.asyncio
async def test_readiness_phase_check(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)
    r = ReadinessResponse(user_id=test_student.id, course_id=c.id, phase="bogus", answers={})
    db_session.add(r)
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_readiness_status_check(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)
    r = ReadinessResponse(
        user_id=test_student.id, course_id=c.id, phase="ready_check",
        answers={}, status="nonsense",
    )
    db_session.add(r)
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_readiness_phase_forward_compat_values(db_session, test_instructor, test_student):
    """All four spec §4.7 phases are accepted even though CLE ships only two
    question sets today (Decision 4 forward-compat)."""
    c = await _course(db_session, test_instructor)
    for phase in ("eligibility_survey", "ready_check", "diagnostic", "recommendation"):
        r = ReadinessResponse(user_id=test_student.id, course_id=c.id, phase=phase, answers={})
        db_session.add(r)
    await db_session.commit()


@pytest.mark.asyncio
async def test_readiness_one_row_per_user_course_phase(db_session, test_instructor, test_student):
    c = await _course(db_session, test_instructor)
    db_session.add(ReadinessResponse(user_id=test_student.id, course_id=c.id, phase="ready_check", answers={}))
    await db_session.flush()
    db_session.add(ReadinessResponse(user_id=test_student.id, course_id=c.id, phase="ready_check", answers={}))
    with pytest.raises(IntegrityError):
        await db_session.commit()
