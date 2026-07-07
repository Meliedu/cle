"""P3 T12: live monitor WS reusing the live-quiz ConnectionManager hub.

The monitor WS (`/api/checkpoints/{id}/monitor`) copies ``websocket_live``'s
auth preamble (``?token=`` → ``verify_jwt`` → resolve user) but swaps the
enrollment check for an OWNER check (only the checkpoint's course instructor may
monitor). On connect the client receives ``{submission_count,
confidence_distribution}``; a ``submission`` broadcast lands when a student's
response is committed; a ``closed`` broadcast lands when the checkpoint closes.

Decision 4 — NO new WS framework: ``monitor_manager`` is an instance of the SAME
``ConnectionManager`` class from ``live_quiz``; broadcasts go through
``monitor_manager.connect/broadcast/disconnect``.

The WS handler is exercised by calling the endpoint coroutine directly with a
``FakeWebSocket`` (mirrors the ``verify_jwt`` monkeypatch pattern established in
``test_pending_enrollment_claim``). This keeps the whole flow inside the pytest
event loop with the real ``db_session`` — a Starlette ``TestClient`` would run
the app in a separate portal loop and break the asyncpg connection binding.
"""
import json
import uuid

import pytest
import pytest_asyncio
from fastapi import WebSocketDisconnect, WebSocketException
from sqlalchemy.ext.asyncio import AsyncSession

import app.api.checkpoints as checkpoints_api
from app.models import Course, User
from app.models.checkpoint import Checkpoint, CheckpointCard, CheckpointResponse
from app.services.auth import VerifiedToken
from app.services.checkpoint_monitor import (
    broadcast_closed,
    compute_monitor_state,
    monitor_manager,
)
from app.services.checkpoint_responses import submit_checkpoint_response
from app.services.live_quiz import ConnectionManager
from app.services.live_quiz import manager as live_manager


# --------------------------------------------------------------------------- #
#  Test doubles + fixtures                                                     #
# --------------------------------------------------------------------------- #


class FakeWebSocket:
    """Minimal WebSocket stand-in for the monitor handler + ConnectionManager.

    ``receive_text`` raises ``WebSocketDisconnect`` once the scripted incoming
    queue drains so the handler's read-loop exits cleanly.
    """

    def __init__(self, incoming: list | None = None):
        self.accepted = False
        self.sent: list[dict] = []
        self._incoming = list(incoming or [])

    async def accept(self):
        self.accepted = True

    async def send_json(self, data):
        self.sent.append(data)

    async def send_text(self, data):
        # ConnectionManager.broadcast sends json.dumps(...) via send_text.
        self.sent.append(json.loads(data))

    async def receive_text(self):
        if self._incoming:
            return self._incoming.pop(0)
        raise WebSocketDisconnect()

    async def receive_json(self):
        if self._incoming:
            return self._incoming.pop(0)
        raise WebSocketDisconnect()


class _SessionCtx:
    """An ``async with`` wrapper that yields a live session without closing it."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *exc) -> bool:
        return False


@pytest.fixture(autouse=True)
def _clear_monitor_manager():
    """Isolate the process-wide ``monitor_manager`` singleton between tests."""
    monitor_manager.connections.clear()
    monitor_manager.sessions.clear()
    monitor_manager._locks.clear()
    yield
    monitor_manager.connections.clear()
    monitor_manager.sessions.clear()
    monitor_manager._locks.clear()


def _patch_ws_deps(monkeypatch, *, sub: str, session: AsyncSession):
    """Point the WS handler at ``session`` and stub ``verify_jwt`` to ``sub``."""
    monkeypatch.setattr(
        checkpoints_api, "async_session_factory", lambda: _SessionCtx(session)
    )
    monkeypatch.setattr(
        checkpoints_api,
        "verify_jwt",
        lambda token: VerifiedToken("better_auth", {"sub": sub}),
    )


async def _make_instructor(db: AsyncSession, suffix: str) -> User:
    user = User(
        better_auth_id=f"mon_instr_{suffix}",
        email=f"mon_instr_{suffix}@ust.hk",
        full_name=f"Instructor {suffix}",
        role="instructor",
    )
    db.add(user)
    await db.flush()
    return user


async def _make_course(db: AsyncSession, owner: User, code: str) -> Course:
    course = Course(
        name="Monitor Test",
        language="english",
        instructor_id=owner.id,
        enroll_code=code,
    )
    db.add(course)
    await db.flush()
    return course


async def _make_checkpoint(
    db: AsyncSession, course: Course, *, status: str = "published"
) -> tuple[Checkpoint, CheckpointCard, CheckpointCard]:
    cp = Checkpoint(
        course_id=course.id, kind="session", title="Monitor checkpoint", status=status
    )
    db.add(cp)
    await db.flush()
    review = CheckpointCard(
        checkpoint_id=cp.id, position=0, kind="review_point", prompt="Confident?"
    )
    final = CheckpointCard(
        checkpoint_id=cp.id, position=1, kind="final_comments", prompt="Comments?"
    )
    db.add_all([review, final])
    await db.flush()
    return cp, review, final


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession, logged_in_user: User):
    """A published checkpoint owned by ``logged_in_user`` + two committed
    review-point responses (+2 and -1)."""
    course = await _make_course(db_session, logged_in_user, "MON00001")
    cp, review, final = await _make_checkpoint(db_session, course)

    s_a = User(
        better_auth_id="mon_stu_a", email="mon_stu_a@connect.ust.hk",
        full_name="A", role="student",
    )
    s_b = User(
        better_auth_id="mon_stu_b", email="mon_stu_b@connect.ust.hk",
        full_name="B", role="student",
    )
    db_session.add_all([s_a, s_b])
    await db_session.flush()

    db_session.add_all([
        CheckpointResponse(
            checkpoint_id=cp.id, card_id=review.id, user_id=s_a.id,
            confidence=2, status="on_time",
        ),
        CheckpointResponse(
            checkpoint_id=cp.id, card_id=review.id, user_id=s_b.id,
            confidence=-1, status="on_time",
        ),
    ])
    await db_session.commit()
    await db_session.refresh(cp)
    return {"course": course, "cp": cp, "review": review, "final": final}


# --------------------------------------------------------------------------- #
#  Reuse assertion: no new WS framework                                        #
# --------------------------------------------------------------------------- #


def test_monitor_manager_reuses_connection_manager_class():
    # SAME class as the live-quiz hub, but a distinct instance (own namespace).
    assert isinstance(monitor_manager, ConnectionManager)
    assert monitor_manager is not live_manager


# --------------------------------------------------------------------------- #
#  State aggregation                                                           #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_compute_monitor_state(db_session: AsyncSession, seeded):
    state = await compute_monitor_state(db_session, seeded["cp"].id)
    assert state["submission_count"] == 2
    assert state["confidence_distribution"] == {
        "-2": 0, "-1": 1, "0": 0, "1": 0, "2": 1,
    }


# --------------------------------------------------------------------------- #
#  WS connect + auth preamble                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_monitor_connect_sends_state(db_session, seeded, monkeypatch, logged_in_user):
    _patch_ws_deps(monkeypatch, sub=logged_in_user.better_auth_id, session=db_session)
    ws = FakeWebSocket()

    await checkpoints_api.websocket_monitor(
        ws, checkpoint_id=str(seeded["cp"].id), token="x"
    )

    assert ws.accepted is True
    assert ws.sent, "expected an initial state message on connect"
    first = ws.sent[0]
    assert first["type"] == "state"
    assert first["submission_count"] == 2
    assert first["confidence_distribution"]["2"] == 1
    # The read-loop exit disconnects and de-registers the socket.
    assert ws not in monitor_manager.connections.get(str(seeded["cp"].id), [])


@pytest.mark.asyncio
async def test_monitor_rejects_non_owner(db_session, seeded, monkeypatch):
    other = await _make_instructor(db_session, "outsider")
    await db_session.commit()
    _patch_ws_deps(monkeypatch, sub=other.better_auth_id, session=db_session)
    ws = FakeWebSocket()

    with pytest.raises(WebSocketException):
        await checkpoints_api.websocket_monitor(
            ws, checkpoint_id=str(seeded["cp"].id), token="x"
        )
    assert ws.accepted is False


@pytest.mark.asyncio
async def test_monitor_rejects_missing_token(seeded):
    ws = FakeWebSocket()
    with pytest.raises(WebSocketException):
        await checkpoints_api.websocket_monitor(
            ws, checkpoint_id=str(seeded["cp"].id), token=""
        )
    assert ws.accepted is False


# --------------------------------------------------------------------------- #
#  Broadcasts: submission (T7 wiring) + closed                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_submission_broadcasts_to_monitor(db_session, seeded):
    """Committing a student response fires a ``submission`` broadcast to a
    connected monitor (the T7 evidence seam is now wired)."""
    cp = seeded["cp"]
    review = seeded["review"]
    ws = FakeWebSocket()
    await monitor_manager.connect(str(cp.id), ws)

    student = User(
        better_auth_id="mon_new_stu", email="mon_new_stu@connect.ust.hk",
        full_name="New", role="student",
    )
    db_session.add(student)
    await db_session.flush()

    await submit_checkpoint_response(
        db_session,
        checkpoint=cp,
        card=review,
        user_id=student.id,
        confidence=1,
        text_response=None,
    )

    submissions = [m for m in ws.sent if m.get("type") == "submission"]
    assert submissions, f"expected a submission broadcast, got {ws.sent}"
    latest = submissions[-1]
    # 2 seeded responses + this new one.
    assert latest["submission_count"] == 3
    assert latest["confidence_distribution"]["1"] == 1


@pytest.mark.asyncio
async def test_broadcast_closed_reaches_monitor(db_session, seeded):
    cp = seeded["cp"]
    ws = FakeWebSocket()
    await monitor_manager.connect(str(cp.id), ws)

    await broadcast_closed(db_session, cp.id)

    closed = [m for m in ws.sent if m.get("type") == "closed"]
    assert closed, f"expected a closed broadcast, got {ws.sent}"
    assert closed[-1]["submission_count"] == 2


@pytest.mark.asyncio
async def test_close_endpoint_broadcasts_closed(async_client, db_session, logged_in_user):
    """The teacher close endpoint emits a ``closed`` broadcast after commit."""
    course = await _make_course(db_session, logged_in_user, "MONCLOSE")
    cp, _review, _final = await _make_checkpoint(db_session, course, status="published")
    await db_session.commit()

    ws = FakeWebSocket()
    await monitor_manager.connect(str(cp.id), ws)

    r = await async_client.post(f"/api/checkpoints/{cp.id}/close")
    assert r.status_code == 200, r.text

    closed = [m for m in ws.sent if m.get("type") == "closed"]
    assert closed, f"expected a closed broadcast, got {ws.sent}"
