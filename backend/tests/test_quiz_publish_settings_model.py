"""Model/constraint tests for the P5 publish-settings columns on ``quizzes``
(P5 Task B1).

Decision 1: practice-vs-graded is a DEDICATED new ``assessment_purpose`` column
(CHECK ``practice|graded``, ``server_default='practice'`` so every existing quiz
backfills to practice) — NOT the existing ``purpose`` (``after_class|live``) or the
unconstrained legacy ``quiz_type``, both of which stay untouched.

This covers only the ORM columns, defaults, and the three new CHECKs
(``assessment_purpose``, ``grading_mode``, ``late_rule``) via
``Base.metadata.create_all`` in the disposable test DB (``db_session``).
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.course import Course
from app.models.quiz import Quiz
from app.models.score import ScoreCategory


@pytest_asyncio.fixture
async def seed_course(db_session, test_instructor):
    course = Course(
        name="LANG1511",
        language="zh",
        instructor_id=test_instructor.id,
        enroll_code="QPUB" + uuid.uuid4().hex[:4].upper(),
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


def _make_quiz(course, created_by, *, title="Unit 1 quiz", **kwargs):
    return Quiz(
        course_id=course.id,
        created_by=created_by,
        title=title,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_publish_settings_defaults(db_session, seed_course, test_instructor):
    """A bare quiz backfills assessment_purpose='practice', score_bearing=False,
    and leaves every optional publish-setting NULL. The existing purpose/quiz_type
    columns keep their own defaults (untouched by P5)."""
    quiz = _make_quiz(seed_course, test_instructor.id)
    db_session.add(quiz)
    await db_session.commit()
    await db_session.refresh(quiz)

    assert quiz.assessment_purpose == "practice"
    assert quiz.score_bearing is False
    assert quiz.score_category_id is None
    assert quiz.points is None
    assert quiz.grading_mode is None
    assert quiz.open_at is None
    assert quiz.due_at is None
    assert quiz.close_at is None
    assert quiz.late_rule is None

    # Existing columns are NOT disturbed (Decision 1).
    assert quiz.purpose == "after_class"
    assert quiz.quiz_type == "practice"


@pytest.mark.asyncio
async def test_full_publish_settings_roundtrip(
    db_session, seed_course, test_instructor
):
    category = ScoreCategory(course_id=seed_course.id, name="Quizzes", sort=0)
    db_session.add(category)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    quiz = _make_quiz(
        seed_course,
        test_instructor.id,
        assessment_purpose="graded",
        score_bearing=True,
        score_category_id=category.id,
        points=Decimal("10.00"),
        grading_mode="auto",
        open_at=now,
        due_at=now + timedelta(days=1),
        close_at=now + timedelta(days=2),
        late_rule="accept_with_flag",
    )
    db_session.add(quiz)
    await db_session.commit()
    await db_session.refresh(quiz)

    assert quiz.assessment_purpose == "graded"
    assert quiz.score_bearing is True
    assert quiz.score_category_id == category.id
    assert quiz.points == Decimal("10.00")
    assert quiz.grading_mode == "auto"
    assert quiz.open_at is not None
    assert quiz.due_at is not None
    assert quiz.close_at is not None
    assert quiz.late_rule == "accept_with_flag"


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["practice", "graded"])
async def test_assessment_purpose_enum_accepts(
    db_session, seed_course, test_instructor, value
):
    quiz = _make_quiz(seed_course, test_instructor.id, assessment_purpose=value)
    db_session.add(quiz)
    await db_session.commit()
    await db_session.refresh(quiz)
    assert quiz.assessment_purpose == value


@pytest.mark.asyncio
async def test_bad_assessment_purpose_rejected(
    db_session, seed_course, test_instructor
):
    quiz = _make_quiz(
        seed_course, test_instructor.id, assessment_purpose="nonsense"
    )
    db_session.add(quiz)
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["auto", "manual", "participation"])
async def test_grading_mode_enum_accepts(
    db_session, seed_course, test_instructor, value
):
    quiz = _make_quiz(seed_course, test_instructor.id, grading_mode=value)
    db_session.add(quiz)
    await db_session.commit()
    await db_session.refresh(quiz)
    assert quiz.grading_mode == value


@pytest.mark.asyncio
async def test_bad_grading_mode_rejected(
    db_session, seed_course, test_instructor
):
    quiz = _make_quiz(seed_course, test_instructor.id, grading_mode="bogus")
    db_session.add(quiz)
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value", ["accept_late", "reject_late", "accept_with_flag"]
)
async def test_late_rule_enum_accepts(
    db_session, seed_course, test_instructor, value
):
    quiz = _make_quiz(seed_course, test_instructor.id, late_rule=value)
    db_session.add(quiz)
    await db_session.commit()
    await db_session.refresh(quiz)
    assert quiz.late_rule == value


@pytest.mark.asyncio
async def test_bad_late_rule_rejected(db_session, seed_course, test_instructor):
    quiz = _make_quiz(seed_course, test_instructor.id, late_rule="whenever")
    db_session.add(quiz)
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_score_category_fk_nullable(
    db_session, seed_course, test_instructor
):
    """score_category_id is a real FK to score_categories.id and nullable."""
    quiz = _make_quiz(seed_course, test_instructor.id)
    db_session.add(quiz)
    await db_session.commit()
    await db_session.refresh(quiz)
    assert quiz.score_category_id is None
