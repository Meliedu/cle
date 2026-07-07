"""P7 B11 (Decision 8b) — close lingering active launches on transition.

When a checkpoint transitions AWAY from ``published``/``live`` (close, or a
soft-delete), any still-``active`` ``checkpoint_launches`` rows are closed so a
stale launch token can never be scanned. Idempotent — closing when there is no
active launch is a no-op.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.main import app
from app.models.attendance import CheckpointLaunch
from app.models.checkpoint import Checkpoint
from app.models.course import Course
from app.models.curriculum import CourseMeeting
from app.models.user import User
from app.services.checkpoint_qr import launch_checkpoint


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def launch_secret(monkeypatch):
    monkeypatch.setattr(settings, "checkpoint_token_secret", "t" * 48)
    yield


async def _make_published(db: AsyncSession, instructor: User) -> dict:
    course = Course(
        name="Close Course",
        language="zh",
        instructor_id=instructor.id,
        enroll_code="CL" + uuid.uuid4().hex[:6].upper(),
    )
    db.add(course)
    await db.flush()

    meeting = CourseMeeting(
        course_id=course.id, meeting_index=1, title="Session 1", scheduled_at=_utcnow()
    )
    db.add(meeting)
    await db.flush()

    cp = Checkpoint(
        course_id=course.id,
        kind="session",
        title="Session checkpoint",
        status="published",
        qr_enabled=True,
        meeting_id=meeting.id,
        release_at=_utcnow() - timedelta(hours=1),
        close_at=None,
        close_rule="manual",
    )
    db.add(cp)
    await db.commit()
    await db.refresh(cp)
    return {"course": course, "meeting": meeting, "cp": cp}


def _instructor_client(db_session: AsyncSession, user: User) -> AsyncClient:
    async def override_db():
        yield db_session

    async def override_user():
        return user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer x"},
    )


async def _active_launches(db: AsyncSession, checkpoint_id) -> list:
    return (
        await db.execute(
            select(CheckpointLaunch).where(
                CheckpointLaunch.checkpoint_id == checkpoint_id,
                CheckpointLaunch.status == "active",
            )
        )
    ).scalars().all()


@pytest.mark.asyncio
async def test_close_checkpoint_closes_active_launch(
    db_session: AsyncSession, test_instructor: User, launch_secret
):
    made = await _make_published(db_session, test_instructor)
    launch = await launch_checkpoint(
        db_session, checkpoint=made["cp"], launched_by=test_instructor.id
    )
    assert launch.status == "active"

    async with _instructor_client(db_session, test_instructor) as ac:
        r = await ac.post(f"/api/checkpoints/{made['cp'].id}/close")
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "closed"

    assert await _active_launches(db_session, made["cp"].id) == []
    closed = await db_session.get(CheckpointLaunch, launch.id)
    assert closed.status == "closed"


@pytest.mark.asyncio
async def test_delete_checkpoint_closes_active_launch(
    db_session: AsyncSession, test_instructor: User, launch_secret
):
    made = await _make_published(db_session, test_instructor)
    launch = await launch_checkpoint(
        db_session, checkpoint=made["cp"], launched_by=test_instructor.id
    )

    async with _instructor_client(db_session, test_instructor) as ac:
        r = await ac.delete(f"/api/checkpoints/{made['cp'].id}")
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    closed = await db_session.get(CheckpointLaunch, launch.id)
    assert closed.status == "closed"


@pytest.mark.asyncio
async def test_close_with_no_active_launch_is_noop(
    db_session: AsyncSession, test_instructor: User, launch_secret
):
    """Closing a checkpoint that was never launched must not error (idempotent)."""
    made = await _make_published(db_session, test_instructor)

    async with _instructor_client(db_session, test_instructor) as ac:
        r = await ac.post(f"/api/checkpoints/{made['cp'].id}/close")
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "closed"
    assert await _active_launches(db_session, made["cp"].id) == []
