"""P3 T6: teacher checkpoint results + history endpoints.

``GET /checkpoints/{id}/results`` returns per-card response counts + a
confidence distribution (histogram of −2..+2 for ``review_point`` cards) plus a
derived "missed" count (active-enrolled students with no response — meaningful
once the checkpoint is closed). ``GET /courses/{id}/checkpoints?history=1``
lists only ``closed``/``archived`` checkpoints; without the filter the P1
behaviour (all non-deleted) is preserved.

Owner-guarded course-scoped reads (Decision 2): a student gets 403, a
non-owner instructor gets 404. Uses the real conftest fixtures.
"""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.main import app
from app.models import Course, Enrollment, User
from app.models.checkpoint import Checkpoint, CheckpointCard, CheckpointResponse
from app.models.curriculum import CourseMeeting


@pytest_asyncio.fixture
async def owned_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="Results Test", language="english",
        instructor_id=logged_in_user.id, enroll_code="RSLT0001",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor")
    )
    await db_session.commit()
    await db_session.refresh(course)
    return course


@pytest_asyncio.fixture
async def seed_meeting(db_session: AsyncSession, owned_course: Course) -> CourseMeeting:
    meeting = CourseMeeting(
        course_id=owned_course.id, meeting_index=1, title="Greetings",
        scheduled_at=datetime.now(timezone.utc),
    )
    db_session.add(meeting)
    await db_session.commit()
    await db_session.refresh(meeting)
    return meeting


async def _make_student(db: AsyncSession, course: Course, suffix: str, *, status="active") -> User:
    student = User(
        better_auth_id=f"rslt_student_{suffix}",
        email=f"rslt_student_{suffix}@connect.ust.hk",
        full_name=f"Student {suffix}", role="student",
    )
    db.add(student)
    await db.flush()
    db.add(
        Enrollment(course_id=course.id, user_id=student.id, role="student", status=status)
    )
    return student


@pytest_asyncio.fixture
async def closed_checkpoint_with_responses(
    db_session: AsyncSession, owned_course: Course, seed_meeting: CourseMeeting
):
    """A closed checkpoint: 2 review cards + final card, 3 active students, only
    2 of them responded (student C never answered → 1 missed)."""
    cp = Checkpoint(
        course_id=owned_course.id, meeting_id=seed_meeting.id,
        kind="session", title="Closed session checkpoint", status="closed",
    )
    db_session.add(cp)
    await db_session.flush()

    rp1 = CheckpointCard(
        checkpoint_id=cp.id, position=0, kind="review_point",
        prompt="How confident ordering food?",
    )
    rp2 = CheckpointCard(
        checkpoint_id=cp.id, position=1, kind="review_point",
        prompt="Rate your grasp of tone sandhi.",
    )
    final = CheckpointCard(
        checkpoint_id=cp.id, position=2, kind="final_comments",
        prompt="Any final comments?",
    )
    db_session.add_all([rp1, rp2, final])
    await db_session.flush()

    student_a = await _make_student(db_session, owned_course, "a")
    student_b = await _make_student(db_session, owned_course, "b")
    await _make_student(db_session, owned_course, "c")  # never responds
    await db_session.flush()

    # Student A: rp1=+2, rp2=+1, final text
    db_session.add_all([
        CheckpointResponse(
            checkpoint_id=cp.id, card_id=rp1.id, user_id=student_a.id,
            confidence=2, status="on_time",
        ),
        CheckpointResponse(
            checkpoint_id=cp.id, card_id=rp2.id, user_id=student_a.id,
            confidence=1, status="on_time",
        ),
        CheckpointResponse(
            checkpoint_id=cp.id, card_id=final.id, user_id=student_a.id,
            text_response="All good!", status="on_time",
        ),
        # Student B: rp1=+2 (same bucket as A), rp2=-2
        CheckpointResponse(
            checkpoint_id=cp.id, card_id=rp1.id, user_id=student_b.id,
            confidence=2, status="late",
        ),
        CheckpointResponse(
            checkpoint_id=cp.id, card_id=rp2.id, user_id=student_b.id,
            confidence=-2, status="on_time",
        ),
    ])
    await db_session.commit()
    await db_session.refresh(cp)
    return cp, rp1, rp2, final


# ----- results -----

@pytest.mark.asyncio
async def test_results_per_card_counts_and_confidence_distribution(
    async_client: AsyncClient, closed_checkpoint_with_responses
):
    cp, rp1, rp2, final = closed_checkpoint_with_responses
    r = await async_client.get(f"/api/checkpoints/{cp.id}/results")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["checkpoint_id"] == str(cp.id)
    assert data["status"] == "closed"

    by_card = {c["card_id"]: c for c in data["cards"]}
    assert set(by_card) == {str(rp1.id), str(rp2.id), str(final.id)}

    # rp1: two responses, both +2
    c1 = by_card[str(rp1.id)]
    assert c1["response_count"] == 2
    assert c1["confidence_distribution"] == {"-2": 0, "-1": 0, "0": 0, "1": 0, "2": 2}

    # rp2: two responses, +1 and -2
    c2 = by_card[str(rp2.id)]
    assert c2["response_count"] == 2
    assert c2["confidence_distribution"] == {"-2": 1, "-1": 0, "0": 0, "1": 1, "2": 0}

    # final: one text response, no confidence histogram
    cf = by_card[str(final.id)]
    assert cf["response_count"] == 1
    assert cf["confidence_distribution"] == {}
    assert cf["text_response_count"] == 1


@pytest.mark.asyncio
async def test_results_missed_count(
    async_client: AsyncClient, closed_checkpoint_with_responses
):
    cp, *_ = closed_checkpoint_with_responses
    r = await async_client.get(f"/api/checkpoints/{cp.id}/results")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    # 3 active students, 2 responded → 1 missed
    assert data["active_student_count"] == 3
    assert data["responded_count"] == 2
    assert data["missed_count"] == 1


@pytest.mark.asyncio
async def test_results_ignores_inactive_students(
    async_client: AsyncClient, db_session: AsyncSession, closed_checkpoint_with_responses
):
    cp, *_ = closed_checkpoint_with_responses
    course = await db_session.get(Course, cp.course_id)
    # A pending (not active) student should not inflate the roster denominator.
    await _make_student(db_session, course, "pending", status="pending")
    await db_session.commit()
    r = await async_client.get(f"/api/checkpoints/{cp.id}/results")
    data = r.json()["data"]
    assert data["active_student_count"] == 3
    assert data["missed_count"] == 1


@pytest.mark.asyncio
async def test_results_non_owner_404(
    async_client: AsyncClient, db_session: AsyncSession
):
    other = User(
        better_auth_id="rslt_other_instr", email="rsltother@ust.hk",
        full_name="Other", role="instructor",
    )
    db_session.add(other)
    await db_session.flush()
    course = Course(
        name="Foreign", language="english",
        instructor_id=other.id, enroll_code="RSLTFOR1",
    )
    db_session.add(course)
    await db_session.flush()
    cp = Checkpoint(course_id=course.id, kind="session", title="x", status="closed")
    db_session.add(cp)
    await db_session.commit()
    r = await async_client.get(f"/api/checkpoints/{cp.id}/results")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_results_student_forbidden(
    db_session: AsyncSession, closed_checkpoint_with_responses
):
    cp, *_ = closed_checkpoint_with_responses
    student = User(
        better_auth_id="rslt_student_forbid",
        email="rsltforbid@connect.ust.hk",
        full_name="Student", role="student",
    )
    db_session.add(student)
    await db_session.commit()

    async def override_db():
        yield db_session

    async def override_user():
        return student

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer x"},
        ) as ac:
            r = await ac.get(f"/api/checkpoints/{cp.id}/results")
            assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


# ----- history -----

@pytest_asyncio.fixture
async def mixed_status_checkpoints(
    db_session: AsyncSession, owned_course: Course
) -> dict[str, Checkpoint]:
    out: dict[str, Checkpoint] = {}
    for st in ("draft", "published", "closed", "archived"):
        cp = Checkpoint(
            course_id=owned_course.id, kind="session",
            title=f"{st} checkpoint", status=st,
        )
        db_session.add(cp)
        await db_session.flush()
        out[st] = cp
    await db_session.commit()
    return out


@pytest.mark.asyncio
async def test_history_returns_only_closed_and_archived(
    async_client: AsyncClient, owned_course: Course, mixed_status_checkpoints
):
    r = await async_client.get(
        f"/api/courses/{owned_course.id}/checkpoints?history=1"
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    statuses = sorted(c["status"] for c in data)
    assert statuses == ["archived", "closed"]


@pytest.mark.asyncio
async def test_list_without_history_preserves_p1_behavior(
    async_client: AsyncClient, owned_course: Course, mixed_status_checkpoints
):
    r = await async_client.get(f"/api/courses/{owned_course.id}/checkpoints")
    assert r.status_code == 200
    data = r.json()["data"]
    # all four non-deleted checkpoints, unchanged from P1
    assert len(data) == 4


@pytest.mark.asyncio
async def test_history_non_owner_404(
    async_client: AsyncClient, db_session: AsyncSession
):
    other = User(
        better_auth_id="rslt_hist_other", email="rslthist@ust.hk",
        full_name="Other", role="instructor",
    )
    db_session.add(other)
    await db_session.flush()
    course = Course(
        name="Foreign", language="english",
        instructor_id=other.id, enroll_code="RSLTHIS1",
    )
    db_session.add(course)
    await db_session.commit()
    r = await async_client.get(f"/api/courses/{course.id}/checkpoints?history=1")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_history_student_forbidden(
    db_session: AsyncSession, owned_course: Course
):
    student = User(
        better_auth_id="rslt_hist_student",
        email="rslthiststudent@connect.ust.hk",
        full_name="Student", role="student",
    )
    db_session.add(student)
    await db_session.commit()

    async def override_db():
        yield db_session

    async def override_user():
        return student

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer x"},
        ) as ac:
            r = await ac.get(
                f"/api/courses/{owned_course.id}/checkpoints?history=1"
            )
            assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()
