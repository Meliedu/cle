"""P5 B10: live activity monitor WS reusing the live-quiz ConnectionManager hub.

The monitor WS (`/api/activities/{id}/monitor`) copies ``websocket_monitor``'s
auth preamble (``?token=`` → ``verify_jwt`` → resolve user) but keeps the OWNER
check (only the activity's course instructor may monitor). On connect the client
receives ``{submission_count, distribution}``; a ``submission`` broadcast lands
when a student's response is committed; a ``closed`` broadcast lands when the
activity closes.

Decision 6 — NO new WS framework: ``monitor_manager`` is an instance of the SAME
``ConnectionManager`` class from ``live_quiz``; broadcasts go through
``monitor_manager.connect/broadcast/disconnect``.

The WS handler is exercised by calling the endpoint coroutine directly with a
``FakeWebSocket`` (mirrors the ``verify_jwt`` monkeypatch pattern from
``test_checkpoint_monitor``). This keeps the whole flow inside the pytest event
loop with the real ``db_session`` — a Starlette ``TestClient`` would run the app
in a separate portal loop and break the asyncpg connection binding.
"""
import json
import uuid

import pytest
import pytest_asyncio
from fastapi import WebSocketDisconnect, WebSocketException
from sqlalchemy.ext.asyncio import AsyncSession

import app.api.activities as activities_api
from app.models import Course, User
from app.models.activity import Activity, ActivityResponse
from app.services.activity_monitor import (
    broadcast_closed,
    compute_activity_monitor_state,
    monitor_manager,
)
from app.services.activity_responses import submit_activity_response
from app.services.auth import VerifiedToken
from app.services.live_quiz import ConnectionManager
from app.services.live_quiz import manager as live_manager


# --------------------------------------------------------------------------- #
#  Test doubles + fixtures                                                     #
# --------------------------------------------------------------------------- #


class FakeWebSocket:
    """Minimal WebSocket stand-in for the monitor handler + ConnectionManager."""

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
        activities_api, "async_session_factory", lambda: _SessionCtx(session)
    )
    monkeypatch.setattr(
        activities_api,
        "verify_jwt",
        lambda token: VerifiedToken("better_auth", {"sub": sub}),
    )


async def _make_instructor(db: AsyncSession, suffix: str) -> User:
    user = User(
        better_auth_id=f"act_mon_instr_{suffix}",
        email=f"act_mon_instr_{suffix}@ust.hk",
        full_name=f"Instructor {suffix}",
        role="instructor",
    )
    db.add(user)
    await db.flush()
    return user


async def _make_course(db: AsyncSession, owner: User, code: str) -> Course:
    course = Course(
        name="Activity Monitor Test",
        language="english",
        instructor_id=owner.id,
        enroll_code=code,
    )
    db.add(course)
    await db.flush()
    return course


async def _make_activity(
    db: AsyncSession,
    course: Course,
    *,
    fmt: str,
    config: dict,
    status: str = "published",
) -> Activity:
    act = Activity(
        course_id=course.id,
        format=fmt,
        title=f"Monitor {fmt}",
        config=config,
        status=status,
    )
    db.add(act)
    await db.flush()
    return act


async def _make_student(db: AsyncSession, suffix: str) -> User:
    student = User(
        better_auth_id=f"act_mon_stu_{suffix}",
        email=f"act_mon_stu_{suffix}@connect.ust.hk",
        full_name=f"Student {suffix}",
        role="student",
    )
    db.add(student)
    await db.flush()
    return student


# --------------------------------------------------------------------------- #
#  Reuse assertion: no new WS framework                                        #
# --------------------------------------------------------------------------- #


def test_monitor_manager_reuses_connection_manager_class():
    # SAME class as the live-quiz hub, but a distinct instance (own namespace).
    assert isinstance(monitor_manager, ConnectionManager)
    assert monitor_manager is not live_manager


# --------------------------------------------------------------------------- #
#  State aggregation — one distribution shape per format                       #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_compute_state_swipe(db_session: AsyncSession, logged_in_user: User):
    course = await _make_course(db_session, logged_in_user, "ACTMONSW")
    act = await _make_activity(
        db_session,
        course,
        fmt="swipe",
        config={"prompts": ["P0", "P1"]},
    )
    s_a = await _make_student(db_session, "sw_a")
    s_b = await _make_student(db_session, "sw_b")
    s_c = await _make_student(db_session, "sw_c")
    db_session.add_all([
        ActivityResponse(
            activity_id=act.id, user_id=s_a.id,
            payload={"prompt_index": 0, "direction": "right"}, status="on_time",
        ),
        ActivityResponse(
            activity_id=act.id, user_id=s_b.id,
            payload={"prompt_index": 0, "direction": "left"}, status="on_time",
        ),
        ActivityResponse(
            activity_id=act.id, user_id=s_c.id,
            payload={"prompt_index": 1, "direction": "right"}, status="on_time",
        ),
    ])
    await db_session.commit()

    state = await compute_activity_monitor_state(db_session, act.id)
    assert state["submission_count"] == 3
    assert state["distribution"] == {"left": 1, "right": 2}


@pytest.mark.asyncio
async def test_compute_state_vote(db_session: AsyncSession, logged_in_user: User):
    course = await _make_course(db_session, logged_in_user, "ACTMONVO")
    act = await _make_activity(
        db_session,
        course,
        fmt="vote",
        config={"options": ["A", "B", "C"]},
    )
    s_a = await _make_student(db_session, "vo_a")
    s_b = await _make_student(db_session, "vo_b")
    db_session.add_all([
        ActivityResponse(
            activity_id=act.id, user_id=s_a.id,
            payload={"choice": "A"}, status="on_time",
        ),
        ActivityResponse(
            activity_id=act.id, user_id=s_b.id,
            payload={"choice": "A"}, status="on_time",
        ),
    ])
    await db_session.commit()

    state = await compute_activity_monitor_state(db_session, act.id)
    assert state["submission_count"] == 2
    # Zero-filled from config options → stable axis (C never voted).
    assert state["distribution"] == {"A": 2, "B": 0, "C": 0}


@pytest.mark.asyncio
async def test_compute_state_comment_reaction(
    db_session: AsyncSession, logged_in_user: User
):
    course = await _make_course(db_session, logged_in_user, "ACTMONCR")
    act = await _make_activity(
        db_session,
        course,
        fmt="comment_reaction",
        config={"reactions": ["like", "love", "wow"]},
    )
    s_a = await _make_student(db_session, "cr_a")
    s_b = await _make_student(db_session, "cr_b")
    db_session.add_all([
        ActivityResponse(
            activity_id=act.id, user_id=s_a.id,
            payload={"entries": [
                {"reaction": "like"}, {"reaction": "love"},
            ]},
            status="on_time",
        ),
        ActivityResponse(
            activity_id=act.id, user_id=s_b.id,
            payload={"entries": [{"reaction": "like"}]},
            status="on_time",
        ),
    ])
    await db_session.commit()

    state = await compute_activity_monitor_state(db_session, act.id)
    # submission_count is rows (students), not stacked entries.
    assert state["submission_count"] == 2
    # Histogram over the stacked entries, zero-filled from config reactions.
    assert state["distribution"] == {"like": 2, "love": 1, "wow": 0}


# --------------------------------------------------------------------------- #
#  WS connect + auth preamble                                                  #
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def seeded_vote(db_session: AsyncSession, logged_in_user: User):
    """A published vote activity owned by ``logged_in_user`` + two committed
    responses (both 'A')."""
    course = await _make_course(db_session, logged_in_user, "ACTMONWS")
    act = await _make_activity(
        db_session, course, fmt="vote", config={"options": ["A", "B"]}
    )
    s_a = await _make_student(db_session, "ws_a")
    s_b = await _make_student(db_session, "ws_b")
    db_session.add_all([
        ActivityResponse(
            activity_id=act.id, user_id=s_a.id,
            payload={"choice": "A"}, status="on_time",
        ),
        ActivityResponse(
            activity_id=act.id, user_id=s_b.id,
            payload={"choice": "A"}, status="on_time",
        ),
    ])
    await db_session.commit()
    await db_session.refresh(act)
    return {"course": course, "act": act}


@pytest.mark.asyncio
async def test_monitor_connect_sends_state(
    db_session, seeded_vote, monkeypatch, logged_in_user
):
    _patch_ws_deps(monkeypatch, sub=logged_in_user.better_auth_id, session=db_session)
    ws = FakeWebSocket()

    await activities_api.websocket_monitor(
        ws, activity_id=str(seeded_vote["act"].id), token="x"
    )

    assert ws.accepted is True
    assert ws.sent, "expected an initial state message on connect"
    first = ws.sent[0]
    assert first["type"] == "state"
    assert first["submission_count"] == 2
    assert first["distribution"]["A"] == 2
    # The read-loop exit disconnects and de-registers the socket.
    assert ws not in monitor_manager.connections.get(str(seeded_vote["act"].id), [])


@pytest.mark.asyncio
async def test_monitor_rejects_non_owner(db_session, seeded_vote, monkeypatch):
    other = await _make_instructor(db_session, "outsider")
    await db_session.commit()
    _patch_ws_deps(monkeypatch, sub=other.better_auth_id, session=db_session)
    ws = FakeWebSocket()

    with pytest.raises(WebSocketException):
        await activities_api.websocket_monitor(
            ws, activity_id=str(seeded_vote["act"].id), token="x"
        )
    assert ws.accepted is False


@pytest.mark.asyncio
async def test_monitor_rejects_missing_token(seeded_vote):
    ws = FakeWebSocket()
    with pytest.raises(WebSocketException):
        await activities_api.websocket_monitor(
            ws, activity_id=str(seeded_vote["act"].id), token=""
        )
    assert ws.accepted is False


# --------------------------------------------------------------------------- #
#  Broadcasts: submission (B9 wiring) + closed                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_submission_broadcasts_to_monitor(db_session, seeded_vote):
    """Committing a student response fires a ``submission`` broadcast to a
    connected monitor (B9's ``_notify_monitor`` seam is now wired)."""
    act = seeded_vote["act"]
    ws = FakeWebSocket()
    await monitor_manager.connect(str(act.id), ws)

    student = await _make_student(db_session, "ws_new")
    await db_session.flush()

    await submit_activity_response(
        db_session,
        activity=act,
        user_id=student.id,
        payload={"choice": "B"},
    )

    submissions = [m for m in ws.sent if m.get("type") == "submission"]
    assert submissions, f"expected a submission broadcast, got {ws.sent}"
    latest = submissions[-1]
    # 2 seeded responses + this new one.
    assert latest["submission_count"] == 3
    assert latest["distribution"]["B"] == 1


@pytest.mark.asyncio
async def test_broadcast_closed_reaches_monitor(db_session, seeded_vote):
    act = seeded_vote["act"]
    ws = FakeWebSocket()
    await monitor_manager.connect(str(act.id), ws)

    await broadcast_closed(db_session, act.id)

    closed = [m for m in ws.sent if m.get("type") == "closed"]
    assert closed, f"expected a closed broadcast, got {ws.sent}"
    assert closed[-1]["submission_count"] == 2
