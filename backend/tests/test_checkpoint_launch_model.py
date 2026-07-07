"""Model/constraint tests for ``checkpoint_launches`` (P3 Task 4).

``checkpoint_launches`` is an operational / teacher-owned table (Decision 3):
NO RLS — it carries a signed QR-launch token, not student-owned data, and is
guarded at the endpoint layer. Here we cover only the ORM columns, defaults and
the CHECK constraint + the PARTIAL UNIQUE INDEX that enforces a single active
launch per checkpoint (``(checkpoint_id) WHERE status='active'``) via
``Base.metadata.create_all`` in the disposable test DB (``db_session``).

The token itself (PyJWT HS256, mirroring ``canvas_oauth.encode_state``) is signed
in T9 — this task only lands the row + the ``checkpoint_token_secret`` config.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError

from app.models.checkpoint import Checkpoint
from app.models.attendance import CheckpointLaunch
from app.models.course import Course
from app.models.curriculum import CourseMeeting


@pytest_asyncio.fixture
async def seed_launch_ctx(db_session, test_instructor):
    course = Course(
        name="LANG1511",
        language="zh",
        instructor_id=test_instructor.id,
        enroll_code="LNCH" + uuid.uuid4().hex[:4].upper(),
    )
    db_session.add(course)
    await db_session.flush()
    meeting = CourseMeeting(
        course_id=course.id,
        meeting_index=1,
        title="Session 1",
        scheduled_at=datetime.now(timezone.utc),
    )
    db_session.add(meeting)
    await db_session.flush()
    cp = Checkpoint(course_id=course.id, kind="session", title="Session 1 check")
    db_session.add(cp)
    await db_session.commit()
    await db_session.refresh(cp)
    await db_session.refresh(meeting)
    return cp, meeting


def _make_launch(cp, meeting, launched_by, *, status="active", jti=None, token=None):
    now = datetime.now(timezone.utc)
    return CheckpointLaunch(
        checkpoint_id=cp.id,
        meeting_id=meeting.id,
        token=token or ("tok_" + uuid.uuid4().hex),
        jti=jti or uuid.uuid4().hex,
        window_start=now,
        window_end=now + timedelta(minutes=15),
        launched_by=launched_by,
        status=status,
    )


@pytest.mark.asyncio
async def test_launch_create_and_defaults(
    db_session, seed_launch_ctx, test_instructor
):
    cp, meeting = seed_launch_ctx
    launch = _make_launch(cp, meeting, test_instructor.id)
    db_session.add(launch)
    await db_session.commit()
    await db_session.refresh(launch)
    assert launch.id is not None
    assert launch.checkpoint_id == cp.id
    assert launch.meeting_id == meeting.id
    assert launch.status == "active"
    assert launch.token
    assert launch.jti
    assert launch.window_start is not None
    assert launch.window_end is not None
    assert launch.launched_by == test_instructor.id
    assert launch.created_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["active", "closed"])
async def test_launch_status_accepts_valid(
    db_session, seed_launch_ctx, test_instructor, status
):
    cp, meeting = seed_launch_ctx
    launch = _make_launch(cp, meeting, test_instructor.id, status=status)
    db_session.add(launch)
    await db_session.commit()
    await db_session.refresh(launch)
    assert launch.status == status


@pytest.mark.asyncio
async def test_launch_bad_status_rejected(
    db_session, seed_launch_ctx, test_instructor
):
    cp, meeting = seed_launch_ctx
    db_session.add(
        _make_launch(cp, meeting, test_instructor.id, status="paused")
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_two_active_launches_same_checkpoint_rejected(
    db_session, seed_launch_ctx, test_instructor
):
    """Partial unique index: only ONE active launch per checkpoint."""
    cp, meeting = seed_launch_ctx
    db_session.add(_make_launch(cp, meeting, test_instructor.id, status="active"))
    await db_session.flush()
    db_session.add(_make_launch(cp, meeting, test_instructor.id, status="active"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_active_plus_closed_same_checkpoint_allowed(
    db_session, seed_launch_ctx, test_instructor
):
    """A rotate closes the prior launch (status='closed') then issues a fresh
    active one — closed rows are excluded from the partial unique index."""
    cp, meeting = seed_launch_ctx
    db_session.add(_make_launch(cp, meeting, test_instructor.id, status="closed"))
    db_session.add(_make_launch(cp, meeting, test_instructor.id, status="active"))
    await db_session.commit()  # no IntegrityError
    # And a second closed row is fine too.
    db_session.add(_make_launch(cp, meeting, test_instructor.id, status="closed"))
    await db_session.commit()


@pytest.mark.asyncio
async def test_two_closed_launches_same_checkpoint_allowed(
    db_session, seed_launch_ctx, test_instructor
):
    cp, meeting = seed_launch_ctx
    db_session.add(_make_launch(cp, meeting, test_instructor.id, status="closed"))
    db_session.add(_make_launch(cp, meeting, test_instructor.id, status="closed"))
    await db_session.commit()  # partial index only covers active rows


def test_checkpoint_token_secret_config_defaults_none():
    """T4 only adds the field (defaults None so dev/test stay bootable). The
    ≥32-byte length check lives in the T9 launch service, not at startup."""
    from app.config import Settings

    s = Settings()
    assert s.checkpoint_token_secret is None
