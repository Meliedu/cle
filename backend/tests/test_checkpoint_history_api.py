"""P3 T8 — student checkpoint history + follow-up-suggested + revisit.

Covers the student-facing tail of the checkpoint loop:

* ``GET /users/me/courses/{id}/checkpoints`` (S039) — the student's own
  checkpoint history for a course, each row carrying a *derived* status:
  ``complete`` (responded to every live card, none late), ``late`` (a response
  arrived after the window / a closed checkpoint left partially answered),
  ``missed`` (closed with no response) or ``upcoming`` (still open, not yet
  complete). Enrollment-scoped: a non-enrolled user is rejected 403.
* ``GET /checkpoints/{id}/follow-up-suggested`` (S040) — the weak cards to
  revisit, derived from the student's own low-confidence responses on this
  checkpoint (threshold: ``confidence <= -1`` on the −2..+2 scale). Concept
  info is attached when the card is concept-tagged.
* ``POST /checkpoints/{id}/revisit-response`` (S041) — re-submits against a
  ``follow_up``-kind checkpoint that carries ``carried_from_id`` → the
  original. Reuses the T7 submission service and returns a before/after
  confidence signal (the student's original vs revisit confidence on the
  shared concept).

All three are enrollment-scoped (the student's own data only); a non-enrolled
user gets 403.
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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def owned_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="Checkpoint History", language="english",
        instructor_id=logged_in_user.id, enroll_code="CHKH0001",
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
        better_auth_id="chkh_student_01", email="chkhstudent@connect.ust.hk",
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
    kind: str = "session",
    status: str = "published",
    title: str = "Session checkpoint",
    close_at: datetime | None = None,
    carried_from_id: uuid.UUID | None = None,
    tag_concept: Concept | None = None,
) -> dict:
    """Build a checkpoint with two review points + one final card.

    When ``tag_concept`` is supplied, the first review card is tagged with it
    (so the revisit before/after can match cards across checkpoints by concept).
    """
    now = _utcnow()
    cp = Checkpoint(
        course_id=course.id, kind=kind, title=title, status=status,
        release_at=now - timedelta(hours=1), close_at=close_at,
        close_rule="manual", carried_from_id=carried_from_id,
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
    if tag_concept is not None:
        db_session.add(
            ConceptTag(
                concept_id=tag_concept.id, target_kind="checkpoint_card",
                target_id=review.id, weight=Decimal("1.00"),
            )
        )
    await db_session.commit()
    await db_session.refresh(cp)
    for c in (review, review2, final):
        await db_session.refresh(c)
    return {"cp": cp, "review": review, "review2": review2, "final": final}


async def _add_response(
    db_session: AsyncSession,
    made: dict,
    card: CheckpointCard,
    user: User,
    *,
    confidence: int | None = None,
    text: str | None = None,
    status: str = "on_time",
) -> None:
    db_session.add(
        CheckpointResponse(
            checkpoint_id=made["cp"].id, card_id=card.id, user_id=user.id,
            confidence=confidence, text_response=text, status=status,
        )
    )
    await db_session.commit()


async def _make_concept(db_session: AsyncSession, course: Course) -> Concept:
    concept = Concept(
        course_id=course.id, name="Ordering food",
        status="approved", instructor_curated=True,
    )
    db_session.add(concept)
    await db_session.commit()
    await db_session.refresh(concept)
    return concept


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


# ----- history (S039) -----

@pytest.mark.asyncio
async def test_history_derives_per_checkpoint_status(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    # complete: closed, responded to every live card on time.
    complete = await _make_checkpoint(
        db_session, owned_course, status="closed", title="Complete one",
        close_at=_utcnow() - timedelta(hours=1),
    )
    await _add_response(db_session, complete, complete["review"], enrolled_student, confidence=1)
    await _add_response(db_session, complete, complete["review2"], enrolled_student, confidence=2)
    await _add_response(db_session, complete, complete["final"], enrolled_student, text="ok")

    # missed: closed, no response at all.
    missed = await _make_checkpoint(
        db_session, owned_course, status="closed", title="Missed one",
        close_at=_utcnow() - timedelta(hours=1),
    )

    # late: closed, responded but a response arrived late.
    late = await _make_checkpoint(
        db_session, owned_course, status="closed", title="Late one",
        close_at=_utcnow() - timedelta(hours=1),
    )
    await _add_response(db_session, late, late["review"], enrolled_student, confidence=0, status="late")

    # upcoming: still open (published), not yet complete.
    upcoming = await _make_checkpoint(
        db_session, owned_course, status="published", title="Upcoming one",
    )

    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.get(f"/api/users/me/courses/{owned_course.id}/checkpoints")
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    by_id = {row["checkpoint_id"]: row for row in rows}
    assert by_id[str(complete["cp"].id)]["derived_status"] == "complete"
    assert by_id[str(missed["cp"].id)]["derived_status"] == "missed"
    assert by_id[str(late["cp"].id)]["derived_status"] == "late"
    assert by_id[str(upcoming["cp"].id)]["derived_status"] == "upcoming"


@pytest.mark.asyncio
async def test_history_excludes_draft_checkpoints(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    await _make_checkpoint(db_session, owned_course, status="draft", title="Draft")
    published = await _make_checkpoint(db_session, owned_course, status="published")

    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.get(f"/api/users/me/courses/{owned_course.id}/checkpoints")
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    ids = {row["checkpoint_id"] for row in r.json()["data"]}
    assert str(published["cp"].id) in ids
    assert len(ids) == 1


@pytest.mark.asyncio
async def test_history_non_enrolled_rejected(
    db_session: AsyncSession, owned_course: Course
):
    await _make_checkpoint(db_session, owned_course, status="published")
    outsider = User(
        better_auth_id="chkh_outsider", email="outsider2@connect.ust.hk",
        full_name="Outsider", role="student",
    )
    db_session.add(outsider)
    await db_session.commit()
    async with _student_client(db_session, outsider) as ac:
        r = await ac.get(f"/api/users/me/courses/{owned_course.id}/checkpoints")
    app.dependency_overrides.clear()
    assert r.status_code == 403


# ----- follow-up-suggested (S040) -----

@pytest.mark.asyncio
async def test_follow_up_suggested_returns_low_confidence_cards(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    concept = await _make_concept(db_session, owned_course)
    made = await _make_checkpoint(
        db_session, owned_course, status="closed", tag_concept=concept,
    )
    # low confidence on the tagged review card → weak.
    await _add_response(db_session, made, made["review"], enrolled_student, confidence=-2)
    # high confidence on the other review card → strong (excluded).
    await _add_response(db_session, made, made["review2"], enrolled_student, confidence=2)

    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.get(f"/api/checkpoints/{made['cp'].id}/follow-up-suggested")
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["threshold"] == -1
    weak = data["weak_cards"]
    assert len(weak) == 1
    assert weak[0]["card_id"] == str(made["review"].id)
    assert weak[0]["confidence"] == -2
    assert weak[0]["concept_id"] == str(concept.id)
    assert weak[0]["concept_name"] == "Ordering food"


@pytest.mark.asyncio
async def test_follow_up_suggested_non_enrolled_rejected(
    db_session: AsyncSession, owned_course: Course
):
    made = await _make_checkpoint(db_session, owned_course, status="closed")
    outsider = User(
        better_auth_id="chkh_outsider2", email="outsider3@connect.ust.hk",
        full_name="Outsider", role="student",
    )
    db_session.add(outsider)
    await db_session.commit()
    async with _student_client(db_session, outsider) as ac:
        r = await ac.get(f"/api/checkpoints/{made['cp'].id}/follow-up-suggested")
    app.dependency_overrides.clear()
    assert r.status_code == 403


# ----- revisit-response (S041) -----

@pytest.mark.asyncio
async def test_revisit_response_submits_and_records_before_after(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    concept = await _make_concept(db_session, owned_course)
    # Original checkpoint: student answered the tagged card with low confidence.
    original = await _make_checkpoint(
        db_session, owned_course, status="closed", title="Original",
        tag_concept=concept,
    )
    await _add_response(db_session, original, original["review"], enrolled_student, confidence=-2)

    # Follow-up checkpoint carries carried_from_id → the original, same concept.
    follow_up = await _make_checkpoint(
        db_session, owned_course, kind="follow_up", status="published",
        title="Follow-up", carried_from_id=original["cp"].id, tag_concept=concept,
    )

    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.post(
            f"/api/checkpoints/{follow_up['cp'].id}/revisit-response",
            json={"card_id": str(follow_up["review"].id), "confidence": 2},
        )
    app.dependency_overrides.clear()

    assert r.status_code in (200, 201), r.text
    data = r.json()["data"]
    assert data["carried_from_id"] == str(original["cp"].id)
    assert data["confidence_before"] == -2
    assert data["confidence_after"] == 2
    assert data["delta"] == 4
    assert data["response"]["card_id"] == str(follow_up["review"].id)

    # The revisit response is persisted against the follow-up checkpoint.
    row = (
        await db_session.execute(
            select(CheckpointResponse).where(
                CheckpointResponse.card_id == follow_up["review"].id,
                CheckpointResponse.user_id == enrolled_student.id,
            )
        )
    ).scalar_one()
    assert row.confidence == 2
    assert row.checkpoint_id == follow_up["cp"].id


@pytest.mark.asyncio
async def test_revisit_rejects_non_follow_up_checkpoint(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    # A plain session checkpoint (no carried_from) can't take a revisit.
    made = await _make_checkpoint(db_session, owned_course, status="published")
    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.post(
            f"/api/checkpoints/{made['cp'].id}/revisit-response",
            json={"card_id": str(made["review"].id), "confidence": 1},
        )
    app.dependency_overrides.clear()
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "NOT_A_REVISIT"


@pytest.mark.asyncio
async def test_revisit_non_enrolled_rejected(
    db_session: AsyncSession, owned_course: Course
):
    original = await _make_checkpoint(db_session, owned_course, status="closed")
    follow_up = await _make_checkpoint(
        db_session, owned_course, kind="follow_up", status="published",
        carried_from_id=original["cp"].id,
    )
    outsider = User(
        better_auth_id="chkh_outsider3", email="outsider4@connect.ust.hk",
        full_name="Outsider", role="student",
    )
    db_session.add(outsider)
    await db_session.commit()
    async with _student_client(db_session, outsider) as ac:
        r = await ac.post(
            f"/api/checkpoints/{follow_up['cp'].id}/revisit-response",
            json={"card_id": str(follow_up["review"].id), "confidence": 1},
        )
    app.dependency_overrides.clear()
    assert r.status_code == 403
