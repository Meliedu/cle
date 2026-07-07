"""P3 T13: the ``close_due_checkpoints`` cron.

``close_due_checkpoints(session)`` sweeps ``published``/``live`` checkpoints whose
close is due (per ``close_at``/``close_rule``) to ``closed`` — routing EVERY
transition through ``assert_transition`` (T1, the single source of truth). It also
flips any ``active`` ``checkpoint_launches`` row for those checkpoints to
``closed`` and broadcasts a terminal ``closed`` event on the T12 monitor hub
(best-effort). A second run is a no-op (nothing left due) — idempotent + re-run
safe, so the worker can tick it every minute.

"Due" per ``close_rule``:
- ``at_close_at``   → due once ``close_at <= now``.
- ``end_of_session``→ due once the linked meeting has ended
  (``scheduled_at + duration_minutes <= now``); falls back to ``close_at`` if the
  checkpoint has no meeting.
- ``manual`` (or NULL) → never auto-closes (teacher closes by hand).
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course, User
from app.models.attendance import CheckpointLaunch
from app.models.checkpoint import Checkpoint, CheckpointCard, CheckpointResponse
from app.models.curriculum import CourseMeeting
from app.services.checkpoint_monitor import monitor_manager
from app.services.checkpoints import close_due_checkpoints


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _FakeWS:
    """Minimal WebSocket stand-in — collects broadcast payloads."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def accept(self) -> None:
        pass

    async def send_text(self, data: str) -> None:
        self.sent.append(json.loads(data))

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)


@pytest.fixture(autouse=True)
def _clear_monitor_manager():
    monitor_manager.connections.clear()
    monitor_manager.sessions.clear()
    monitor_manager._locks.clear()
    yield
    monitor_manager.connections.clear()
    monitor_manager.sessions.clear()
    monitor_manager._locks.clear()


async def _make_course(db: AsyncSession, owner: User, code: str) -> Course:
    course = Course(
        name="Close Cron Test",
        language="english",
        instructor_id=owner.id,
        enroll_code=code,
    )
    db.add(course)
    await db.flush()
    return course


async def _make_meeting(
    db: AsyncSession, course: Course, *, index: int, ends_ago: timedelta
) -> CourseMeeting:
    """A meeting whose END (scheduled_at + duration) is ``ends_ago`` in the past
    (negative delta → future)."""
    duration = 60
    scheduled_at = _now() - ends_ago - timedelta(minutes=duration)
    meeting = CourseMeeting(
        course_id=course.id,
        meeting_index=index,
        scheduled_at=scheduled_at,
        duration_minutes=duration,
    )
    db.add(meeting)
    await db.flush()
    return meeting


async def _make_checkpoint(
    db: AsyncSession,
    course: Course,
    *,
    status: str,
    close_rule: str | None,
    close_at: datetime | None = None,
    meeting: CourseMeeting | None = None,
) -> Checkpoint:
    cp = Checkpoint(
        course_id=course.id,
        kind="session",
        title="cp",
        status=status,
        close_rule=close_rule,
        close_at=close_at,
        meeting_id=meeting.id if meeting else None,
    )
    db.add(cp)
    await db.flush()
    return cp


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession, logged_in_user: User):
    course = await _make_course(db_session, logged_in_user, "CLOSE001")

    past = _now() - timedelta(hours=1)
    future = _now() + timedelta(hours=1)

    ended_meeting = await _make_meeting(
        db_session, course, index=1, ends_ago=timedelta(hours=1)
    )
    future_meeting = await _make_meeting(
        db_session, course, index=2, ends_ago=-timedelta(hours=1)
    )

    cps = {
        # published + at_close_at in the past → DUE
        "due_close_at": await _make_checkpoint(
            db_session, course, status="published",
            close_rule="at_close_at", close_at=past,
        ),
        # live + at_close_at in the future → NOT due
        "future_close_at": await _make_checkpoint(
            db_session, course, status="live",
            close_rule="at_close_at", close_at=future,
        ),
        # published + manual, even with a past close_at → never auto-closes
        "manual": await _make_checkpoint(
            db_session, course, status="published",
            close_rule="manual", close_at=past,
        ),
        # live + end_of_session, meeting already ended → DUE
        "due_eos": await _make_checkpoint(
            db_session, course, status="live",
            close_rule="end_of_session", meeting=ended_meeting,
        ),
        # published + end_of_session, meeting ends later → NOT due
        "future_eos": await _make_checkpoint(
            db_session, course, status="published",
            close_rule="end_of_session", meeting=future_meeting,
        ),
        # approved (pre-publish) + past close_at → not an eligible source state
        "approved": await _make_checkpoint(
            db_session, course, status="approved",
            close_rule="at_close_at", close_at=past,
        ),
    }

    # An active launch on the due checkpoint — the cron must close it too.
    launch = CheckpointLaunch(
        checkpoint_id=cps["due_close_at"].id,
        meeting_id=ended_meeting.id,
        token="tok",
        jti=str(uuid.uuid4()),
        window_start=past,
        window_end=future,
        launched_by=logged_in_user.id,
        status="active",
    )
    db_session.add(launch)
    await db_session.commit()
    return {"course": course, "cps": cps, "launch": launch}


@pytest.mark.asyncio
async def test_closes_only_due_checkpoints(db_session: AsyncSession, seeded):
    n = await close_due_checkpoints(db_session)
    assert n == 2  # due_close_at + due_eos

    cps = seeded["cps"]
    for key in ("due_close_at", "due_eos"):
        await db_session.refresh(cps[key])
        assert cps[key].status == "closed"

    for key in ("future_close_at", "manual", "future_eos"):
        await db_session.refresh(cps[key])
        assert cps[key].status != "closed", key

    # The approved checkpoint is not an eligible source state — untouched.
    await db_session.refresh(cps["approved"])
    assert cps["approved"].status == "approved"


@pytest.mark.asyncio
async def test_closes_active_launch(db_session: AsyncSession, seeded):
    await close_due_checkpoints(db_session)

    launch = (
        await db_session.execute(
            select(CheckpointLaunch).where(
                CheckpointLaunch.id == seeded["launch"].id
            )
        )
    ).scalar_one()
    assert launch.status == "closed"


@pytest.mark.asyncio
async def test_idempotent_second_run_noops(db_session: AsyncSession, seeded):
    first = await close_due_checkpoints(db_session)
    assert first == 2
    second = await close_due_checkpoints(db_session)
    assert second == 0


@pytest.mark.asyncio
async def test_broadcasts_closed_to_monitor(db_session: AsyncSession, seeded):
    cp = seeded["cps"]["due_close_at"]
    # Seed a response so the aggregate is non-trivial.
    review = CheckpointCard(
        checkpoint_id=cp.id, position=0, kind="review_point", prompt="?"
    )
    db_session.add(review)
    await db_session.flush()
    student = User(
        better_auth_id="close_stu", email="close_stu@connect.ust.hk",
        full_name="S", role="student",
    )
    db_session.add(student)
    await db_session.flush()
    db_session.add(
        CheckpointResponse(
            checkpoint_id=cp.id, card_id=review.id, user_id=student.id,
            confidence=1, status="on_time",
        )
    )
    await db_session.commit()

    ws = _FakeWS()
    await monitor_manager.connect(str(cp.id), ws)

    await close_due_checkpoints(db_session)

    closed = [m for m in ws.sent if m.get("type") == "closed"]
    assert closed, f"expected a closed broadcast, got {ws.sent}"
    assert closed[-1]["submission_count"] == 1


@pytest.mark.asyncio
async def test_routes_through_assert_transition(db_session: AsyncSession, seeded):
    """A published checkpoint is walked published→live→closed (no skip-edge)."""
    cp = seeded["cps"]["due_close_at"]
    assert cp.status == "published"
    await close_due_checkpoints(db_session)
    await db_session.refresh(cp)
    assert cp.status == "closed"
