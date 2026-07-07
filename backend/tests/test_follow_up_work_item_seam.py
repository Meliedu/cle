"""P6 B1 — reviewed follow-up writes a `follow_up` work_item (transactional seam).

Exercises ``app/api/review.py::review_learning_note``: when an instructor review
assigns a follow-up to a STUDENT-scoped note, the follow-up rides the endpoint's
single commit together with a ``follow_up`` work_item (on the shared spine) and a
per-student ``follow_up_assigned`` progress row — all atomically. A cohort note
(no target) still 400s and writes NO work_item; the item surfaces on the student
checklist through ``checklist.py::_build_checklist``.

Auth is swapped per request via ``app.dependency_overrides`` (mirrors
``test_learning_notes_review.py``). The ``client`` fixture owns the ``get_db``
override; tests only (re)assign ``get_current_user``.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.api.deps import get_current_user
from app.main import app
from app.models import FollowUpAction, LearningNote
from app.models.course import Course, Enrollment
from app.models.user import User
from app.models.work_item import WorkItem, WorkItemProgress

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


async def _make_note(db, course: Course, *, user_id=None) -> LearningNote:
    note = LearningNote(
        course_id=course.id,
        user_id=user_id,
        observed_signal="missed 3/5 prompts on tone sandhi",
        draft_interpretation="AI draft interpretation",
        review_status="draft",
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


async def _enroll(db, course: Course, student: User) -> None:
    db.add(Enrollment(course_id=course.id, user_id=student.id, role="student"))
    await db.commit()


async def _work_items(db, source_id):
    return (
        await db.execute(
            select(WorkItem).where(WorkItem.source_id == source_id)
        )
    ).scalars().all()


@pytest.mark.asyncio
async def test_assign_followup_writes_follow_up_work_item_and_progress(
    client, db_session, test_instructor, test_student
):
    """assign_followup on a student note → a `follow_up` work_item + progress row."""
    course = await _make_course(db_session, test_instructor, "FW0001")
    note = await _make_note(db_session, course, user_id=test_student.id)

    _act_as(test_instructor)
    r = await client.post(
        f"/api/learning-notes/{note.id}/review",
        json={"action_type": "assign_followup"},
        headers=_AUTH,
    )
    assert r.status_code == 200, r.text

    follow_up = (
        await db_session.execute(
            select(FollowUpAction).where(FollowUpAction.learning_note_id == note.id)
        )
    ).scalar_one()

    rows = await _work_items(db_session, follow_up.id)
    assert len(rows) == 1
    wi = rows[0]
    assert wi.source_kind == "follow_up"
    assert wi.source_id == follow_up.id
    assert wi.course_id == course.id
    assert wi.required is True
    assert wi.score_bearing is False
    assert wi.created_by == test_instructor.id
    assert wi.due_at == follow_up.due_at

    progress = (
        await db_session.execute(
            select(WorkItemProgress).where(
                WorkItemProgress.work_item_id == wi.id,
                WorkItemProgress.user_id == test_student.id,
            )
        )
    ).scalar_one()
    assert progress.status == "follow_up_assigned"


@pytest.mark.asyncio
async def test_inline_follow_up_spec_due_at_flows_to_work_item(
    client, db_session, test_instructor, test_student
):
    """An inline follow-up spec's due_at is mirrored onto the work_item."""
    from datetime import datetime, timedelta, timezone

    course = await _make_course(db_session, test_instructor, "FW0002")
    note = await _make_note(db_session, course, user_id=test_student.id)

    due = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0)
    _act_as(test_instructor)
    r = await client.post(
        f"/api/learning-notes/{note.id}/review",
        json={
            "action_type": "assign_followup",
            "follow_up": {
                "action_type": "practice",
                "due_at": due.isoformat(),
            },
        },
        headers=_AUTH,
    )
    assert r.status_code == 200, r.text

    follow_up = (
        await db_session.execute(
            select(FollowUpAction).where(FollowUpAction.learning_note_id == note.id)
        )
    ).scalar_one()
    rows = await _work_items(db_session, follow_up.id)
    assert len(rows) == 1
    assert rows[0].due_at == due
    assert rows[0].close_at == due


@pytest.mark.asyncio
async def test_second_review_does_not_duplicate_work_item(
    client, db_session, test_instructor, test_student
):
    """Re-assigning a follow-up for the SAME note keeps exactly one work_item."""
    course = await _make_course(db_session, test_instructor, "FW0003")
    note = await _make_note(db_session, course, user_id=test_student.id)

    _act_as(test_instructor)
    for _ in range(2):
        r = await client.post(
            f"/api/learning-notes/{note.id}/review",
            json={"action_type": "assign_followup"},
            headers=_AUTH,
        )
        assert r.status_code == 200, r.text

    follow_ups = (
        await db_session.execute(
            select(FollowUpAction).where(FollowUpAction.learning_note_id == note.id)
        )
    ).scalars().all()
    # Guarded upstream: a re-review reuses the active follow-up (no duplicate).
    assert len(follow_ups) == 1

    rows = await _work_items(db_session, follow_ups[0].id)
    assert len(rows) == 1  # idempotent on (course, source_kind, source_id)

    progress = (
        await db_session.execute(
            select(WorkItemProgress).where(
                WorkItemProgress.work_item_id == rows[0].id
            )
        )
    ).scalars().all()
    assert len(progress) == 1


@pytest.mark.asyncio
async def test_cohort_note_400s_and_writes_no_work_item(
    client, db_session, test_instructor
):
    """A cohort note (user_id NULL, no target) 400s and writes NO work_item."""
    course = await _make_course(db_session, test_instructor, "FW0004")
    note = await _make_note(db_session, course, user_id=None)

    _act_as(test_instructor)
    r = await client.post(
        f"/api/learning-notes/{note.id}/review",
        json={"action_type": "assign_followup"},
        headers=_AUTH,
    )
    assert r.status_code == 400, r.text

    all_items = (
        await db_session.execute(
            select(WorkItem).where(WorkItem.course_id == course.id)
        )
    ).scalars().all()
    assert all_items == []


@pytest.mark.asyncio
async def test_assign_followup_rejects_unenrolled_spec_target(
    client, db_session, test_instructor, test_student
):
    """MEDIUM (access-control): an explicit ``spec.user_id`` that is NOT actively
    enrolled in the note's course is rejected (400) and writes NO FollowUpAction,
    work_item or progress row (verified on an INDEPENDENT connection)."""
    from tests.conftest import test_session_factory

    course = await _make_course(db_session, test_instructor, "FW0007")
    note = await _make_note(db_session, course, user_id=test_student.id)

    # An outsider who is NOT enrolled in the course.
    outsider = User(
        better_auth_id="dev_student_outsider",
        email="outsider@connect.ust.hk",
        full_name="Outsider",
        role="student",
    )
    db_session.add(outsider)
    await db_session.commit()
    await db_session.refresh(outsider)
    outsider_id = outsider.id
    course_id = course.id

    _act_as(test_instructor)
    r = await client.post(
        f"/api/learning-notes/{note.id}/review",
        json={
            "action_type": "assign_followup",
            "follow_up": {"action_type": "practice", "user_id": str(outsider_id)},
        },
        headers=_AUTH,
    )
    assert r.status_code == 400, r.text

    # Nothing persisted for the outsider — assert on an independent connection.
    async with test_session_factory() as verify:
        fus = (
            await verify.execute(
                select(FollowUpAction).where(FollowUpAction.user_id == outsider_id)
            )
        ).scalars().all()
        assert fus == []
        wis = (
            await verify.execute(
                select(WorkItem).where(WorkItem.course_id == course_id)
            )
        ).scalars().all()
        assert wis == []
        progress = (
            await verify.execute(
                select(WorkItemProgress).where(
                    WorkItemProgress.user_id == outsider_id
                )
            )
        ).scalars().all()
        assert progress == []


@pytest.mark.asyncio
async def test_assign_followup_enrolled_spec_target_succeeds(
    client, db_session, test_instructor, test_student
):
    """An explicit ``spec.user_id`` that IS actively enrolled still succeeds —
    existing behavior preserved (cohort note re-targeted at an enrolled student)."""
    course = await _make_course(db_session, test_instructor, "FW0008")
    note = await _make_note(db_session, course, user_id=None)  # cohort note
    await _enroll(db_session, course, test_student)  # active enrollment

    _act_as(test_instructor)
    r = await client.post(
        f"/api/learning-notes/{note.id}/review",
        json={
            "action_type": "assign_followup",
            "follow_up": {
                "action_type": "practice",
                "user_id": str(test_student.id),
            },
        },
        headers=_AUTH,
    )
    assert r.status_code == 200, r.text

    follow_up = (
        await db_session.execute(
            select(FollowUpAction).where(FollowUpAction.learning_note_id == note.id)
        )
    ).scalar_one()
    assert follow_up.user_id == test_student.id

    rows = await _work_items(db_session, follow_up.id)
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_pre_commit_failure_rolls_back_follow_up_work_item_and_progress(
    client, db_session, test_instructor, test_student, monkeypatch
):
    """A failure AFTER the seam upsert but BEFORE commit rolls back all three:
    the follow-up, its work_item and its progress row (one transaction)."""
    from tests.conftest import test_session_factory

    course = await _make_course(db_session, test_instructor, "FW0005")
    note = await _make_note(db_session, course, user_id=test_student.id)
    note_id = note.id
    course_id = course.id

    def _boom(*args, **kwargs):
        raise RuntimeError("boom after seam upsert, before commit")

    # `db.commit()` runs AFTER the follow-up flush + work_item + progress upsert;
    # patching it to raise keeps every seam write in the uncommitted transaction.
    monkeypatch.setattr(db_session, "commit", _boom)

    _act_as(test_instructor)
    with pytest.raises(RuntimeError, match="boom after seam upsert"):
        await client.post(
            f"/api/learning-notes/{note_id}/review",
            json={"action_type": "assign_followup"},
            headers=_AUTH,
        )

    # Verify COMMITTED state on an INDEPENDENT connection: nothing persisted.
    async with test_session_factory() as verify:
        fus = (
            await verify.execute(
                select(FollowUpAction).where(
                    FollowUpAction.learning_note_id == note_id
                )
            )
        ).scalars().all()
        assert fus == []
        wis = (
            await verify.execute(
                select(WorkItem).where(WorkItem.course_id == course_id)
            )
        ).scalars().all()
        assert wis == []
        progress = (
            await verify.execute(
                select(WorkItemProgress).where(
                    WorkItemProgress.user_id == test_student.id
                )
            )
        ).scalars().all()
        assert progress == []


@pytest.mark.asyncio
async def test_follow_up_item_appears_in_student_checklist(
    client, db_session, test_instructor, test_student
):
    """Integration: the `follow_up` work_item surfaces on GET /courses/{id}/checklist."""
    course = await _make_course(db_session, test_instructor, "FW0006")
    note = await _make_note(db_session, course, user_id=test_student.id)
    await _enroll(db_session, course, test_student)

    _act_as(test_instructor)
    r = await client.post(
        f"/api/learning-notes/{note.id}/review",
        json={"action_type": "assign_followup"},
        headers=_AUTH,
    )
    assert r.status_code == 200, r.text

    _act_as(test_student)
    r = await client.get(
        f"/api/courses/{course.id}/checklist", headers=_AUTH
    )
    assert r.status_code == 200, r.text
    items = r.json()["data"]
    follow_up_items = [i for i in items if i["source_kind"] == "follow_up"]
    assert len(follow_up_items) == 1
    assert follow_up_items[0]["status"] == "follow_up_assigned"
