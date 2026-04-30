import uuid
import pytest

from app.models import Course, EngineOverride, User
from app.services.engine_mode import resolve_engine_mode


@pytest.mark.asyncio
async def test_override_wins_over_course_flag(db_session, test_instructor: User, test_student: User):
    course = Course(
        name="Override wins",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ENG-OVR1",
        adaptive_engine_mode="on",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        EngineOverride(
            user_id=test_student.id,
            course_id=course.id,
            mode="off",
            set_by=test_instructor.id,
        )
    )
    await db_session.commit()

    mode = await resolve_engine_mode(db_session, user_id=test_student.id, course_id=course.id)
    assert mode == "off"


@pytest.mark.asyncio
async def test_no_override_falls_through_to_course(db_session, test_instructor: User, test_student: User):
    course = Course(
        name="Course flag",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ENG-OVR2",
        adaptive_engine_mode="off",
    )
    db_session.add(course)
    await db_session.commit()

    mode = await resolve_engine_mode(db_session, user_id=test_student.id, course_id=course.id)
    assert mode == "off"


@pytest.mark.asyncio
async def test_random_50_is_deterministic(db_session, test_instructor: User, test_student: User):
    course = Course(
        name="Random 50",
        language="en",
        instructor_id=test_instructor.id,
        enroll_code="ENG-RAND",
        adaptive_engine_mode="random_50",
    )
    db_session.add(course)
    await db_session.commit()

    a = await resolve_engine_mode(db_session, user_id=test_student.id, course_id=course.id)
    b = await resolve_engine_mode(db_session, user_id=test_student.id, course_id=course.id)
    assert a == b
    assert a in ("on", "off")


def test_random_50_distribution_is_balanced():
    # Pure unit test — the splitter alone, no DB.
    from app.services.engine_mode import _coin_flip_random_50

    course_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    flips = [_coin_flip_random_50(uuid.uuid4(), course_id) for _ in range(2000)]
    on_count = sum(1 for f in flips if f == "on")
    # Allow ±5% slack — 2000 flips of a fair coin is well inside binomial.
    assert 900 <= on_count <= 1100
