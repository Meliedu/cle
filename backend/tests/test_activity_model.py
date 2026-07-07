"""Model/constraint tests for ``activities`` + ``activity_responses`` (P5 Task B3).

``activities`` is the course-scoped, teacher-authored activity table (spec §4.4).
It is operational — mirrors ``Checkpoint``/``WorkItem``: **NO RLS** (every read is
enrollment- or owner-guarded at the endpoint layer). Per-student submissions live
in the separate owner-owned ``activity_responses`` table.

This covers only the ORM columns, defaults and CHECK/UNIQUE constraints via
``Base.metadata.create_all`` in the disposable test DB (``db_session``). The RLS
owner-isolation policy on ``activity_responses`` is proven separately under
``meli_app`` in B12; here we only assert the *migration* declares it (Decision 3).
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.activity import Activity, ActivityResponse
from app.models.course import Course

ACTIVITY_FORMATS = ["swipe", "vote", "comment_reaction"]
ACTIVITY_STATUSES = ["draft", "published", "live", "closed", "archived"]
GRADING_MODES = ["auto", "manual", "participation"]
LATE_RULES = ["accept_late", "reject_late", "accept_with_flag"]

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "c7d2f4b9e6a1_activities_activity_responses_tables_rls.py"
)


@pytest_asyncio.fixture
async def seed_course(db_session, test_instructor):
    course = Course(
        name="LANG1520",
        language="zh",
        instructor_id=test_instructor.id,
        enroll_code="ACTV" + uuid.uuid4().hex[:4].upper(),
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


def _make_activity(
    course,
    *,
    format="swipe",
    title="Warm-up swipe",
    status=None,
    config=None,
    anonymous=None,
    open_at=None,
    due_at=None,
    close_at=None,
    score_category_id=None,
    points=None,
    grading_mode=None,
    late_rule=None,
    score_bearing=None,
    meeting_id=None,
):
    kwargs = dict(
        course_id=course.id,
        format=format,
        title=title,
        config=config,
        open_at=open_at,
        due_at=due_at,
        close_at=close_at,
        score_category_id=score_category_id,
        points=points,
        grading_mode=grading_mode,
        late_rule=late_rule,
        meeting_id=meeting_id,
    )
    if status is not None:
        kwargs["status"] = status
    if anonymous is not None:
        kwargs["anonymous"] = anonymous
    if score_bearing is not None:
        kwargs["score_bearing"] = score_bearing
    return Activity(**kwargs)


# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_activity_create_and_defaults(db_session, seed_course):
    now = datetime.now(timezone.utc)
    activity = _make_activity(
        seed_course,
        config={"prompts": ["Agree?", "Disagree?"]},
        open_at=now,
        due_at=now + timedelta(hours=1),
        close_at=now + timedelta(hours=2),
    )
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)

    assert activity.id is not None
    assert isinstance(activity.id, uuid.UUID)
    assert activity.course_id == seed_course.id
    assert activity.meeting_id is None
    assert activity.format == "swipe"
    assert activity.title == "Warm-up swipe"
    assert activity.config == {"prompts": ["Agree?", "Disagree?"]}
    # Defaults: status=draft, anonymous=False, score_bearing=False.
    assert activity.status == "draft"
    assert activity.anonymous is False
    assert activity.score_bearing is False
    # Publish-settings default to NULL (§4.5).
    assert activity.score_category_id is None
    assert activity.points is None
    assert activity.grading_mode is None
    assert activity.late_rule is None
    assert activity.open_at is not None
    assert activity.due_at is not None
    assert activity.close_at is not None
    # TimestampMixin + SoftDeleteMixin.
    assert activity.created_at is not None
    assert activity.updated_at is not None
    assert activity.deleted_at is None


@pytest.mark.asyncio
async def test_activity_nullable_time_columns(db_session, seed_course):
    activity = _make_activity(seed_course)
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)
    assert activity.open_at is None
    assert activity.due_at is None
    assert activity.close_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("format", ACTIVITY_FORMATS)
async def test_activity_format_accepts_valid(db_session, seed_course, format):
    activity = _make_activity(seed_course, format=format)
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)
    assert activity.format == format


@pytest.mark.asyncio
async def test_activity_bad_format_rejected(db_session, seed_course):
    db_session.add(_make_activity(seed_course, format="poll"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ACTIVITY_STATUSES)
async def test_activity_status_accepts_full_machine(db_session, seed_course, status):
    activity = _make_activity(seed_course, status=status)
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)
    assert activity.status == status


@pytest.mark.asyncio
async def test_activity_bad_status_rejected(db_session, seed_course):
    db_session.add(_make_activity(seed_course, status="nonsense"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("grading_mode", GRADING_MODES)
async def test_activity_grading_mode_accepts_valid(
    db_session, seed_course, grading_mode
):
    activity = _make_activity(seed_course, grading_mode=grading_mode)
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)
    assert activity.grading_mode == grading_mode


@pytest.mark.asyncio
async def test_activity_bad_grading_mode_rejected(db_session, seed_course):
    db_session.add(_make_activity(seed_course, grading_mode="curve"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("late_rule", LATE_RULES)
async def test_activity_late_rule_accepts_valid(db_session, seed_course, late_rule):
    activity = _make_activity(seed_course, late_rule=late_rule)
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)
    assert activity.late_rule == late_rule


@pytest.mark.asyncio
async def test_activity_bad_late_rule_rejected(db_session, seed_course):
    db_session.add(_make_activity(seed_course, late_rule="whenever"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_activity_score_bearing_publish_settings(db_session, seed_course):
    """A score-bearing activity carries the §4.5 publish-settings columns."""
    from app.models.score import ScoreCategory

    cat = ScoreCategory(course_id=seed_course.id, name="Participation", sort=0)
    db_session.add(cat)
    await db_session.flush()

    activity = _make_activity(
        seed_course,
        format="vote",
        score_bearing=True,
        anonymous=True,
        score_category_id=cat.id,
        points=Decimal("10.00"),
        grading_mode="participation",
        late_rule="accept_with_flag",
    )
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)
    assert activity.score_bearing is True
    assert activity.anonymous is True
    assert activity.score_category_id == cat.id
    assert activity.points == Decimal("10.00")
    assert activity.grading_mode == "participation"
    assert activity.late_rule == "accept_with_flag"


@pytest.mark.asyncio
async def test_activity_soft_delete_column(db_session, seed_course):
    activity = _make_activity(seed_course)
    db_session.add(activity)
    await db_session.commit()
    activity.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()
    await db_session.refresh(activity)
    assert activity.deleted_at is not None


# ---------------------------------------------------------------------------
# ActivityResponse
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def seed_activity(db_session, seed_course):
    activity = _make_activity(seed_course, format="comment_reaction", status="live")
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)
    return activity


@pytest.mark.asyncio
async def test_activity_response_create_and_defaults(
    db_session, seed_activity, test_student
):
    resp = ActivityResponse(
        activity_id=seed_activity.id,
        user_id=test_student.id,
        payload={"reactions": ["clap", "think"]},
        status="on_time",
    )
    db_session.add(resp)
    await db_session.commit()
    await db_session.refresh(resp)
    assert resp.id is not None
    assert isinstance(resp.id, uuid.UUID)
    assert resp.activity_id == seed_activity.id
    assert resp.user_id == test_student.id
    assert resp.payload == {"reactions": ["clap", "think"]}
    assert resp.status == "on_time"
    assert resp.submitted_at is not None
    # TimestampMixin present; NO soft-delete on a student-owned row.
    assert resp.created_at is not None
    assert resp.updated_at is not None
    assert not hasattr(resp, "deleted_at")


@pytest.mark.asyncio
async def test_activity_response_bad_status_rejected(
    db_session, seed_activity, test_student
):
    db_session.add(
        ActivityResponse(
            activity_id=seed_activity.id,
            user_id=test_student.id,
            status="nonsense",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_activity_response_unique_activity_user(
    db_session, seed_activity, test_student
):
    """uq_activity_responses_activity_user on (activity_id, user_id) — a resubmit
    upserts in place; comment_reaction stacks multiple reactions in ``payload``."""
    db_session.add(
        ActivityResponse(
            activity_id=seed_activity.id,
            user_id=test_student.id,
            status="on_time",
        )
    )
    await db_session.flush()
    db_session.add(
        ActivityResponse(
            activity_id=seed_activity.id,
            user_id=test_student.id,
            status="late",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


# ---------------------------------------------------------------------------
# Migration: RLS declared on activity_responses (Decision 3)
# ---------------------------------------------------------------------------


def test_migration_enables_rls_on_activity_responses():
    """The B3 migration COPIES the ``e6c2b8f4a19d`` owner-isolation structure for
    ``activity_responses`` (create table + user_id index + ENABLE RLS + policy),
    while ``activities`` stays a plain no-RLS table (Decision 3)."""
    src = MIGRATION.read_text(encoding="utf-8")
    assert "ALTER TABLE activity_responses ENABLE ROW LEVEL SECURITY" in src
    assert "activity_responses_owner_isolation" in src
    assert "ix_activity_responses_user_id" in src
    assert "current_setting('app.current_user_id', true)::uuid" in src
    # activities is course-scoped / endpoint-guarded — NEVER RLS.
    assert "ALTER TABLE activities ENABLE ROW LEVEL SECURITY" not in src
    assert "down_revision: Union[str, None] = 'b8e5d1a4c297'" in src
