"""P6 B3 — student follow-up action detail + revisit link.

Exercises ``app/api/review.py::follow_up_detail`` — ``GET /users/me/follow-ups/{id}``:

- owner-scoped by ``user_id`` (404 masks another student's row);
- merges the follow-up (``action_type``/``target_kind``/``target_id``/
  ``assignment_status``/``due_at``) with its linked ``LearningNote``'s **reviewed**
  fields ONLY (``observed_signal`` / instructor-``reviewed``/``edited``
  ``draft_interpretation`` / ``limitation_note``);
- a ``draft``/``queued`` note's interpretation is NEVER exposed (Core §0.2,
  Decision 6);
- surfaces the linked ``OutcomeCheck.status`` (the "did it move" state) when one
  exists;
- a ``suggested`` (not-yet-``assigned``) follow-up returns the waiting-for-feedback
  shape with no action content;
- a ``checkpoint`` target carries the P3 ``revisit-response`` link.

Auth is swapped per request via ``app.dependency_overrides`` (mirrors
``test_follow_up_work_item_seam.py``).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.api.deps import get_current_user
from app.main import app
from app.models import FollowUpAction, LearningNote, OutcomeCheck
from app.models.course import Course, Enrollment
from app.models.user import User

_AUTH = {"Authorization": "Bearer test-token"}


def _act_as(user: User) -> None:
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


async def _enroll(db, course, student, *, status="active") -> None:
    db.add(
        Enrollment(
            course_id=course.id,
            user_id=student.id,
            role="student",
            status=status,
        )
    )
    await db.commit()


async def _make_note(db, course, *, user_id, review_status="reviewed") -> LearningNote:
    note = LearningNote(
        course_id=course.id,
        user_id=user_id,
        observed_signal="missed 3/5 prompts on tone sandhi",
        draft_interpretation="You tend to drop the third tone before a fourth.",
        limitation_note="Based on 5 prompts only.",
        review_status=review_status,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


async def _make_follow_up(
    db,
    course,
    note,
    *,
    user_id,
    assignment_status="assigned",
    target_kind=None,
    target_id=None,
    action_type="practice",
    due_at=None,
) -> FollowUpAction:
    fua = FollowUpAction(
        learning_note_id=note.id if note is not None else None,
        course_id=course.id,
        user_id=user_id,
        action_type=action_type,
        target_kind=target_kind,
        target_id=target_id,
        assignment_status=assignment_status,
        due_at=due_at,
    )
    db.add(fua)
    await db.commit()
    await db.refresh(fua)
    return fua


@pytest.mark.asyncio
async def test_reviewed_follow_up_detail_exposes_reviewed_note_fields(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor, "FD0001")
    await _enroll(db_session, course, test_student)
    note = await _make_note(db_session, course, user_id=test_student.id)
    due = (datetime.now(timezone.utc) + timedelta(days=2)).replace(microsecond=0)
    fua = await _make_follow_up(
        db_session, course, note, user_id=test_student.id, due_at=due
    )

    _act_as(test_student)
    r = await client.get(f"/api/users/me/follow-ups/{fua.id}", headers=_AUTH)
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    assert data["id"] == str(fua.id)
    assert data["course_id"] == str(course.id)
    assert data["action_type"] == "practice"
    assert data["assignment_status"] == "assigned"
    assert data["waiting_for_review"] is False
    # reviewed note fields surfaced
    assert data["observed_signal"] == note.observed_signal
    assert data["draft_interpretation"] == note.draft_interpretation
    assert data["limitation_note"] == note.limitation_note
    # no outcome yet
    assert data["outcome_status"] is None
    # not a checkpoint target → no revisit link
    assert data["revisit"] is None


@pytest.mark.asyncio
async def test_draft_note_interpretation_never_exposed(
    client, db_session, test_instructor, test_student
):
    """Decision 6 / Core §0.2 — an unreviewed note's content is not shown."""
    course = await _make_course(db_session, test_instructor, "FD0002")
    await _enroll(db_session, course, test_student)
    note = await _make_note(
        db_session, course, user_id=test_student.id, review_status="draft"
    )
    fua = await _make_follow_up(
        db_session, course, note, user_id=test_student.id
    )

    _act_as(test_student)
    r = await client.get(f"/api/users/me/follow-ups/{fua.id}", headers=_AUTH)
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    assert data["draft_interpretation"] is None
    assert data["observed_signal"] is None
    assert data["limitation_note"] is None
    assert data["waiting_for_review"] is True


@pytest.mark.asyncio
async def test_suggested_follow_up_returns_waiting_shape(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor, "FD0003")
    await _enroll(db_session, course, test_student)
    note = await _make_note(
        db_session, course, user_id=test_student.id, review_status="draft"
    )
    fua = await _make_follow_up(
        db_session,
        course,
        note,
        user_id=test_student.id,
        assignment_status="suggested",
    )

    _act_as(test_student)
    r = await client.get(f"/api/users/me/follow-ups/{fua.id}", headers=_AUTH)
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    assert data["assignment_status"] == "suggested"
    assert data["waiting_for_review"] is True
    # no action content in the waiting shape
    assert data["observed_signal"] is None
    assert data["draft_interpretation"] is None
    assert data["revisit"] is None


@pytest.mark.asyncio
async def test_outcome_status_surfaced_when_present(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor, "FD0004")
    await _enroll(db_session, course, test_student)
    note = await _make_note(db_session, course, user_id=test_student.id)
    fua = await _make_follow_up(
        db_session,
        course,
        note,
        user_id=test_student.id,
        assignment_status="completed",
    )
    db_session.add(
        OutcomeCheck(
            course_id=course.id,
            user_id=test_student.id,
            learning_note_id=note.id,
            follow_up_action_id=fua.id,
            status="improved",
        )
    )
    await db_session.commit()

    _act_as(test_student)
    r = await client.get(f"/api/users/me/follow-ups/{fua.id}", headers=_AUTH)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["outcome_status"] == "improved"


@pytest.mark.asyncio
async def test_checkpoint_target_carries_revisit_link(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor, "FD0005")
    await _enroll(db_session, course, test_student)
    note = await _make_note(db_session, course, user_id=test_student.id)
    checkpoint_id = uuid.uuid4()
    fua = await _make_follow_up(
        db_session,
        course,
        note,
        user_id=test_student.id,
        action_type="revisit",
        target_kind="checkpoint",
        target_id=checkpoint_id,
    )

    _act_as(test_student)
    r = await client.get(f"/api/users/me/follow-ups/{fua.id}", headers=_AUTH)
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    assert data["revisit"] is not None
    assert data["revisit"]["checkpoint_id"] == str(checkpoint_id)
    assert data["revisit"]["revisit_path"] == (
        f"/api/checkpoints/{checkpoint_id}/revisit-response"
    )


@pytest.mark.asyncio
async def test_other_students_follow_up_is_404(
    client, db_session, test_instructor, test_student
):
    """Owner-scoped: another student's row is masked as 404."""
    other = User(
        better_auth_id="dev_student_002",
        email="other@connect.ust.hk",
        full_name="Other Student",
        role="student",
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)

    course = await _make_course(db_session, test_instructor, "FD0006")
    note = await _make_note(db_session, course, user_id=other.id)
    fua = await _make_follow_up(db_session, course, note, user_id=other.id)

    _act_as(test_student)
    r = await client.get(f"/api/users/me/follow-ups/{fua.id}", headers=_AUTH)
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_missing_follow_up_is_404(
    client, db_session, test_student
):
    _act_as(test_student)
    r = await client.get(
        f"/api/users/me/follow-ups/{uuid.uuid4()}", headers=_AUTH
    )
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_active_enrolled_owner_gets_200(
    client, db_session, test_instructor, test_student
):
    """LOW-1: an owner with an ACTIVE enrollment reads their own follow-up (200)."""
    course = await _make_course(db_session, test_instructor, "FD0007")
    await _enroll(db_session, course, test_student, status="active")
    note = await _make_note(db_session, course, user_id=test_student.id)
    fua = await _make_follow_up(db_session, course, note, user_id=test_student.id)

    _act_as(test_student)
    r = await client.get(f"/api/users/me/follow-ups/{fua.id}", headers=_AUTH)
    assert r.status_code == 200, r.text


@pytest.mark.parametrize(
    ("bad_status", "code"),
    [("pending", "FD0P01"), ("rejected", "FD0R01")],
)
@pytest.mark.asyncio
async def test_non_active_enrollment_owner_is_403(
    client, db_session, test_instructor, test_student, bad_status, code
):
    """LOW-1: a dropped/pending/rejected owner is refused (403) even for their
    OWN row — the reviewed note content stays gated on active enrollment."""
    course = await _make_course(db_session, test_instructor, code)
    await _enroll(db_session, course, test_student, status=bad_status)
    note = await _make_note(db_session, course, user_id=test_student.id)
    fua = await _make_follow_up(db_session, course, note, user_id=test_student.id)

    _act_as(test_student)
    r = await client.get(f"/api/users/me/follow-ups/{fua.id}", headers=_AUTH)
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_no_enrollment_owner_is_403(
    client, db_session, test_instructor, test_student
):
    """LOW-1: an owner with NO enrollment row is refused (403)."""
    course = await _make_course(db_session, test_instructor, "FD0008")
    note = await _make_note(db_session, course, user_id=test_student.id)
    fua = await _make_follow_up(db_session, course, note, user_id=test_student.id)

    _act_as(test_student)
    r = await client.get(f"/api/users/me/follow-ups/{fua.id}", headers=_AUTH)
    assert r.status_code == 403, r.text


# ----- POST /follow-ups/{id}/viewed — verify_enrollment defense-in-depth -----


@pytest.mark.asyncio
async def test_viewed_active_owner_succeeds(
    client, db_session, test_instructor, test_student
):
    """An active-enrolled owner can mark their own follow-up viewed (200)."""
    course = await _make_course(db_session, test_instructor, "FDV001")
    await _enroll(db_session, course, test_student, status="active")
    note = await _make_note(db_session, course, user_id=test_student.id)
    fua = await _make_follow_up(db_session, course, note, user_id=test_student.id)

    _act_as(test_student)
    r = await client.post(f"/api/follow-ups/{fua.id}/viewed", headers=_AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["assignment_status"] == "viewed"


@pytest.mark.parametrize("bad_status", ["pending", "rejected"])
@pytest.mark.asyncio
async def test_viewed_non_active_owner_is_403(
    client, db_session, test_instructor, test_student, bad_status
):
    """Fix 3: a dropped/pending/rejected owner is refused (403) even for their
    OWN row, and the follow-up is NOT flipped to viewed."""
    course = await _make_course(db_session, test_instructor, f"FDV{bad_status[:3]}")
    await _enroll(db_session, course, test_student, status=bad_status)
    note = await _make_note(db_session, course, user_id=test_student.id)
    fua = await _make_follow_up(db_session, course, note, user_id=test_student.id)

    _act_as(test_student)
    r = await client.post(f"/api/follow-ups/{fua.id}/viewed", headers=_AUTH)
    assert r.status_code == 403, r.text
    await db_session.refresh(fua)
    assert fua.assignment_status == "assigned"


@pytest.mark.asyncio
async def test_viewed_other_students_row_is_404(
    client, db_session, test_instructor, test_student
):
    """Owner-scoped: another student's row is masked as 404 (before enrollment)."""
    other = User(
        better_auth_id="dev_student_003", email="other3@connect.ust.hk",
        full_name="Other 3", role="student",
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)

    course = await _make_course(db_session, test_instructor, "FDV004")
    note = await _make_note(db_session, course, user_id=other.id)
    fua = await _make_follow_up(db_session, course, note, user_id=other.id)

    _act_as(test_student)
    r = await client.post(f"/api/follow-ups/{fua.id}/viewed", headers=_AUTH)
    assert r.status_code == 404, r.text
