"""P3 T7 — student checkpoint intro + response submission (evidence seam).

Covers the student-facing half of the checkpoint loop:

* ``GET /checkpoints/{id}/intro`` — enrollment-scoped; returns the ordered live
  (non-removed) cards only while the checkpoint is ``published``/``live`` AND
  inside its release..close window, else a typed ``QR_NOT_AVAILABLE`` 409.
* ``POST /checkpoints/{id}/responses`` — upserts one row per ``(card_id,
  user_id)`` (a resubmit updates in place), derives ``on_time``/``late`` from
  ``close_at``, enforces confidence-on-review / text-on-final, and rejects a
  card that belongs to a different checkpoint.

The evidence seam mirrors ``quizzes.py`` exactly: after the response is
committed a single ``LearningEvent`` (``stage='during_class'``,
``source_kind='checkpoint_card'``) is written and — for ``review_point`` cards
only — an ``update_concept_mastery`` Task is enqueued with
``outcome=(confidence+2)/4``. The enqueue is best-effort: a failure there must
never lose the already-committed response.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.main import app
from app.models import Concept, ConceptTag, Course, Enrollment, User
from app.models.checkpoint import Checkpoint, CheckpointCard, CheckpointResponse
from app.models.evidence import LearningEvent
from app.models.task import Task


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def owned_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="Checkpoint Responses", language="english",
        instructor_id=logged_in_user.id, enroll_code="CHKR0001",
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
async def enrolled_student(db_session: AsyncSession, owned_course: Course) -> User:
    student = User(
        better_auth_id="chkr_student_01", email="chkrstudent@connect.ust.hk",
        full_name="Chk Student", role="student",
    )
    db_session.add(student)
    await db_session.flush()
    db_session.add(
        Enrollment(
            course_id=owned_course.id, user_id=student.id,
            role="student", status="active",
        )
    )
    await db_session.commit()
    await db_session.refresh(student)
    return student


async def _make_checkpoint(
    db_session: AsyncSession,
    course: Course,
    *,
    status: str = "published",
    release_at: datetime | None = None,
    close_at: datetime | None = None,
    tag_review_point: bool = False,
) -> dict:
    """Build a checkpoint with two review points + one final card.

    Returns ``{cp, review, review2, final, concept}`` (concept only when
    ``tag_review_point``).
    """
    now = _utcnow()
    cp = Checkpoint(
        course_id=course.id, kind="session", title="Session checkpoint",
        status=status,
        release_at=release_at if release_at is not None else now - timedelta(hours=1),
        close_at=close_at,
        close_rule="manual",
    )
    db_session.add(cp)
    await db_session.flush()
    review = CheckpointCard(
        checkpoint_id=cp.id, position=0, kind="review_point",
        prompt="How confident are you ordering food?",
    )
    review2 = CheckpointCard(
        checkpoint_id=cp.id, position=1, kind="review_point",
        prompt="Rate your grasp of tone sandhi.",
    )
    final = CheckpointCard(
        checkpoint_id=cp.id, position=2, kind="final_comments",
        prompt="Any final comments?",
    )
    db_session.add_all([review, review2, final])
    await db_session.flush()

    concept = None
    if tag_review_point:
        concept = Concept(
            course_id=course.id, name="Ordering food",
            status="approved", instructor_curated=True,
        )
        db_session.add(concept)
        await db_session.flush()
        db_session.add(
            ConceptTag(
                concept_id=concept.id, target_kind="checkpoint_card",
                target_id=review.id, weight=Decimal("1.00"),
            )
        )
    await db_session.commit()
    await db_session.refresh(cp)
    for c in (review, review2, final):
        await db_session.refresh(c)
    return {
        "cp": cp, "review": review, "review2": review2,
        "final": final, "concept": concept,
    }


def _student_client(db_session: AsyncSession, student: User) -> AsyncClient:
    async def override_db():
        yield db_session

    async def override_user():
        return student

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    return AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
        headers={"Authorization": "Bearer x"},
    )


# ----- intro -----

@pytest.mark.asyncio
async def test_intro_returns_cards_when_live_in_window(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    made = await _make_checkpoint(db_session, owned_course, status="published")
    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.get(f"/api/checkpoints/{made['cp'].id}/intro")
    app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["checkpoint_id"] == str(made["cp"].id)
    positions = [c["position"] for c in data["cards"]]
    assert positions == sorted(positions)
    assert len(data["cards"]) == 3


@pytest.mark.asyncio
async def test_intro_qr_not_available_when_draft(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    made = await _make_checkpoint(db_session, owned_course, status="draft")
    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.get(f"/api/checkpoints/{made['cp'].id}/intro")
    app.dependency_overrides.clear()
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "QR_NOT_AVAILABLE"


@pytest.mark.asyncio
async def test_intro_qr_not_available_when_closed(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    made = await _make_checkpoint(db_session, owned_course, status="closed")
    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.get(f"/api/checkpoints/{made['cp'].id}/intro")
    app.dependency_overrides.clear()
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "QR_NOT_AVAILABLE"


@pytest.mark.asyncio
async def test_intro_qr_not_available_out_of_window(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    # published but release is still in the future → not yet open.
    made = await _make_checkpoint(
        db_session, owned_course, status="published",
        release_at=_utcnow() + timedelta(hours=1),
    )
    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.get(f"/api/checkpoints/{made['cp'].id}/intro")
    app.dependency_overrides.clear()
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "QR_NOT_AVAILABLE"


@pytest.mark.asyncio
async def test_intro_non_enrolled_student_rejected(
    db_session: AsyncSession, owned_course: Course
):
    made = await _make_checkpoint(db_session, owned_course, status="published")
    outsider = User(
        better_auth_id="chkr_outsider", email="outsider@connect.ust.hk",
        full_name="Outsider", role="student",
    )
    db_session.add(outsider)
    await db_session.commit()
    async with _student_client(db_session, outsider) as ac:
        r = await ac.get(f"/api/checkpoints/{made['cp'].id}/intro")
    app.dependency_overrides.clear()
    assert r.status_code == 403


# ----- submit -----

@pytest.mark.asyncio
async def test_submit_review_point_upserts_in_place(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    made = await _make_checkpoint(db_session, owned_course, status="published")
    async with _student_client(db_session, enrolled_student) as ac:
        r1 = await ac.post(
            f"/api/checkpoints/{made['cp'].id}/responses",
            json={"card_id": str(made["review"].id), "confidence": 1},
        )
        assert r1.status_code in (200, 201), r1.text
        # resubmit with a different confidence — must update in place.
        r2 = await ac.post(
            f"/api/checkpoints/{made['cp'].id}/responses",
            json={"card_id": str(made["review"].id), "confidence": -2},
        )
        assert r2.status_code in (200, 201), r2.text
    app.dependency_overrides.clear()

    rows = (
        await db_session.execute(
            select(CheckpointResponse).where(
                CheckpointResponse.card_id == made["review"].id,
                CheckpointResponse.user_id == enrolled_student.id,
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].confidence == -2
    assert rows[0].status == "on_time"


@pytest.mark.asyncio
async def test_submit_final_comments_text(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    made = await _make_checkpoint(db_session, owned_course, status="published")
    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.post(
            f"/api/checkpoints/{made['cp'].id}/responses",
            json={"card_id": str(made["final"].id), "text_response": "Great session!"},
        )
    app.dependency_overrides.clear()
    assert r.status_code in (200, 201), r.text
    row = (
        await db_session.execute(
            select(CheckpointResponse).where(
                CheckpointResponse.card_id == made["final"].id
            )
        )
    ).scalar_one()
    assert row.text_response == "Great session!"
    assert row.confidence is None


@pytest.mark.asyncio
async def test_submit_confidence_only_on_review_point(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    made = await _make_checkpoint(db_session, owned_course, status="published")
    async with _student_client(db_session, enrolled_student) as ac:
        # text on a review_point card → rejected
        r1 = await ac.post(
            f"/api/checkpoints/{made['cp'].id}/responses",
            json={"card_id": str(made["review"].id), "text_response": "nope"},
        )
        # confidence on a final_comments card → rejected
        r2 = await ac.post(
            f"/api/checkpoints/{made['cp'].id}/responses",
            json={"card_id": str(made["final"].id), "confidence": 1},
        )
    app.dependency_overrides.clear()
    assert r1.status_code == 422
    assert r2.status_code == 422


@pytest.mark.asyncio
async def test_submit_cross_checkpoint_card_rejected(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    made = await _make_checkpoint(db_session, owned_course, status="published")
    other = await _make_checkpoint(db_session, owned_course, status="published")
    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.post(
            f"/api/checkpoints/{made['cp'].id}/responses",
            json={"card_id": str(other["review"].id), "confidence": 1},
        )
    app.dependency_overrides.clear()
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_submit_writes_learning_event(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    made = await _make_checkpoint(db_session, owned_course, status="published")
    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.post(
            f"/api/checkpoints/{made['cp'].id}/responses",
            json={"card_id": str(made["review"].id), "confidence": 2},
        )
        assert r.status_code in (200, 201), r.text
    app.dependency_overrides.clear()

    events = (
        await db_session.execute(
            select(LearningEvent).where(
                LearningEvent.course_id == owned_course.id
            )
        )
    ).scalars().all()
    assert len(events) == 1
    ev = events[0]
    assert ev.source_kind == "checkpoint_card"
    assert ev.source_id == made["review"].id
    assert ev.stage == "during_class"
    assert ev.user_id == enrolled_student.id


@pytest.mark.asyncio
async def test_submit_enqueues_mastery_for_tagged_review_point(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    made = await _make_checkpoint(
        db_session, owned_course, status="published", tag_review_point=True
    )
    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.post(
            f"/api/checkpoints/{made['cp'].id}/responses",
            json={"card_id": str(made["review"].id), "confidence": 1},
        )
        assert r.status_code in (200, 201), r.text
    app.dependency_overrides.clear()

    tasks = (
        await db_session.execute(
            select(Task).where(Task.task_type == "update_concept_mastery")
        )
    ).scalars().all()
    assert len(tasks) == 1
    payload = tasks[0].payload
    assert payload["target_kind"] == "checkpoint_card"
    assert payload["target_id"] == str(made["review"].id)
    assert payload["attempt_kind"] == "checkpoint"
    assert payload["user_id"] == str(enrolled_student.id)
    assert payload["course_id"] == str(owned_course.id)
    # confidence 1 on the −2..+2 scale → outcome (1+2)/4 = 0.75
    assert float(payload["outcome"]) == 0.75


@pytest.mark.asyncio
async def test_submit_final_does_not_enqueue_mastery(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    made = await _make_checkpoint(db_session, owned_course, status="published")
    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.post(
            f"/api/checkpoints/{made['cp'].id}/responses",
            json={"card_id": str(made["final"].id), "text_response": "thanks"},
        )
        assert r.status_code in (200, 201), r.text
    app.dependency_overrides.clear()

    tasks = (
        await db_session.execute(
            select(Task).where(Task.task_type == "update_concept_mastery")
        )
    ).scalars().all()
    assert tasks == []


@pytest.mark.asyncio
async def test_submit_enqueue_failure_preserves_response(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User,
    monkeypatch,
):
    made = await _make_checkpoint(db_session, owned_course, status="published")

    async def _boom(*args, **kwargs):
        raise RuntimeError("evidence seam down")

    monkeypatch.setattr(
        "app.services.checkpoint_responses.record_attempt_event", _boom
    )

    # Capture ids before the request: the endpoint's best-effort rollback (the
    # evidence seam raising) expires instances in the shared test session, so a
    # later ``made['review'].id`` access would trigger lazy async IO.
    cp_id = made["cp"].id
    review_id = made["review"].id
    student_id = enrolled_student.id

    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.post(
            f"/api/checkpoints/{cp_id}/responses",
            json={"card_id": str(review_id), "confidence": 0},
        )
    app.dependency_overrides.clear()
    # The response persists even though the evidence seam blew up.
    assert r.status_code in (200, 201), r.text
    row = (
        await db_session.execute(
            select(CheckpointResponse).where(
                CheckpointResponse.card_id == review_id,
                CheckpointResponse.user_id == student_id,
            )
        )
    ).scalar_one()
    assert row.confidence == 0


@pytest.mark.asyncio
async def test_submit_late_when_past_close_at(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    # published + still open (manual close) but past close_at → late.
    made = await _make_checkpoint(
        db_session, owned_course, status="published",
        close_at=_utcnow() - timedelta(minutes=5),
    )
    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.post(
            f"/api/checkpoints/{made['cp'].id}/responses",
            json={"card_id": str(made["review"].id), "confidence": 1},
        )
        assert r.status_code in (200, 201), r.text
    app.dependency_overrides.clear()
    row = (
        await db_session.execute(
            select(CheckpointResponse).where(
                CheckpointResponse.card_id == made["review"].id
            )
        )
    ).scalar_one()
    assert row.status == "late"
