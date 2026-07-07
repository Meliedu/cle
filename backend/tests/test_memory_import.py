"""P7 Task B9: next-term suggestions + setup import-memory + memory summary.

Covers the course-bound carry-forward memory flow (spec §4.10 / §5.6, Decision 6):

* ``GET /courses/{id}/memory/next-term-suggestions`` — lists ONLY
  ``decision='carry_forward'`` record items from the SAME course-code lineage
  (matched on ``courses.code`` + the SAME ``instructor_id`` of a DIFFERENT prior
  course — NEVER by student identity). Undecided / ``reject`` / ``keep`` items,
  a different-code course, and a same-code course owned by ANOTHER instructor are
  all excluded.
* ``POST /courses/{id}/setup/import-memory {item_ids}`` — refuses an undecided /
  ``reject`` item with a typed 409 ``MEMORY_UNDECIDED``; on accepted
  ``carry_forward`` items it copies ONLY the instructor-authored summaries
  (relationship / action / outcome / instructor_comment — NO student ``user_id``)
  into the new course and threads them into ``checkpoint_generation._build_context``.
* ``GET /courses/{id}/memory/summary`` (T036) — counts-by-decision + a
  carry-forward roster for the teacher overview.

Security invariant (Decision 6): memory is course-bound — no student ``user_id``
crosses terms; the imported grounding block contains ONLY instructor summaries.
"""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course, User
from app.models.audit_event import AuditEvent
from app.models.curriculum import CourseMeeting
from app.models.evidence import CourseRecordItem, LearningNote


# ----- fixtures -----

@pytest_asyncio.fixture
async def current_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    """The NEW-term course being set up (same code lineage LING101)."""
    course = Course(
        name="Cantonese I (2026 Fall)", code="LING101", language="cantonese",
        instructor_id=logged_in_user.id, enroll_code="CURR0101",
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


@pytest_asyncio.fixture
async def prior_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    """A PRIOR-term course of the SAME code + instructor (the lineage source)."""
    course = Course(
        name="Cantonese I (2025 Fall)", code="LING101", language="cantonese",
        instructor_id=logged_in_user.id, enroll_code="PRIO0101",
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


async def _make_item(
    db_session: AsyncSession, course: Course, *, decision=None,
    relationship_summary=None, action_summary=None, outcome_summary=None,
    instructor_comment=None, learning_note_id=None,
) -> CourseRecordItem:
    item = CourseRecordItem(
        course_id=course.id,
        learning_note_id=learning_note_id,
        relationship_summary=relationship_summary,
        action_summary=action_summary,
        outcome_summary=outcome_summary,
        instructor_comment=instructor_comment,
        decision=decision,
        carry_forward=(decision == "carry_forward"),
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


# ----- next-term suggestions -----

@pytest.mark.asyncio
async def test_suggestions_only_carry_forward_from_same_lineage(
    async_client, db_session, current_course, prior_course, logged_in_user
):
    # The one that MUST appear: carry_forward in the same-code prior course.
    keeper = await _make_item(
        db_session, prior_course, decision="carry_forward",
        outcome_summary={"status": "persistent", "note": "tone drilling helps"},
        instructor_comment="Front-load tone pairs next term.",
    )
    # Same course, non-carry_forward decisions → excluded.
    await _make_item(db_session, prior_course, decision="keep",
                     action_summary={"a": 1})
    await _make_item(db_session, prior_course, decision="reject",
                     action_summary={"a": 2})
    await _make_item(db_session, prior_course, decision=None,
                     action_summary={"a": 3})  # undecided

    # A DIFFERENT-code prior course (same instructor) → excluded.
    other_code = Course(
        name="Mandarin", code="LING220", language="mandarin",
        instructor_id=logged_in_user.id, enroll_code="OTHERCOD",
    )
    db_session.add(other_code)
    await db_session.commit()
    await _make_item(db_session, other_code, decision="carry_forward",
                     outcome_summary={"x": 1})

    # A SAME-code course owned by ANOTHER instructor → excluded (Decision 6).
    other = User(better_auth_id="mi_other", email="other@ust.hk",
                 full_name="Other", role="instructor")
    db_session.add(other)
    await db_session.flush()
    foreign_same_code = Course(
        name="Cantonese I (other prof)", code="LING101", language="cantonese",
        instructor_id=other.id, enroll_code="FORGN101",
    )
    db_session.add(foreign_same_code)
    await db_session.commit()
    await _make_item(db_session, foreign_same_code, decision="carry_forward",
                     outcome_summary={"y": 1})

    r = await async_client.get(
        f"/api/courses/{current_course.id}/memory/next-term-suggestions"
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == str(keeper.id)
    assert data[0]["decision"] == "carry_forward"
    # Source-course provenance for the picker.
    assert data[0]["source_course_id"] == str(prior_course.id)
    assert data[0]["source_course_code"] == "LING101"


@pytest.mark.asyncio
async def test_suggestions_empty_when_current_course_has_no_code(
    async_client, db_session, logged_in_user
):
    codeless = Course(
        name="Ad-hoc", code=None, language="english",
        instructor_id=logged_in_user.id, enroll_code="NOCODE01",
    )
    db_session.add(codeless)
    await db_session.commit()
    await db_session.refresh(codeless)
    r = await async_client.get(
        f"/api/courses/{codeless.id}/memory/next-term-suggestions"
    )
    assert r.status_code == 200
    assert r.json()["data"] == []


@pytest.mark.asyncio
async def test_suggestions_non_owner_404(async_client, db_session):
    other = User(better_auth_id="mi_o2", email="o2@ust.hk",
                 full_name="O2", role="instructor")
    db_session.add(other)
    await db_session.flush()
    course = Course(name="F", code="LING101", language="cantonese",
                    instructor_id=other.id, enroll_code="FORGN102")
    db_session.add(course)
    await db_session.commit()
    r = await async_client.get(
        f"/api/courses/{course.id}/memory/next-term-suggestions"
    )
    assert r.status_code == 404


# ----- import-memory gate -----

@pytest.mark.asyncio
async def test_import_refuses_undecided_item(
    async_client, db_session, current_course, prior_course
):
    undecided = await _make_item(db_session, prior_course, decision=None,
                                 outcome_summary={"x": 1})
    r = await async_client.post(
        f"/api/courses/{current_course.id}/setup/import-memory",
        json={"item_ids": [str(undecided.id)]},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "MEMORY_UNDECIDED"


@pytest.mark.asyncio
async def test_import_refuses_reject_item(
    async_client, db_session, current_course, prior_course
):
    rejected = await _make_item(db_session, prior_course, decision="reject",
                                outcome_summary={"x": 1})
    r = await async_client.post(
        f"/api/courses/{current_course.id}/setup/import-memory",
        json={"item_ids": [str(rejected.id)]},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "MEMORY_UNDECIDED"


@pytest.mark.asyncio
async def test_import_non_owner_course_404(async_client, db_session):
    other = User(better_auth_id="mi_o3", email="o3@ust.hk",
                 full_name="O3", role="instructor")
    db_session.add(other)
    await db_session.flush()
    course = Course(name="F", code="LING101", language="cantonese",
                    instructor_id=other.id, enroll_code="FORGN103")
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    r = await async_client.post(
        f"/api/courses/{course.id}/setup/import-memory",
        json={"item_ids": [str(uuid.uuid4())]},
    )
    assert r.status_code == 404


# ----- import threads into checkpoint-generation grounding -----

@pytest.mark.asyncio
async def test_import_threads_into_build_context_no_student_id(
    async_client, db_session, current_course, prior_course, test_student, monkeypatch
):
    # A note authored over a STUDENT signal — its id must NEVER cross terms.
    note = LearningNote(
        course_id=prior_course.id, user_id=test_student.id,
        observed_signal="student struggled with tone 6", review_status="reviewed",
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)

    item = await _make_item(
        db_session, prior_course, decision="carry_forward",
        learning_note_id=note.id,
        relationship_summary={"rapport": "warmed up after week 3"},
        action_summary={"plan": "spaced tone-pair drills"},
        outcome_summary={"status": "improved", "detail": "tone 6 stabilised"},
        instructor_comment="Keep the week-3 pairing exercise.",
    )

    r = await async_client.post(
        f"/api/courses/{current_course.id}/setup/import-memory",
        json={"item_ids": [str(item.id)]},
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["imported_count"] == 1

    # Keep generation offline: no embedding / retrieval network call.
    from app.services import checkpoint_generation as cg

    async def _no_chunks(*args, **kwargs):
        return []

    monkeypatch.setattr(cg, "retrieve_grounding_chunks", _no_chunks)

    meeting = CourseMeeting(
        course_id=current_course.id, meeting_index=1, title="Session 1",
        scheduled_at=datetime.now(timezone.utc), topic_summary="tones review",
    )
    db_session.add(meeting)
    await db_session.commit()
    await db_session.refresh(meeting)

    context = await cg._build_context(db_session, current_course.id, meeting)

    # The imported instructor summaries are present.
    assert "Keep the week-3 pairing exercise." in context
    assert "spaced tone-pair drills" in context
    assert "tone 6 stabilised" in context
    assert "warmed up after week 3" in context

    # SECURITY: no student identity crosses terms — neither the student user_id
    # nor the source note id appears in the grounding context.
    assert str(test_student.id) not in context
    assert str(note.id) not in context


# ----- memory summary (T036) -----

@pytest.mark.asyncio
async def test_memory_summary_counts_and_roster(
    async_client, db_session, current_course
):
    cf1 = await _make_item(db_session, current_course, decision="carry_forward",
                           outcome_summary={"a": 1},
                           instructor_comment="carry me 1")
    cf2 = await _make_item(db_session, current_course, decision="carry_forward",
                           outcome_summary={"a": 2},
                           instructor_comment="carry me 2")
    await _make_item(db_session, current_course, decision="keep",
                     action_summary={"b": 1})
    await _make_item(db_session, current_course, decision="reject",
                     action_summary={"b": 2})
    await _make_item(db_session, current_course, decision="revise",
                     action_summary={"b": 3})
    await _make_item(db_session, current_course, decision=None,
                     action_summary={"b": 4})  # undecided

    r = await async_client.get(
        f"/api/courses/{current_course.id}/memory/summary"
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == 6
    counts = data["counts"]
    assert counts["carry_forward"] == 2
    assert counts["keep"] == 1
    assert counts["reject"] == 1
    assert counts["revise"] == 1
    assert counts["undecided"] == 1
    roster_ids = {row["id"] for row in data["carry_forward_roster"]}
    assert roster_ids == {str(cf1.id), str(cf2.id)}


@pytest.mark.asyncio
async def test_summary_non_owner_404(async_client, db_session):
    other = User(better_auth_id="mi_o4", email="o4@ust.hk",
                 full_name="O4", role="instructor")
    db_session.add(other)
    await db_session.flush()
    course = Course(name="F", code="LING101", language="cantonese",
                    instructor_id=other.id, enroll_code="FORGN104")
    db_session.add(course)
    await db_session.commit()
    r = await async_client.get(f"/api/courses/{course.id}/memory/summary")
    assert r.status_code == 404


# ----- import writes an audit row -----

@pytest.mark.asyncio
async def test_import_writes_audit_event(
    async_client, db_session, current_course, prior_course, logged_in_user
):
    item = await _make_item(db_session, prior_course, decision="carry_forward",
                            outcome_summary={"x": 1},
                            instructor_comment="carry")
    r = await async_client.post(
        f"/api/courses/{current_course.id}/setup/import-memory",
        json={"item_ids": [str(item.id)]},
    )
    assert r.status_code == 200
    events = (
        await db_session.execute(
            select(AuditEvent).where(
                AuditEvent.event_type == "memory.import",
                AuditEvent.course_id == current_course.id,
            )
        )
    ).scalars().all()
    assert len(events) == 1
    assert events[0].actor_id == logged_in_user.id
