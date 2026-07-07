"""P7 Task B8: memory.py router — course-record list + detail + decide + audit.

Covers the owner-guarded teacher surface over ``course_record_items`` (spec
§4.10, Decision 5):

* The migration adds ``decision`` (CHECK ``keep|revise|reject|carry_forward``,
  nullable), ``decided_by`` (FK users nullable), ``decided_at`` (tz nullable) —
  asserted here via the ORM model / ``create_all`` bootstrap.
* ``GET /courses/{id}/memory`` — the course's record items with a derived
  ``kind`` (from which summary JSONBs are populated), newest first
  (owner-guarded via ``get_owned_course`` → 404 non-owner).
* ``GET /memory/{id}`` — detail (owner-guarded via the item's course → 404).
* ``POST /memory/{id}/decide {decision}`` — sets ``decision`` / ``decided_by`` /
  ``decided_at``, syncs ``carry_forward`` (true iff decision ``carry_forward``),
  appends an ``audit_events`` row (``memory.decide`` / ``course_record_item``),
  AND appends a ``review_action`` ONLY when ``learning_note_id`` is present
  (Decision 5); an invalid decision → 422; a non-owner → 404.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course, User
from app.models.audit_event import AuditEvent
from app.models.evidence import CourseRecordItem, LearningNote, ReviewAction


@pytest_asyncio.fixture
async def owned_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="Memory Test", language="english",
        instructor_id=logged_in_user.id, enroll_code="MEMAPI01",
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


@pytest_asyncio.fixture
async def foreign_course(db_session: AsyncSession) -> Course:
    other = User(
        better_auth_id="mem_other_instr", email="memother@ust.hk",
        full_name="Other", role="instructor",
    )
    db_session.add(other)
    await db_session.flush()
    course = Course(
        name="Foreign", language="english",
        instructor_id=other.id, enroll_code="MEMFOR01",
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


async def _make_item(
    db_session: AsyncSession,
    course: Course,
    *,
    learning_note_id=None,
    relationship_summary=None,
    action_summary=None,
    outcome_summary=None,
    instructor_comment=None,
    carry_forward=False,
    created_at=None,
) -> CourseRecordItem:
    item = CourseRecordItem(
        course_id=course.id,
        learning_note_id=learning_note_id,
        relationship_summary=relationship_summary,
        action_summary=action_summary,
        outcome_summary=outcome_summary,
        instructor_comment=instructor_comment,
        carry_forward=carry_forward,
    )
    if created_at is not None:
        item.created_at = created_at
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


async def _make_note(db_session: AsyncSession, course: Course) -> LearningNote:
    note = LearningNote(
        course_id=course.id,
        observed_signal="observed something",
        review_status="reviewed",
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)
    return note


# ----- migration / model columns -----

@pytest.mark.asyncio
async def test_model_has_decision_columns(db_session, owned_course):
    """The new columns exist and the CHECK accepts a valid decision."""
    item = await _make_item(
        db_session, owned_course, outcome_summary={"status": "persistent"},
    )
    assert item.decision is None
    assert item.decided_by is None
    assert item.decided_at is None
    # A valid decision round-trips.
    item.decision = "carry_forward"
    await db_session.commit()
    await db_session.refresh(item)
    assert item.decision == "carry_forward"


# ----- list -----

@pytest.mark.asyncio
async def test_list_derives_kind_and_orders_desc(
    async_client, db_session, owned_course
):
    now = datetime.now(timezone.utc)
    await _make_item(
        db_session, owned_course, relationship_summary={"x": 1},
        created_at=now - timedelta(days=2),
    )
    await _make_item(
        db_session, owned_course, action_summary={"y": 1},
        created_at=now - timedelta(days=1),
    )
    await _make_item(
        db_session, owned_course, outcome_summary={"status": "persistent"},
        created_at=now,
    )
    r = await async_client.get(f"/api/courses/{owned_course.id}/memory")
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data) == 3
    # newest first
    assert data[0]["kind"] == "outcome"
    assert data[1]["kind"] == "action"
    assert data[2]["kind"] == "relationship"


@pytest.mark.asyncio
async def test_list_non_owner_404(async_client, foreign_course):
    r = await async_client.get(f"/api/courses/{foreign_course.id}/memory")
    assert r.status_code == 404


# ----- detail -----

@pytest.mark.asyncio
async def test_detail_returns_item(async_client, db_session, owned_course):
    item = await _make_item(
        db_session, owned_course, outcome_summary={"status": "improved"},
        instructor_comment="good progress",
    )
    r = await async_client.get(f"/api/memory/{item.id}")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["id"] == str(item.id)
    assert data["instructor_comment"] == "good progress"
    assert data["kind"] == "outcome"


@pytest.mark.asyncio
async def test_detail_non_owner_404(async_client, db_session, foreign_course):
    item = await _make_item(db_session, foreign_course, action_summary={"a": 1})
    r = await async_client.get(f"/api/memory/{item.id}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_detail_missing_404(async_client):
    r = await async_client.get(f"/api/memory/{uuid.uuid4()}")
    assert r.status_code == 404


# ----- decide -----

@pytest.mark.asyncio
async def test_decide_carry_forward_sets_flag_and_audit(
    async_client, db_session, owned_course, logged_in_user
):
    item = await _make_item(
        db_session, owned_course, outcome_summary={"status": "persistent"},
        carry_forward=False,
    )
    r = await async_client.post(
        f"/api/memory/{item.id}/decide", json={"decision": "carry_forward"}
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["decision"] == "carry_forward"
    assert data["carry_forward"] is True
    assert data["decided_by"] == str(logged_in_user.id)
    assert data["decided_at"] is not None

    await db_session.refresh(item)
    assert item.decision == "carry_forward"
    assert item.carry_forward is True
    assert item.decided_by == logged_in_user.id

    events = (
        await db_session.execute(
            select(AuditEvent).where(
                AuditEvent.event_type == "memory.decide",
                AuditEvent.target_id == item.id,
            )
        )
    ).scalars().all()
    assert len(events) == 1
    assert events[0].target_kind == "course_record_item"
    assert events[0].course_id == owned_course.id
    assert events[0].actor_id == logged_in_user.id


@pytest.mark.asyncio
async def test_decide_reject_clears_carry_forward(
    async_client, db_session, owned_course
):
    item = await _make_item(
        db_session, owned_course, outcome_summary={"status": "persistent"},
        carry_forward=True,
    )
    r = await async_client.post(
        f"/api/memory/{item.id}/decide", json={"decision": "reject"}
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["decision"] == "reject"
    # carry_forward synced false (true iff decision == carry_forward)
    assert data["carry_forward"] is False
    await db_session.refresh(item)
    assert item.carry_forward is False


@pytest.mark.asyncio
async def test_decide_appends_review_action_when_note_linked(
    async_client, db_session, owned_course, logged_in_user
):
    note = await _make_note(db_session, owned_course)
    item = await _make_item(
        db_session, owned_course, learning_note_id=note.id,
        outcome_summary={"status": "persistent"},
    )
    r = await async_client.post(
        f"/api/memory/{item.id}/decide", json={"decision": "carry_forward"}
    )
    assert r.status_code == 200
    actions = (
        await db_session.execute(
            select(ReviewAction).where(
                ReviewAction.learning_note_id == note.id
            )
        )
    ).scalars().all()
    assert len(actions) == 1
    assert actions[0].action_type == "carry_forward"
    assert actions[0].reviewer_id == logged_in_user.id


@pytest.mark.asyncio
async def test_decide_no_review_action_when_no_note(
    async_client, db_session, owned_course
):
    item = await _make_item(
        db_session, owned_course, outcome_summary={"status": "persistent"},
        learning_note_id=None,
    )
    r = await async_client.post(
        f"/api/memory/{item.id}/decide", json={"decision": "keep"}
    )
    assert r.status_code == 200
    # No note → no review_action row, but the audit_events row is still written.
    actions = (
        await db_session.execute(select(ReviewAction))
    ).scalars().all()
    assert len(actions) == 0
    events = (
        await db_session.execute(
            select(AuditEvent).where(AuditEvent.target_id == item.id)
        )
    ).scalars().all()
    assert len(events) == 1


@pytest.mark.asyncio
async def test_decide_invalid_decision_422(
    async_client, db_session, owned_course
):
    item = await _make_item(db_session, owned_course, action_summary={"a": 1})
    r = await async_client.post(
        f"/api/memory/{item.id}/decide", json={"decision": "bogus"}
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_decide_non_owner_404(async_client, db_session, foreign_course):
    item = await _make_item(db_session, foreign_course, action_summary={"a": 1})
    r = await async_client.post(
        f"/api/memory/{item.id}/decide", json={"decision": "keep"}
    )
    assert r.status_code == 404
