"""P3 T9 — QR launch service + endpoint (token signing + gate).

Covers the teacher-side QR launch half of the checkpoint loop:

* ``launch_checkpoint`` signs a PyJWT HS256 token (mirroring
  ``canvas_oauth.encode_state``) with ``{launch_id, checkpoint_id, meeting_id,
  jti, exp=window_end}``, persisting a ``checkpoint_launches`` row.
* The **gate** raises the typed ``QRNotAvailable`` (mapped to the
  ``QR_NOT_AVAILABLE`` code the mobile flow switches on) unless the checkpoint is
  ``published``/``live`` + session-bound (has a meeting) + ``qr_enabled`` + inside
  its release..close window.
* Only ONE active launch per checkpoint (partial unique index). A ``rotate``
  closes the prior launch (``status='closed'``) and issues a fresh token with a
  new ``launch_id``/``jti``.
* An expired token (``exp`` past) fails to decode; a tampered signature fails.
* Secret validation (≥32 bytes) is enforced at launch time (fails closed), not
  at startup — so dev/test stay bootable with checkpoints unconfigured.
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
from app.services.checkpoint_qr import (
    LaunchTokenInvalid,
    QRNotAvailable,
    decode_launch_token,
    encode_launch_token,
    launch_checkpoint,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def launch_secret(monkeypatch):
    """A configured ≥32-byte signing secret for the duration of the test."""
    monkeypatch.setattr(settings, "checkpoint_token_secret", "t" * 48)
    yield


async def _make_launchable(
    db: AsyncSession,
    instructor: User,
    *,
    status: str = "published",
    qr_enabled: bool = True,
    release_at: datetime | None = None,
    close_at: datetime | None = None,
    with_meeting: bool = True,
) -> dict:
    course = Course(
        name="QR Course",
        language="zh",
        instructor_id=instructor.id,
        enroll_code="QR" + uuid.uuid4().hex[:6].upper(),
    )
    db.add(course)
    await db.flush()

    meeting_id = None
    meeting = None
    if with_meeting:
        meeting = CourseMeeting(
            course_id=course.id,
            meeting_index=1,
            title="Session 1",
            scheduled_at=_utcnow(),
        )
        db.add(meeting)
        await db.flush()
        meeting_id = meeting.id

    cp = Checkpoint(
        course_id=course.id,
        kind="session",
        title="Session checkpoint",
        status=status,
        qr_enabled=qr_enabled,
        meeting_id=meeting_id,
        release_at=release_at if release_at is not None else _utcnow() - timedelta(hours=1),
        close_at=close_at,
        close_rule="manual",
    )
    db.add(cp)
    await db.commit()
    await db.refresh(cp)
    return {"course": course, "meeting": meeting, "cp": cp}


# ----- token signing -----

@pytest.mark.asyncio
async def test_launch_signs_token_with_expected_claims(
    db_session: AsyncSession, test_instructor: User, launch_secret
):
    made = await _make_launchable(db_session, test_instructor)
    cp = made["cp"]

    launch = await launch_checkpoint(
        db_session, checkpoint=cp, launched_by=test_instructor.id
    )
    assert launch.status == "active"
    assert launch.checkpoint_id == cp.id
    assert launch.meeting_id == cp.meeting_id
    assert launch.launched_by == test_instructor.id

    payload = decode_launch_token(launch.token)
    assert payload["launch_id"] == str(launch.id)
    assert payload["checkpoint_id"] == str(cp.id)
    assert payload["meeting_id"] == str(cp.meeting_id)
    assert payload["jti"] == launch.jti
    assert payload["exp"] == int(launch.window_end.timestamp())


@pytest.mark.asyncio
async def test_launch_persists_single_active_row(
    db_session: AsyncSession, test_instructor: User, launch_secret
):
    made = await _make_launchable(db_session, test_instructor)
    await launch_checkpoint(
        db_session, checkpoint=made["cp"], launched_by=test_instructor.id
    )
    rows = (
        await db_session.execute(
            select(CheckpointLaunch).where(
                CheckpointLaunch.checkpoint_id == made["cp"].id,
                CheckpointLaunch.status == "active",
            )
        )
    ).scalars().all()
    assert len(rows) == 1


# ----- gate -----

@pytest.mark.asyncio
async def test_gate_rejects_draft(
    db_session: AsyncSession, test_instructor: User, launch_secret
):
    made = await _make_launchable(db_session, test_instructor, status="draft")
    with pytest.raises(QRNotAvailable):
        await launch_checkpoint(
            db_session, checkpoint=made["cp"], launched_by=test_instructor.id
        )


@pytest.mark.asyncio
async def test_gate_rejects_unbound_session(
    db_session: AsyncSession, test_instructor: User, launch_secret
):
    made = await _make_launchable(
        db_session, test_instructor, status="published", with_meeting=False
    )
    with pytest.raises(QRNotAvailable):
        await launch_checkpoint(
            db_session, checkpoint=made["cp"], launched_by=test_instructor.id
        )


@pytest.mark.asyncio
async def test_gate_rejects_qr_disabled(
    db_session: AsyncSession, test_instructor: User, launch_secret
):
    made = await _make_launchable(
        db_session, test_instructor, status="published", qr_enabled=False
    )
    with pytest.raises(QRNotAvailable):
        await launch_checkpoint(
            db_session, checkpoint=made["cp"], launched_by=test_instructor.id
        )


@pytest.mark.asyncio
async def test_gate_rejects_out_of_window(
    db_session: AsyncSession, test_instructor: User, launch_secret
):
    made = await _make_launchable(
        db_session,
        test_instructor,
        status="published",
        release_at=_utcnow() + timedelta(hours=1),
    )
    with pytest.raises(QRNotAvailable):
        await launch_checkpoint(
            db_session, checkpoint=made["cp"], launched_by=test_instructor.id
        )


@pytest.mark.asyncio
async def test_launch_accepts_live_status(
    db_session: AsyncSession, test_instructor: User, launch_secret
):
    made = await _make_launchable(db_session, test_instructor, status="live")
    launch = await launch_checkpoint(
        db_session, checkpoint=made["cp"], launched_by=test_instructor.id
    )
    assert launch.status == "active"


# ----- single active + rotate -----

@pytest.mark.asyncio
async def test_second_launch_without_rotate_rejected(
    db_session: AsyncSession, test_instructor: User, launch_secret
):
    made = await _make_launchable(db_session, test_instructor)
    await launch_checkpoint(
        db_session, checkpoint=made["cp"], launched_by=test_instructor.id
    )
    with pytest.raises(QRNotAvailable):
        await launch_checkpoint(
            db_session, checkpoint=made["cp"], launched_by=test_instructor.id
        )


@pytest.mark.asyncio
async def test_rotate_closes_prior_and_issues_fresh(
    db_session: AsyncSession, test_instructor: User, launch_secret
):
    made = await _make_launchable(db_session, test_instructor)
    first = await launch_checkpoint(
        db_session, checkpoint=made["cp"], launched_by=test_instructor.id
    )
    first_id, first_jti, first_token = first.id, first.jti, first.token

    second = await launch_checkpoint(
        db_session, checkpoint=made["cp"], launched_by=test_instructor.id, rotate=True
    )
    assert second.id != first_id
    assert second.jti != first_jti
    assert second.token != first_token
    assert second.status == "active"

    # The prior launch is now closed; exactly one active remains.
    active = (
        await db_session.execute(
            select(CheckpointLaunch).where(
                CheckpointLaunch.checkpoint_id == made["cp"].id,
                CheckpointLaunch.status == "active",
            )
        )
    ).scalars().all()
    assert len(active) == 1
    assert active[0].id == second.id

    prior = await db_session.get(CheckpointLaunch, first_id)
    assert prior.status == "closed"


# ----- token decode failures -----

def test_expired_token_fails_decode(launch_secret):
    token = encode_launch_token(
        {
            "launch_id": str(uuid.uuid4()),
            "checkpoint_id": str(uuid.uuid4()),
            "meeting_id": str(uuid.uuid4()),
            "jti": uuid.uuid4().hex,
            "exp": int((_utcnow() - timedelta(minutes=5)).timestamp()),
        }
    )
    with pytest.raises(LaunchTokenInvalid):
        decode_launch_token(token)


def test_tampered_token_fails_decode(launch_secret):
    token = encode_launch_token(
        {
            "launch_id": str(uuid.uuid4()),
            "checkpoint_id": str(uuid.uuid4()),
            "meeting_id": str(uuid.uuid4()),
            "jti": uuid.uuid4().hex,
            "exp": int((_utcnow() + timedelta(minutes=15)).timestamp()),
        }
    )
    # Flip the final character of the signature segment.
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(LaunchTokenInvalid):
        decode_launch_token(tampered)


# ----- fail closed when unconfigured -----

@pytest.mark.asyncio
async def test_launch_fails_closed_when_secret_unconfigured(
    db_session: AsyncSession, test_instructor: User, monkeypatch
):
    monkeypatch.setattr(settings, "checkpoint_token_secret", None)
    made = await _make_launchable(db_session, test_instructor)
    with pytest.raises(QRNotAvailable):
        await launch_checkpoint(
            db_session, checkpoint=made["cp"], launched_by=test_instructor.id
        )


@pytest.mark.asyncio
async def test_launch_fails_closed_when_secret_too_short(
    db_session: AsyncSession, test_instructor: User, monkeypatch
):
    monkeypatch.setattr(settings, "checkpoint_token_secret", "short")
    made = await _make_launchable(db_session, test_instructor)
    with pytest.raises(QRNotAvailable):
        await launch_checkpoint(
            db_session, checkpoint=made["cp"], launched_by=test_instructor.id
        )


# ----- endpoint -----

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


@pytest.mark.asyncio
async def test_launch_endpoint_returns_token(
    db_session: AsyncSession, test_instructor: User, launch_secret
):
    made = await _make_launchable(db_session, test_instructor)
    async with _instructor_client(db_session, test_instructor) as ac:
        r = await ac.post(f"/api/checkpoints/{made['cp'].id}/launch")
    app.dependency_overrides.clear()
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["checkpoint_id"] == str(made["cp"].id)
    assert data["meeting_id"] == str(made["cp"].meeting_id)
    assert data["status"] == "active"
    assert data["token"]
    payload = decode_launch_token(data["token"])
    assert payload["launch_id"] == data["id"]


@pytest.mark.asyncio
async def test_launch_endpoint_owner_guarded(
    db_session: AsyncSession, test_instructor: User, launch_secret
):
    made = await _make_launchable(db_session, test_instructor)
    other = User(
        better_auth_id="qr_other_instructor",
        email="other@ust.hk",
        full_name="Other Instructor",
        role="instructor",
    )
    db_session.add(other)
    await db_session.commit()
    async with _instructor_client(db_session, other) as ac:
        r = await ac.post(f"/api/checkpoints/{made['cp'].id}/launch")
    app.dependency_overrides.clear()
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_launch_endpoint_qr_not_available(
    db_session: AsyncSession, test_instructor: User, launch_secret
):
    made = await _make_launchable(db_session, test_instructor, status="draft")
    async with _instructor_client(db_session, test_instructor) as ac:
        r = await ac.post(f"/api/checkpoints/{made['cp'].id}/launch")
    app.dependency_overrides.clear()
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "QR_NOT_AVAILABLE"


@pytest.mark.asyncio
async def test_launch_endpoint_rotate(
    db_session: AsyncSession, test_instructor: User, launch_secret
):
    made = await _make_launchable(db_session, test_instructor)
    async with _instructor_client(db_session, test_instructor) as ac:
        r1 = await ac.post(f"/api/checkpoints/{made['cp'].id}/launch")
        assert r1.status_code == 201, r1.text
        r2 = await ac.post(
            f"/api/checkpoints/{made['cp'].id}/launch", json={"rotate": True}
        )
    app.dependency_overrides.clear()
    assert r2.status_code == 201, r2.text
    assert r2.json()["data"]["id"] != r1.json()["data"]["id"]
    assert r2.json()["data"]["token"] != r1.json()["data"]["token"]
