"""B7 — signal detail + evidence source view (pure-read reshape).

Security-sensitive (Decision 8, id never trusted): both endpoints resolve the
row, RE-DERIVE its ``course_id``, and re-apply the owner/enrollment guard —
404 on any mismatch, no existence leak. A student sees ONLY their own
``reviewed`` signal (a ``draft``/``queued`` note collapses to the designed
waiting shape with NO AI content, Core §0.2); an instructor sees any signal in
an OWNED course, including cohort (``user_id IS NULL``) notes.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.api.deps import get_current_user
from app.main import app


async def _make_course(db_session, instructor):
    from app.models import Course
    course = Course(
        instructor_id=instructor.id,
        name="C", language="english", enroll_code=uuid.uuid4().hex[:8].upper(),
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


async def _make_user(db_session, role):
    from app.models import User
    u = User(
        better_auth_id=f"dev_{role}_{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@{'ust.hk' if role == 'instructor' else 'connect.ust.hk'}",
        full_name=f"Test {role}",
        role=role,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


async def _enroll(db_session, course, student, status="active"):
    from app.models import Enrollment
    db_session.add(
        Enrollment(
            course_id=course.id, user_id=student.id, role="student", status=status
        )
    )
    await db_session.commit()


async def _add_note(
    db_session,
    course,
    user_id,
    review_status,
    *,
    source_event_ids=None,
    context_anchor=None,
):
    from app.models import LearningNote
    n = LearningNote(
        course_id=course.id,
        user_id=user_id,
        observed_signal="Struggled with tone 3",
        draft_interpretation="AI: likely tone confusion",
        limitation_note="based on a single attempt",
        evidence_category="concept_weakness",
        review_status=review_status,
        context_anchor=context_anchor,
        source_event_ids=source_event_ids or [],
    )
    db_session.add(n)
    await db_session.commit()
    await db_session.refresh(n)
    return n


async def _add_event(db_session, course, user):
    from app.models import LearningEvent
    now = datetime.now(timezone.utc)
    ev = LearningEvent(
        course_id=course.id,
        user_id=user.id,
        source_kind="checkpoint",
        source_id=uuid.uuid4(),
        stage="during_class",
        event_type="attempt",
        value={"score": 2, "max": 5},
        visibility_scope="instructor",
        occurred_at=now,
    )
    db_session.add(ev)
    await db_session.commit()
    await db_session.refresh(ev)
    return ev


def _headers():
    return {"Authorization": "Bearer test-token"}


# ---------------------------------------------------------------------------
# GET /signals/{id}
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_student_sees_own_reviewed_signal_with_content(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)
    note = await _add_note(
        db_session, course, test_student.id, "reviewed",
        context_anchor={"concept": "tone3"},
    )

    app.dependency_overrides[get_current_user] = lambda: test_student
    try:
        r = await client.get(f"/api/signals/{note.id}", headers=_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["waiting_for_review"] is False
        assert data["review_status"] == "reviewed"
        assert data["observed_signal"] == "Struggled with tone 3"
        assert data["draft_interpretation"] == "AI: likely tone confusion"
        assert data["limitation_note"] == "based on a single attempt"
        assert data["context_anchor"] == {"concept": "tone3"}
        assert data["user_id"] == str(test_student.id)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_student_own_draft_signal_is_waiting_shape_no_content(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)
    note = await _add_note(
        db_session, course, test_student.id, "draft",
        context_anchor={"concept": "tone3"},
    )

    app.dependency_overrides[get_current_user] = lambda: test_student
    try:
        r = await client.get(f"/api/signals/{note.id}", headers=_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        # Waiting shape: discriminator flipped, AI content withheld (Core §0.2).
        assert data["waiting_for_review"] is True
        assert data["review_status"] == "draft"
        assert data["observed_signal"] is None
        assert data["draft_interpretation"] is None
        assert data["limitation_note"] is None
        assert data["context_anchor"] is None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_student_queued_signal_is_waiting_shape(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)
    note = await _add_note(db_session, course, test_student.id, "queued")

    app.dependency_overrides[get_current_user] = lambda: test_student
    try:
        r = await client.get(f"/api/signals/{note.id}", headers=_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["waiting_for_review"] is True
        assert data["observed_signal"] is None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_student_cannot_see_another_students_signal_404(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    other = await _make_user(db_session, "student")
    await _enroll(db_session, course, test_student)
    await _enroll(db_session, course, other)
    note = await _add_note(db_session, course, other.id, "reviewed")

    app.dependency_overrides[get_current_user] = lambda: test_student
    try:
        r = await client.get(f"/api/signals/{note.id}", headers=_headers())
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_student_cannot_see_cohort_signal_404(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)
    # Cohort note: user_id IS NULL — not "the student's own".
    note = await _add_note(db_session, course, None, "reviewed")

    app.dependency_overrides[get_current_user] = lambda: test_student
    try:
        r = await client.get(f"/api/signals/{note.id}", headers=_headers())
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_student_archived_own_signal_404(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)
    note = await _add_note(db_session, course, test_student.id, "archived")

    app.dependency_overrides[get_current_user] = lambda: test_student
    try:
        r = await client.get(f"/api/signals/{note.id}", headers=_headers())
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_instructor_sees_any_owned_signal_including_cohort(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)
    # A cohort note AND a still-draft note — instructor sees both, with content.
    cohort = await _add_note(db_session, course, None, "draft")
    student_note = await _add_note(db_session, course, test_student.id, "reviewed")

    app.dependency_overrides[get_current_user] = lambda: test_instructor
    try:
        r1 = await client.get(f"/api/signals/{cohort.id}", headers=_headers())
        assert r1.status_code == 200
        d1 = r1.json()["data"]
        assert d1["user_id"] is None
        assert d1["observed_signal"] == "Struggled with tone 3"

        r2 = await client.get(f"/api/signals/{student_note.id}", headers=_headers())
        assert r2.status_code == 200
        assert r2.json()["data"]["draft_interpretation"] == "AI: likely tone confusion"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_instructor_cannot_see_signal_in_unowned_course_404(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)
    note = await _add_note(db_session, course, test_student.id, "reviewed")
    other_instructor = await _make_user(db_session, "instructor")

    app.dependency_overrides[get_current_user] = lambda: other_instructor
    try:
        r = await client.get(f"/api/signals/{note.id}", headers=_headers())
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_signal_not_found_404(
    client, db_session, test_instructor
):
    app.dependency_overrides[get_current_user] = lambda: test_instructor
    try:
        r = await client.get(f"/api/signals/{uuid.uuid4()}", headers=_headers())
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /evidence/{id}/source
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_student_sees_own_event_source_with_anchor(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)
    ev = await _add_event(db_session, course, test_student)
    # A reviewed note citing this event carries the "where it came from" anchor.
    await _add_note(
        db_session, course, test_student.id, "reviewed",
        source_event_ids=[str(ev.id)],
        context_anchor={"stage": "during_class", "concept": "tone3"},
    )

    app.dependency_overrides[get_current_user] = lambda: test_student
    try:
        r = await client.get(f"/api/evidence/{ev.id}/source", headers=_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["source_kind"] == "checkpoint"
        assert data["stage"] == "during_class"
        assert data["value"] == {"score": 2, "max": 5}
        assert data["source_id"] == str(ev.source_id)
        assert data["context_anchor"] == {"stage": "during_class", "concept": "tone3"}
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_student_event_source_draft_note_anchor_withheld(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)
    ev = await _add_event(db_session, course, test_student)
    # Only an UNREVIEWED (draft) note cites the event — its anchor must not leak.
    await _add_note(
        db_session, course, test_student.id, "draft",
        source_event_ids=[str(ev.id)],
        context_anchor={"concept": "tone3"},
    )

    app.dependency_overrides[get_current_user] = lambda: test_student
    try:
        r = await client.get(f"/api/evidence/{ev.id}/source", headers=_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["source_kind"] == "checkpoint"
        assert data["context_anchor"] is None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_student_cannot_see_another_students_event_404(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    other = await _make_user(db_session, "student")
    await _enroll(db_session, course, test_student)
    await _enroll(db_session, course, other)
    ev = await _add_event(db_session, course, other)

    app.dependency_overrides[get_current_user] = lambda: test_student
    try:
        r = await client.get(f"/api/evidence/{ev.id}/source", headers=_headers())
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_instructor_sees_owned_event_source(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)
    ev = await _add_event(db_session, course, test_student)
    await _add_note(
        db_session, course, test_student.id, "reviewed",
        source_event_ids=[str(ev.id)],
        context_anchor={"concept": "tone3"},
    )

    app.dependency_overrides[get_current_user] = lambda: test_instructor
    try:
        r = await client.get(f"/api/evidence/{ev.id}/source", headers=_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["user_id"] == str(test_student.id)
        assert data["context_anchor"] == {"concept": "tone3"}
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_instructor_cannot_see_event_in_unowned_course_404(
    client, db_session, test_instructor, test_student
):
    course = await _make_course(db_session, test_instructor)
    await _enroll(db_session, course, test_student)
    ev = await _add_event(db_session, course, test_student)
    other_instructor = await _make_user(db_session, "instructor")

    app.dependency_overrides[get_current_user] = lambda: other_instructor
    try:
        r = await client.get(f"/api/evidence/{ev.id}/source", headers=_headers())
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_evidence_source_not_found_404(
    client, db_session, test_instructor
):
    app.dependency_overrides[get_current_user] = lambda: test_instructor
    try:
        r = await client.get(
            f"/api/evidence/{uuid.uuid4()}/source", headers=_headers()
        )
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()
