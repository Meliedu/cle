"""Task 9: checkpoints.py router — teacher draft/generate/CRUD (DRAFT-only).

Decision 3: P1 only ever writes ``draft``/``teacher_editing`` checkpoints and
exposes NO publish/approve/schedule/close routes (those ship P3). The final
``final_comments`` card is fixed (not removable); removing a ``review_point``
requires a reason. Card edit/remove/add is only allowed while the checkpoint is
in an editable draft state.

Adapted to the real conftest fixtures (``async_client`` = ``logged_in_user``
instructor; ``db_session``). Local ``owned_course`` / ``seed_meeting`` /
``draft_checkpoint_with_cards`` fixtures mirror ``test_setup_api.py``.
"""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.main import app
from app.models import Course, Enrollment, User
from app.models.checkpoint import Checkpoint, CheckpointCard
from app.models.curriculum import CourseMeeting
from app.models.task import Task


@pytest_asyncio.fixture
async def owned_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="Checkpoint Test", language="english",
        instructor_id=logged_in_user.id, enroll_code="CHKP0001",
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


@pytest_asyncio.fixture
async def draft_checkpoint_with_cards(
    db_session: AsyncSession, owned_course: Course, seed_meeting: CourseMeeting
):
    cp = Checkpoint(
        course_id=owned_course.id, meeting_id=seed_meeting.id,
        kind="session", title="Session 1 checkpoint", status="draft",
    )
    db_session.add(cp)
    await db_session.flush()
    db_session.add(CheckpointCard(
        checkpoint_id=cp.id, position=0, kind="review_point",
        prompt="How confident are you ordering food?",
    ))
    db_session.add(CheckpointCard(
        checkpoint_id=cp.id, position=1, kind="review_point",
        prompt="Rate your grasp of tone sandhi.",
    ))
    final = CheckpointCard(
        checkpoint_id=cp.id, position=2, kind="final_comments",
        prompt="Any final comments or questions about today's session?",
    )
    db_session.add(final)
    await db_session.commit()
    await db_session.refresh(cp)
    await db_session.refresh(final)
    return cp, final


# ----- generate -----

@pytest.mark.asyncio
async def test_generate_enqueues(
    async_client: AsyncClient, db_session: AsyncSession,
    owned_course: Course, seed_meeting: CourseMeeting,
):
    r = await async_client.post(
        f"/api/courses/{owned_course.id}/checkpoints/generate",
        json={"meeting_id": str(seed_meeting.id)},
    )
    assert r.status_code == 202
    tasks = (
        await db_session.execute(
            select(Task).where(Task.task_type == "generate_checkpoints")
        )
    ).scalars().all()
    assert len(tasks) == 1
    assert tasks[0].payload["course_id"] == str(owned_course.id)
    assert tasks[0].payload["meeting_id"] == str(seed_meeting.id)
    assert tasks[0].status == "pending"


@pytest.mark.asyncio
async def test_generate_non_owner_gets_404(
    async_client: AsyncClient, db_session: AsyncSession
):
    other = User(
        better_auth_id="chkp_other_instr", email="chkpother@ust.hk",
        full_name="Other", role="instructor",
    )
    db_session.add(other)
    await db_session.flush()
    course = Course(
        name="Foreign", language="english",
        instructor_id=other.id, enroll_code="CHKPFOR1",
    )
    db_session.add(course)
    await db_session.commit()
    r = await async_client.post(
        f"/api/courses/{course.id}/checkpoints/generate", json={}
    )
    assert r.status_code == 404


# ----- list / get -----

@pytest.mark.asyncio
async def test_list_returns_drafts(
    async_client: AsyncClient, owned_course: Course, draft_checkpoint_with_cards
):
    cp, _ = draft_checkpoint_with_cards
    r = await async_client.get(f"/api/courses/{owned_course.id}/checkpoints")
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == str(cp.id)
    assert data[0]["status"] == "draft"


@pytest.mark.asyncio
async def test_get_returns_checkpoint_with_cards(
    async_client: AsyncClient, draft_checkpoint_with_cards
):
    cp, _ = draft_checkpoint_with_cards
    r = await async_client.get(f"/api/checkpoints/{cp.id}")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["id"] == str(cp.id)
    kinds = sorted(c["kind"] for c in data["cards"])
    assert kinds.count("final_comments") == 1
    assert kinds.count("review_point") == 2


# ----- edit card -----

@pytest.mark.asyncio
async def test_edit_review_card_prompt_bumps_state(
    async_client: AsyncClient, db_session: AsyncSession, draft_checkpoint_with_cards
):
    cp, _ = draft_checkpoint_with_cards
    detail = (await async_client.get(f"/api/checkpoints/{cp.id}")).json()["data"]
    rp = next(c for c in detail["cards"] if c["kind"] == "review_point")
    r = await async_client.patch(
        f"/api/checkpoints/{cp.id}/cards/{rp['id']}", json={"prompt": "Edited?"}
    )
    assert r.status_code == 200
    assert r.json()["data"]["prompt"] == "Edited?"
    # editing a draft bumps it to teacher_editing (Decision 3)
    await db_session.refresh(cp)
    assert cp.status == "teacher_editing"


# ----- remove card -----

@pytest.mark.asyncio
async def test_remove_review_card_requires_reason(
    async_client: AsyncClient, draft_checkpoint_with_cards
):
    cp, _ = draft_checkpoint_with_cards
    detail = (await async_client.get(f"/api/checkpoints/{cp.id}")).json()["data"]
    rp = next(c for c in detail["cards"] if c["kind"] == "review_point")
    # remove with no reason -> rejected
    r = await async_client.patch(
        f"/api/checkpoints/{cp.id}/cards/{rp['id']}", json={"removed": True}
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "REMOVE_REASON_REQUIRED"


@pytest.mark.asyncio
async def test_remove_review_card_soft_removes(
    async_client: AsyncClient, db_session: AsyncSession, draft_checkpoint_with_cards
):
    cp, _ = draft_checkpoint_with_cards
    detail = (await async_client.get(f"/api/checkpoints/{cp.id}")).json()["data"]
    rp = next(c for c in detail["cards"] if c["kind"] == "review_point")
    r = await async_client.patch(
        f"/api/checkpoints/{cp.id}/cards/{rp['id']}",
        json={"removed": True, "removed_reason": "duplicate"},
    )
    assert r.status_code == 200
    card = await db_session.get(CheckpointCard, uuid.UUID(rp["id"]))
    await db_session.refresh(card)
    assert card.removed is True
    assert card.removed_reason == "duplicate"
    assert card.deleted_at is not None


@pytest.mark.asyncio
async def test_cannot_remove_final_card(
    async_client: AsyncClient, draft_checkpoint_with_cards
):
    cp, final_card = draft_checkpoint_with_cards
    r = await async_client.patch(
        f"/api/checkpoints/{cp.id}/cards/{final_card.id}",
        json={"removed": True, "removed_reason": "not_needed"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "FINAL_CARD_FIXED"


# ----- add card -----

@pytest.mark.asyncio
async def test_add_review_card(
    async_client: AsyncClient, draft_checkpoint_with_cards
):
    cp, _ = draft_checkpoint_with_cards
    r = await async_client.post(
        f"/api/checkpoints/{cp.id}/cards",
        json={"prompt": "Rate your listening comprehension."},
    )
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["kind"] == "review_point"
    assert data["prompt"] == "Rate your listening comprehension."


@pytest.mark.asyncio
async def test_cannot_add_second_final_card(
    async_client: AsyncClient, draft_checkpoint_with_cards
):
    cp, _ = draft_checkpoint_with_cards
    # The router only creates review_point cards; a client can't request a
    # second final_comments via this endpoint. But if the unique index is the
    # real guard, adding is still fine (it's a review_point). Assert we can't
    # create a duplicate final by any exposed route: there is no such route.
    r = await async_client.post(
        f"/api/checkpoints/{cp.id}/cards",
        json={"prompt": "another", "kind": "final_comments"},
    )
    # kind is server-forced to review_point (or rejected). Either way, no second
    # final_comments card is ever created.
    assert r.status_code in (201, 422)
    detail = (await async_client.get(f"/api/checkpoints/{cp.id}")).json()["data"]
    finals = [c for c in detail["cards"] if c["kind"] == "final_comments"]
    assert len(finals) == 1


# ----- DRAFT-only guard -----

@pytest.mark.asyncio
async def test_edit_rejected_when_not_editable(
    async_client: AsyncClient, db_session: AsyncSession, draft_checkpoint_with_cards
):
    cp, _ = draft_checkpoint_with_cards
    cp.status = "approved"  # a P3 state; P1 must refuse edits here
    await db_session.commit()
    detail_cp = await db_session.get(Checkpoint, cp.id)
    card = (
        await db_session.execute(
            select(CheckpointCard).where(
                CheckpointCard.checkpoint_id == cp.id,
                CheckpointCard.kind == "review_point",
            )
        )
    ).scalars().first()
    r = await async_client.patch(
        f"/api/checkpoints/{cp.id}/cards/{card.id}", json={"prompt": "nope"}
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "REVIEW_REQUIRED"


# ----- ownership / delete -----

@pytest.mark.asyncio
async def test_get_checkpoint_non_owner_404(
    async_client: AsyncClient, db_session: AsyncSession
):
    other = User(
        better_auth_id="chkp_other_2", email="chkpother2@ust.hk",
        full_name="Other", role="instructor",
    )
    db_session.add(other)
    await db_session.flush()
    course = Course(
        name="Foreign2", language="english",
        instructor_id=other.id, enroll_code="CHKPFOR2",
    )
    db_session.add(course)
    await db_session.flush()
    cp = Checkpoint(course_id=course.id, kind="session", title="x", status="draft")
    db_session.add(cp)
    await db_session.commit()
    r = await async_client.get(f"/api/checkpoints/{cp.id}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_checkpoint_soft_deletes(
    async_client: AsyncClient, db_session: AsyncSession, draft_checkpoint_with_cards
):
    cp, _ = draft_checkpoint_with_cards
    r = await async_client.delete(f"/api/checkpoints/{cp.id}")
    assert r.status_code == 200
    await db_session.refresh(cp)
    assert cp.deleted_at is not None


# ----- publish path: approve / schedule / publish / close (P3 T5) -----

def _review_actions(cp: Checkpoint) -> list[dict]:
    return list((cp.generation_meta or {}).get("review_actions", []))


@pytest.mark.asyncio
async def test_approve_happy_path(
    async_client: AsyncClient, db_session: AsyncSession, draft_checkpoint_with_cards
):
    cp, _ = draft_checkpoint_with_cards
    r = await async_client.post(f"/api/checkpoints/{cp.id}/approve")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "approved"
    await db_session.refresh(cp)
    assert cp.status == "approved"
    actions = _review_actions(cp)
    assert len(actions) == 1
    assert actions[0]["action"] == "approve"
    assert actions[0]["to"] == "approved"


@pytest.mark.asyncio
async def test_approve_from_teacher_editing(
    async_client: AsyncClient, db_session: AsyncSession, draft_checkpoint_with_cards
):
    cp, _ = draft_checkpoint_with_cards
    cp.status = "teacher_editing"
    await db_session.commit()
    r = await async_client.post(f"/api/checkpoints/{cp.id}/approve")
    assert r.status_code == 200, r.text
    await db_session.refresh(cp)
    assert cp.status == "approved"


@pytest.mark.asyncio
async def test_approve_requires_review_point_card(
    async_client: AsyncClient, db_session: AsyncSession,
    owned_course: Course, seed_meeting: CourseMeeting,
):
    # Checkpoint with only the final_comments card — no review_point → refused.
    cp = Checkpoint(
        course_id=owned_course.id, meeting_id=seed_meeting.id,
        kind="session", title="No review points", status="draft",
    )
    db_session.add(cp)
    await db_session.flush()
    db_session.add(CheckpointCard(
        checkpoint_id=cp.id, position=0, kind="final_comments",
        prompt="Any final comments?",
    ))
    await db_session.commit()
    r = await async_client.post(f"/api/checkpoints/{cp.id}/approve")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "REVIEW_REQUIRED"


@pytest.mark.asyncio
async def test_approve_requires_final_card(
    async_client: AsyncClient, db_session: AsyncSession,
    owned_course: Course, seed_meeting: CourseMeeting,
):
    # Checkpoint with a review_point but no final_comments card → refused.
    cp = Checkpoint(
        course_id=owned_course.id, meeting_id=seed_meeting.id,
        kind="session", title="No final card", status="draft",
    )
    db_session.add(cp)
    await db_session.flush()
    db_session.add(CheckpointCard(
        checkpoint_id=cp.id, position=0, kind="review_point",
        prompt="Rate your grasp.",
    ))
    await db_session.commit()
    r = await async_client.post(f"/api/checkpoints/{cp.id}/approve")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "REVIEW_REQUIRED"


@pytest.mark.asyncio
async def test_schedule_happy_path(
    async_client: AsyncClient, db_session: AsyncSession, draft_checkpoint_with_cards
):
    cp, _ = draft_checkpoint_with_cards
    cp.status = "approved"
    await db_session.commit()
    release = datetime.now(timezone.utc).replace(microsecond=0)
    r = await async_client.post(
        f"/api/checkpoints/{cp.id}/schedule",
        json={"release_at": release.isoformat(), "close_rule": "at_close_at"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "scheduled"
    await db_session.refresh(cp)
    assert cp.status == "scheduled"
    assert cp.release_at is not None
    assert cp.close_rule == "at_close_at"


@pytest.mark.asyncio
async def test_schedule_requires_release_and_close_rule(
    async_client: AsyncClient, db_session: AsyncSession, draft_checkpoint_with_cards
):
    cp, _ = draft_checkpoint_with_cards
    cp.status = "approved"
    await db_session.commit()
    r = await async_client.post(f"/api/checkpoints/{cp.id}/schedule", json={})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "REVIEW_REQUIRED"


@pytest.mark.asyncio
async def test_schedule_illegal_from_draft(
    async_client: AsyncClient, draft_checkpoint_with_cards
):
    cp, _ = draft_checkpoint_with_cards  # still draft
    release = datetime.now(timezone.utc).isoformat()
    r = await async_client.post(
        f"/api/checkpoints/{cp.id}/schedule",
        json={"release_at": release, "close_rule": "manual"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "REVIEW_REQUIRED"


@pytest.mark.asyncio
async def test_publish_happy_path_from_approved(
    async_client: AsyncClient, db_session: AsyncSession, draft_checkpoint_with_cards
):
    cp, _ = draft_checkpoint_with_cards  # has meeting_id set
    cp.status = "approved"
    await db_session.commit()
    release = datetime.now(timezone.utc).isoformat()
    r = await async_client.post(
        f"/api/checkpoints/{cp.id}/publish",
        json={"release_at": release, "close_rule": "manual"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "published"
    await db_session.refresh(cp)
    assert cp.status == "published"
    actions = _review_actions(cp)
    assert any(a["action"] == "publish" for a in actions)


@pytest.mark.asyncio
async def test_publish_happy_path_from_scheduled(
    async_client: AsyncClient, db_session: AsyncSession, draft_checkpoint_with_cards
):
    cp, _ = draft_checkpoint_with_cards
    cp.status = "scheduled"
    cp.release_at = datetime.now(timezone.utc)
    cp.close_rule = "manual"
    await db_session.commit()
    r = await async_client.post(f"/api/checkpoints/{cp.id}/publish")
    assert r.status_code == 200, r.text
    await db_session.refresh(cp)
    assert cp.status == "published"


@pytest.mark.asyncio
async def test_publish_gate_missing_release_timing(
    async_client: AsyncClient, db_session: AsyncSession, draft_checkpoint_with_cards
):
    cp, _ = draft_checkpoint_with_cards
    cp.status = "approved"  # meeting_id set, but no release_at / close_rule
    await db_session.commit()
    r = await async_client.post(f"/api/checkpoints/{cp.id}/publish")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "REVIEW_REQUIRED"


@pytest.mark.asyncio
async def test_publish_gate_requires_session_relation(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course
):
    cp = Checkpoint(
        course_id=owned_course.id, meeting_id=None,
        kind="session", title="Sessionless", status="approved",
        release_at=datetime.now(timezone.utc), close_rule="manual",
    )
    db_session.add(cp)
    await db_session.commit()
    r = await async_client.post(f"/api/checkpoints/{cp.id}/publish")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "REVIEW_REQUIRED"


@pytest.mark.asyncio
async def test_close_happy_path_from_published(
    async_client: AsyncClient, db_session: AsyncSession, draft_checkpoint_with_cards
):
    cp, _ = draft_checkpoint_with_cards
    cp.status = "published"
    await db_session.commit()
    r = await async_client.post(f"/api/checkpoints/{cp.id}/close")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "closed"
    await db_session.refresh(cp)
    assert cp.status == "closed"
    actions = _review_actions(cp)
    assert any(a["action"] == "close" for a in actions)


@pytest.mark.asyncio
async def test_close_happy_path_from_live(
    async_client: AsyncClient, db_session: AsyncSession, draft_checkpoint_with_cards
):
    cp, _ = draft_checkpoint_with_cards
    cp.status = "live"
    await db_session.commit()
    r = await async_client.post(f"/api/checkpoints/{cp.id}/close")
    assert r.status_code == 200, r.text
    await db_session.refresh(cp)
    assert cp.status == "closed"


@pytest.mark.asyncio
async def test_close_illegal_from_draft(
    async_client: AsyncClient, draft_checkpoint_with_cards
):
    cp, _ = draft_checkpoint_with_cards  # draft
    r = await async_client.post(f"/api/checkpoints/{cp.id}/close")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "REVIEW_REQUIRED"


@pytest.mark.asyncio
async def test_publish_path_non_owner_404(
    async_client: AsyncClient, db_session: AsyncSession
):
    other = User(
        better_auth_id="chkp_other_pub", email="chkpotherpub@ust.hk",
        full_name="Other", role="instructor",
    )
    db_session.add(other)
    await db_session.flush()
    course = Course(
        name="ForeignPub", language="english",
        instructor_id=other.id, enroll_code="CHKPPUB1",
    )
    db_session.add(course)
    await db_session.flush()
    cp = Checkpoint(
        course_id=course.id, kind="session", title="x", status="draft",
    )
    db_session.add(cp)
    await db_session.commit()
    r = await async_client.post(f"/api/checkpoints/{cp.id}/approve")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_publish_path_student_forbidden(
    db_session: AsyncSession, draft_checkpoint_with_cards
):
    cp, _ = draft_checkpoint_with_cards
    student = User(
        better_auth_id="chkp_student_pub", email="chkpstudentpub@connect.ust.hk",
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
            r = await ac.post(f"/api/checkpoints/{cp.id}/approve")
            assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_student_forbidden(db_session: AsyncSession, owned_course: Course):
    student = User(
        better_auth_id="chkp_student_01", email="chkpstudent@connect.ust.hk",
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
            r = await ac.get(f"/api/courses/{owned_course.id}/checkpoints")
            assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()
