"""Phase 6 — instructor review + student follow-up API (Meli evidence loop).

Exercises ``app/api/review.py``: the evidence-conversion point where a draft
``LearningNote`` becomes course memory once an instructor records a
``ReviewAction``, plus the student-facing follow-up Review Path.

No live Postgres assumptions beyond the shared test-database fixtures; auth is
swapped per request via ``app.dependency_overrides`` (mirroring
``test_mastery_integration.py``). The ``client`` fixture owns the ``get_db``
override and clears all overrides on teardown, so tests only (re)assign
``get_current_user`` and never clear mid-test.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.api.deps import get_current_user
from app.main import app
from app.models import FollowUpAction, LearningNote, ReviewAction
from app.models.course import Course, Enrollment
from app.models.user import User


def _act_as(user: User) -> None:
    """Route ``get_current_user`` to a specific user for the next request(s)."""
    app.dependency_overrides[get_current_user] = lambda u=user: u


async def _make_course(db, instructor: User, code: str) -> Course:
    course = Course(
        instructor_id=instructor.id,
        name="C",
        language="english",
        enroll_code=code,
    )
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return course


async def _make_note(
    db,
    course: Course,
    *,
    user_id=None,
    review_status: str = "draft",
    draft: str | None = "AI draft interpretation",
) -> LearningNote:
    note = LearningNote(
        course_id=course.id,
        user_id=user_id,
        observed_signal="missed 3/5 prompts on tone sandhi",
        draft_interpretation=draft,
        review_status=review_status,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


_AUTH = {"Authorization": "Bearer test-token"}


@pytest.mark.asyncio
async def test_accept_promotes_note_and_records_review_action(
    client, db_session, test_instructor, test_student
):
    """action_type='accept' → note 'reviewed' + immutable ReviewAction audit row."""
    course = await _make_course(db_session, test_instructor, "RV0001")
    note = await _make_note(db_session, course, user_id=test_student.id)

    _act_as(test_instructor)
    r = await client.post(
        f"/api/learning-notes/{note.id}/review",
        json={"action_type": "accept"},
        headers=_AUTH,
    )
    assert r.status_code == 200, r.text

    await db_session.refresh(note)
    assert note.review_status == "reviewed"

    action = (
        await db_session.execute(
            select(ReviewAction).where(ReviewAction.learning_note_id == note.id)
        )
    ).scalar_one()
    assert action.prior_status == "draft"
    assert action.new_status == "reviewed"
    assert action.reviewer_id == test_instructor.id


@pytest.mark.asyncio
async def test_edit_rewrites_draft_interpretation(
    client, db_session, test_instructor, test_student
):
    """action_type='edit' with edit_text → 'edited' + draft_interpretation rewritten."""
    course = await _make_course(db_session, test_instructor, "RV0002")
    note = await _make_note(db_session, course, user_id=test_student.id)

    edited = "Instructor-corrected interpretation: partial tone confusion."
    _act_as(test_instructor)
    r = await client.post(
        f"/api/learning-notes/{note.id}/review",
        json={"action_type": "edit", "edit_text": edited},
        headers=_AUTH,
    )
    assert r.status_code == 200, r.text

    await db_session.refresh(note)
    assert note.review_status == "edited"
    assert note.draft_interpretation == edited


@pytest.mark.asyncio
async def test_assign_followup_creates_student_follow_up(
    client, db_session, test_instructor, test_student
):
    """action_type='assign_followup' → FollowUpAction assigned to the note's student."""
    course = await _make_course(db_session, test_instructor, "RV0003")
    note = await _make_note(db_session, course, user_id=test_student.id)

    _act_as(test_instructor)
    r = await client.post(
        f"/api/learning-notes/{note.id}/review",
        json={"action_type": "assign_followup"},
        headers=_AUTH,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["follow_up"] is not None

    follow_up = (
        await db_session.execute(
            select(FollowUpAction).where(FollowUpAction.learning_note_id == note.id)
        )
    ).scalar_one()
    assert follow_up.assignment_status == "assigned"
    assert follow_up.assigned_by == test_instructor.id
    assert follow_up.user_id == test_student.id


@pytest.mark.asyncio
async def test_review_on_foreign_course_note_returns_404(
    client, db_session, test_instructor, test_student
):
    """Instructor B reviewing instructor A's note → 404 (existence masked)."""
    course_a = await _make_course(db_session, test_instructor, "RV0004")
    note = await _make_note(db_session, course_a, user_id=test_student.id)

    instructor_b = User(
        better_auth_id="dev_instructor_b",
        email="instructor-b@ust.hk",
        full_name="Instructor B",
        role="instructor",
    )
    db_session.add(instructor_b)
    await db_session.commit()
    await db_session.refresh(instructor_b)

    _act_as(instructor_b)
    r = await client.post(
        f"/api/learning-notes/{note.id}/review",
        json={"action_type": "accept"},
        headers=_AUTH,
    )
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_assign_followup_on_cohort_note_without_target_returns_400(
    client, db_session, test_instructor
):
    """Cohort note (user_id=None) + assign_followup with no target user → 400."""
    course = await _make_course(db_session, test_instructor, "RV0005")
    note = await _make_note(db_session, course, user_id=None)

    _act_as(test_instructor)
    r = await client.post(
        f"/api/learning-notes/{note.id}/review",
        json={"action_type": "assign_followup"},
        headers=_AUTH,
    )
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_student_follow_up_review_path(
    client, db_session, test_instructor, test_student
):
    """Student sees assigned follow-up, marks it viewed; a peer cannot view it."""
    course = await _make_course(db_session, test_instructor, "RV0006")
    note = await _make_note(db_session, course, user_id=test_student.id)

    db_session.add(
        Enrollment(course_id=course.id, user_id=test_student.id, role="student")
    )
    follow_up = FollowUpAction(
        learning_note_id=note.id,
        course_id=course.id,
        user_id=test_student.id,
        action_type="follow_up",
        assignment_status="assigned",
        assigned_by=test_instructor.id,
    )
    db_session.add(follow_up)
    await db_session.commit()
    await db_session.refresh(follow_up)

    # Student lists their Review Path.
    _act_as(test_student)
    r = await client.get(
        f"/api/users/me/courses/{course.id}/follow-ups", headers=_AUTH
    )
    assert r.status_code == 200, r.text
    ids = [item["id"] for item in r.json()["data"]]
    assert str(follow_up.id) in ids

    # Student marks it viewed.
    r = await client.post(
        f"/api/follow-ups/{follow_up.id}/viewed", headers=_AUTH
    )
    assert r.status_code == 200, r.text
    await db_session.refresh(follow_up)
    assert follow_up.assignment_status == "viewed"

    # A different student cannot view someone else's follow-up.
    other_student = User(
        better_auth_id="dev_student_002",
        email="student2@connect.ust.hk",
        full_name="Other Student",
        role="student",
    )
    db_session.add(other_student)
    await db_session.commit()
    await db_session.refresh(other_student)

    _act_as(other_student)
    r = await client.post(
        f"/api/follow-ups/{follow_up.id}/viewed", headers=_AUTH
    )
    assert r.status_code == 404, r.text
