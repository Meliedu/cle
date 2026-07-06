import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.course import Course
from app.models.score import ScoreCategory
from app.pilot import get_pilot_profile
from app.services.setup import (
    SETUP_STEP_KEYS,
    SetupGateError,
    assert_course_open,
    missing_steps,
    publish_setup,
    reopen_setup,
    set_step_flag,
)


@pytest_asyncio.fixture
async def seed_course(db_session, test_instructor):
    course = Course(
        name="LANG1511",
        language="zh",
        instructor_id=test_instructor.id,
        enroll_code="SETP" + uuid.uuid4().hex[:4].upper(),
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


@pytest.mark.asyncio
async def test_publish_blocked_until_all_steps_complete(db_session, seed_course):
    with pytest.raises(SetupGateError) as exc:
        await publish_setup(db_session, seed_course)
    assert exc.value.code == "SETUP_INCOMPLETE"
    # context gate untouched by a failed publish
    await db_session.refresh(seed_course)
    assert seed_course.context_status == "draft"
    assert seed_course.setup_status == "draft"


@pytest.mark.asyncio
async def test_publish_flips_both_gates(db_session, seed_course):
    for key in SETUP_STEP_KEYS:
        await set_step_flag(db_session, seed_course, key, True)
    await publish_setup(db_session, seed_course)
    await db_session.refresh(seed_course)
    assert seed_course.setup_status == "published"
    assert seed_course.context_status == "approved"  # Decision 1
    assert seed_course.context_approved_at is not None


@pytest.mark.asyncio
async def test_reopen_keeps_students_in(db_session, seed_course):
    for key in SETUP_STEP_KEYS:
        await set_step_flag(db_session, seed_course, key, True)
    await publish_setup(db_session, seed_course)
    await reopen_setup(db_session, seed_course)
    await db_session.refresh(seed_course)
    assert seed_course.setup_status == "in_review"
    assert seed_course.context_status == "approved"  # §4.8: stays open


@pytest.mark.asyncio
async def test_set_step_flag_rejects_unknown_key(db_session, seed_course):
    with pytest.raises(SetupGateError) as exc:
        await set_step_flag(db_session, seed_course, "not_a_step", True)
    assert exc.value.code == "UNKNOWN_STEP"


@pytest.mark.asyncio
async def test_set_step_flag_moves_draft_to_in_review(db_session, seed_course):
    assert seed_course.setup_status == "draft"
    await set_step_flag(db_session, seed_course, SETUP_STEP_KEYS[0], True)
    await db_session.refresh(seed_course)
    assert seed_course.setup_status == "in_review"


@pytest.mark.asyncio
async def test_missing_steps_lists_all_when_empty(seed_course):
    assert missing_steps(seed_course) == list(SETUP_STEP_KEYS)


@pytest.mark.asyncio
async def test_assert_course_open_gate(db_session, seed_course):
    # draft course is not open
    with pytest.raises(SetupGateError) as exc:
        assert_course_open(seed_course)
    assert exc.value.code == "SETUP_NOT_OPEN"

    # publish flips context_status -> approved, gate now passes
    for key in SETUP_STEP_KEYS:
        await set_step_flag(db_session, seed_course, key, True)
    await publish_setup(db_session, seed_course)
    await db_session.refresh(seed_course)
    assert assert_course_open(seed_course) is None  # does not raise


@pytest.mark.asyncio
async def test_reopen_then_gate_still_open(db_session, seed_course):
    for key in SETUP_STEP_KEYS:
        await set_step_flag(db_session, seed_course, key, True)
    await publish_setup(db_session, seed_course)
    await reopen_setup(db_session, seed_course)
    await db_session.refresh(seed_course)
    # reopening must NOT lock enrolled students out
    assert assert_course_open(seed_course) is None


@pytest.mark.asyncio
async def test_create_course_seeds_pilot_score_categories(async_client, db_session):
    resp = await async_client.post(
        "/api/courses",
        json={"name": "LANG1512", "language": "zh"},
    )
    assert resp.status_code == 201
    course_id = uuid.UUID(resp.json()["data"]["id"])

    rows = (
        await db_session.execute(
            select(ScoreCategory)
            .where(ScoreCategory.course_id == course_id)
            .order_by(ScoreCategory.sort)
        )
    ).scalars().all()

    defaults = get_pilot_profile().score_category_defaults
    assert len(rows) == len(defaults)
    assert [r.name for r in rows] == [d.name for d in defaults]
    # CLE pilot ships exactly Participation + Quizzes
    assert [r.name for r in rows] == ["Participation", "Quizzes"]
