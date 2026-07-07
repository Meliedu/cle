"""Quiz API tests — P5 B5: gated publish → transactional practice/quiz work_item.

Mirrors ``test_checkpoints_api.py`` B4 (the publish→work_item transactional seam):

- A ``graded`` quiz missing score-policy fields → 422 ``SCORE_POLICY_INCOMPLETE``
  with NOTHING published and NO work_item written (gate raises before any state
  change — atomicity).
- A fully-specified ``graded`` publish → ``is_published=True`` + a ``work_items``
  row ``source_kind='quiz'``, ``required=True``, ``score_bearing=True``,
  ``due_at=close_at``.
- A ``practice`` publish → published + a ``work_items`` row
  ``source_kind='practice'``, ``required=False``, ``score_bearing=False``,
  SKIPPING the gate.
- Re-publishing does NOT duplicate (unique index) and keeps
  ``title``/``due_at``/``close_at`` in sync (choice b, mirror publish_checkpoint).
- Non-owner → 404.
- A forced failure AFTER the work_item insert but BEFORE commit rolls the
  work_item back with the publish (one transaction).
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
from app.models import Course, Enrollment, User
from app.models.quiz import Quiz
from app.models.score import ScoreCategory
from app.models.work_item import WorkItem


@pytest_asyncio.fixture
async def owned_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="Quiz Publish Test",
        language="english",
        instructor_id=logged_in_user.id,
        enroll_code="QZPB0001",
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
async def score_category(db_session: AsyncSession, owned_course: Course) -> ScoreCategory:
    cat = ScoreCategory(course_id=owned_course.id, name="Quizzes", sort=0)
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_quiz(
    db_session: AsyncSession,
    course: Course,
    created_by: uuid.UUID,
    *,
    title: str = "Unit 1 quiz",
    **kwargs,
) -> Quiz:
    quiz = Quiz(
        course_id=course.id,
        created_by=created_by,
        title=title,
        **kwargs,
    )
    db_session.add(quiz)
    await db_session.commit()
    await db_session.refresh(quiz)
    return quiz


def _work_items_for(db_session: AsyncSession, quiz_id: uuid.UUID):
    return db_session.execute(
        select(WorkItem).where(WorkItem.source_id == quiz_id)
    )


# --------------------------------------------------------------------------- #
#  Graded publish: gated + atomic                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_publish_graded_missing_score_fields_422_and_atomic(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course,
    logged_in_user: User,
):
    """A graded quiz missing its score policy → 422 SCORE_POLICY_INCOMPLETE and
    NOTHING is published / no work_item written (gate raises before any state
    change)."""
    from tests.conftest import test_session_factory

    quiz = await _make_quiz(
        db_session, owned_course, logged_in_user.id,
        assessment_purpose="graded", score_bearing=True,
        # score_category_id / points / grading_mode / deadline all absent.
    )
    quiz_id = quiz.id

    r = await async_client.post(f"/api/quizzes/{quiz_id}/publish")
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "SCORE_POLICY_INCOMPLETE"
    assert set(detail["missing"]) == {
        "score_category_id", "points", "grading_mode", "deadline",
    }

    # Verify COMMITTED state on an independent connection: no publish, no work_item.
    async with test_session_factory() as verify:
        q_after = await verify.get(Quiz, quiz_id)
        assert q_after.is_published is False
        rows = (
            await verify.execute(select(WorkItem).where(WorkItem.source_id == quiz_id))
        ).scalars().all()
        assert rows == []


@pytest.mark.asyncio
async def test_publish_graded_full_writes_quiz_work_item(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course,
    score_category: ScoreCategory, logged_in_user: User,
):
    """A fully-specified graded publish → is_published=True + a `quiz` work_item
    (required + score_bearing) with due_at/close_at = the quiz's close_at."""
    close = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=2)
    quiz = await _make_quiz(
        db_session, owned_course, logged_in_user.id,
        assessment_purpose="graded", score_bearing=True,
        score_category_id=score_category.id, points=Decimal("10.00"),
        grading_mode="auto", close_at=close,
    )

    r = await async_client.post(f"/api/quizzes/{quiz.id}/publish")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["is_published"] is True

    rows = (await _work_items_for(db_session, quiz.id)).scalars().all()
    assert len(rows) == 1
    wi = rows[0]
    assert wi.source_kind == "quiz"
    assert wi.source_id == quiz.id
    assert wi.course_id == owned_course.id
    assert wi.title == quiz.title
    assert wi.required is True
    assert wi.score_bearing is True
    assert wi.created_by == logged_in_user.id
    assert wi.due_at == close
    assert wi.close_at == close


# --------------------------------------------------------------------------- #
#  Practice publish: skips the gate, writes a non-required work_item           #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_publish_practice_writes_practice_work_item_skips_gate(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course,
    logged_in_user: User,
):
    """A practice publish SKIPS the score gate and writes a `practice` work_item
    that is optional (required=False, score_bearing=False)."""
    quiz = await _make_quiz(
        db_session, owned_course, logged_in_user.id,
        assessment_purpose="practice",
        # No score policy at all — the gate must NOT run for practice.
    )

    r = await async_client.post(f"/api/quizzes/{quiz.id}/publish")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["is_published"] is True

    rows = (await _work_items_for(db_session, quiz.id)).scalars().all()
    assert len(rows) == 1
    wi = rows[0]
    assert wi.source_kind == "practice"
    assert wi.source_id == quiz.id
    assert wi.required is False
    assert wi.score_bearing is False


# --------------------------------------------------------------------------- #
#  Re-publish idempotency + kept-in-sync                                       #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_republish_graded_no_duplicate_and_syncs(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course,
    score_category: ScoreCategory, logged_in_user: User,
):
    """Re-publishing keeps ONE work_item (unique index) and its title/due_at/
    close_at track the quiz's current schedule (choice b)."""
    close1 = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)
    quiz = await _make_quiz(
        db_session, owned_course, logged_in_user.id, title="Quiz v1",
        assessment_purpose="graded", score_bearing=True,
        score_category_id=score_category.id, points=Decimal("10.00"),
        grading_mode="auto", close_at=close1,
    )

    r1 = await async_client.post(f"/api/quizzes/{quiz.id}/publish")
    assert r1.status_code == 200, r1.text

    # Teacher edits the title + schedule, then re-publishes.
    quiz.title = "Quiz v2"
    close2 = close1 + timedelta(days=4)
    quiz.close_at = close2
    await db_session.commit()

    r2 = await async_client.post(f"/api/quizzes/{quiz.id}/publish")
    assert r2.status_code == 200, r2.text

    rows = (await _work_items_for(db_session, quiz.id)).scalars().all()
    assert len(rows) == 1  # idempotent on (course, source_kind, source)
    await db_session.refresh(rows[0])
    assert rows[0].title == "Quiz v2"
    assert rows[0].due_at == close2
    assert rows[0].close_at == close2


# --------------------------------------------------------------------------- #
#  Owner isolation                                                            #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_publish_non_owner_404(
    async_client: AsyncClient, db_session: AsyncSession,
):
    """A quiz owned by another instructor is invisible → 404 (never leaks)."""
    other = User(
        better_auth_id="quiz_other_pub", email="quizotherpub@ust.hk",
        full_name="Other", role="instructor",
    )
    db_session.add(other)
    await db_session.flush()
    course = Course(
        name="ForeignQuiz", language="english",
        instructor_id=other.id, enroll_code="QZPBFRGN",
    )
    db_session.add(course)
    await db_session.flush()
    quiz = Quiz(
        course_id=course.id, created_by=other.id, title="theirs",
        assessment_purpose="practice",
    )
    db_session.add(quiz)
    await db_session.commit()

    r = await async_client.post(f"/api/quizzes/{quiz.id}/publish")
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
#  Atomicity: work_item rides the publish commit                              #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_publish_work_item_rolls_back_on_failure(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course,
    score_category: ScoreCategory, logged_in_user: User, monkeypatch,
):
    """If the publish transaction fails AFTER the work_item insert but before
    commit, the work_item is rolled back too — same transaction (atomicity)."""
    from tests.conftest import test_session_factory

    close = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=2)
    quiz = await _make_quiz(
        db_session, owned_course, logged_in_user.id,
        assessment_purpose="graded", score_bearing=True,
        score_category_id=score_category.id, points=Decimal("10.00"),
        grading_mode="auto", close_at=close,
    )
    quiz_id = quiz.id

    import app.api.quizzes as quizzes_mod
    from app.services.work_items import upsert_work_item as real_upsert

    async def _boom_after_insert(*args, **kwargs):
        # Perform the REAL insert (so the row lives in the uncommitted
        # transaction), then blow up before the endpoint reaches db.commit().
        await real_upsert(*args, **kwargs)
        raise RuntimeError("boom after work_item insert, before commit")

    monkeypatch.setattr(quizzes_mod, "upsert_work_item", _boom_after_insert)

    with pytest.raises(RuntimeError, match="boom after work_item insert"):
        await async_client.post(f"/api/quizzes/{quiz_id}/publish")

    # Verify COMMITTED state on an independent connection: neither the publish
    # flip nor the work_item insert persisted — they shared one transaction.
    async with test_session_factory() as verify:
        rows = (
            await verify.execute(select(WorkItem).where(WorkItem.source_id == quiz_id))
        ).scalars().all()
        assert rows == []
        q_after = await verify.get(Quiz, quiz_id)
        assert q_after.is_published is False
