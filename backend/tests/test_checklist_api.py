"""P4 B6 — checklist router: student read + next-action + teacher manager.

Covers ``app/api/checklist.py``:

* ``GET /courses/{id}/checklist`` (student, enrollment-scoped via
  ``verify_enrollment``) — the course's non-deleted ``work_items`` merged with
  the CALLER'S OWN ``work_item_progress``, ordered by ``due_at`` then
  ``visible_from``. For pre-backfill checkpoint items with no progress row, the
  per-student status is DERIVED from ``checkpoint_responses`` (Decision 4).
* ``GET /courses/{id}/next-action`` — the single next ``pending``/``in_progress``
  item by ``due_at`` (Decision 7), or ``null``.
* Teacher manager (owner-guarded): ``GET /courses/{id}/work-items`` (no
  progress), ``POST /courses/{id}/work-items`` (manual add), ``PATCH
  /work-items/{id}`` (reorder/required/title), ``DELETE /work-items/{id}``
  (soft-remove).
* A non-enrolled user → 403; a non-owner teacher on manager routes → 404.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.main import app
from app.models import Course, Enrollment, User
from app.models.checkpoint import Checkpoint, CheckpointCard, CheckpointResponse
from app.models.work_item import WorkItem, WorkItemProgress


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def owned_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="Checklist Course", language="english",
        instructor_id=logged_in_user.id, enroll_code="CHKL0001",
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
        better_auth_id="chkl_student_01", email="chklstudent@connect.ust.hk",
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


async def _make_work_item(
    db_session: AsyncSession,
    course: Course,
    author: User,
    *,
    source_kind: str = "material",
    source_id: uuid.UUID | None = None,
    title: str = "Item",
    required: bool = True,
    score_bearing: bool = False,
    due_at: datetime | None = None,
    visible_from: datetime | None = None,
    deleted: bool = False,
) -> WorkItem:
    wi = WorkItem(
        course_id=course.id,
        source_kind=source_kind,
        source_id=source_id or uuid.uuid4(),
        title=title,
        required=required,
        score_bearing=score_bearing,
        due_at=due_at,
        close_at=due_at,
        visible_from=visible_from,
        created_by=author.id,
    )
    if deleted:
        wi.deleted_at = _utcnow()
    db_session.add(wi)
    await db_session.commit()
    await db_session.refresh(wi)
    return wi


async def _set_progress(
    db_session: AsyncSession, wi: WorkItem, user: User, status: str
) -> None:
    db_session.add(
        WorkItemProgress(work_item_id=wi.id, user_id=user.id, status=status)
    )
    await db_session.commit()


def _client(db_session: AsyncSession, actor: User) -> AsyncClient:
    async def override_db():
        yield db_session

    async def override_user():
        return actor

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    return AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
        headers={"Authorization": "Bearer x"},
    )


# ----- student checklist -----


@pytest.mark.asyncio
async def test_checklist_merges_progress_and_orders_by_due_then_visible(
    db_session: AsyncSession, owned_course: Course, logged_in_user: User,
    enrolled_student: User,
):
    now = _utcnow()
    later = await _make_work_item(
        db_session, owned_course, logged_in_user, title="Later",
        due_at=now + timedelta(days=2),
    )
    sooner = await _make_work_item(
        db_session, owned_course, logged_in_user, title="Sooner",
        due_at=now + timedelta(days=1),
    )
    # Deleted item never appears.
    await _make_work_item(
        db_session, owned_course, logged_in_user, title="Gone", deleted=True,
    )
    await _set_progress(db_session, sooner, enrolled_student, "completed")

    async with _client(db_session, enrolled_student) as ac:
        r = await ac.get(f"/api/courses/{owned_course.id}/checklist")
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    assert [row["title"] for row in rows] == ["Sooner", "Later"]
    by_id = {row["id"]: row for row in rows}
    # Merged with the caller's own progress.
    assert by_id[str(sooner.id)]["status"] == "completed"
    # No progress row + non-checkpoint item → default pending.
    assert by_id[str(later.id)]["status"] == "pending"
    assert str(later.id) in by_id  # deleted item excluded implicitly
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_checklist_uses_only_callers_own_progress(
    db_session: AsyncSession, owned_course: Course, logged_in_user: User,
    enrolled_student: User,
):
    """Another student's progress must not leak into the caller's checklist."""
    wi = await _make_work_item(db_session, owned_course, logged_in_user)
    other = User(
        better_auth_id="chkl_other", email="chklother@connect.ust.hk",
        full_name="Other", role="student",
    )
    db_session.add(other)
    await db_session.flush()
    db_session.add(
        Enrollment(
            course_id=owned_course.id, user_id=other.id,
            role="student", status="active",
        )
    )
    await db_session.commit()
    await _set_progress(db_session, wi, other, "completed")

    async with _client(db_session, enrolled_student) as ac:
        r = await ac.get(f"/api/courses/{owned_course.id}/checklist")
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    assert len(rows) == 1
    # The caller has no progress of their own → pending, not the other's completed.
    assert rows[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_checklist_pre_backfill_fallback_from_checkpoint_responses(
    db_session: AsyncSession, owned_course: Course, logged_in_user: User,
    enrolled_student: User,
):
    """A checkpoint work_item lacking a progress row derives status from the
    student's ``checkpoint_responses`` (Decision 4 — history isn't blank)."""
    now = _utcnow()
    cp = Checkpoint(
        course_id=owned_course.id, kind="session", title="Pre-backfill CP",
        status="closed", release_at=now - timedelta(days=2),
        close_at=now - timedelta(days=1), close_rule="manual",
    )
    db_session.add(cp)
    await db_session.flush()
    review = CheckpointCard(
        checkpoint_id=cp.id, position=0, kind="review_point", prompt="q1",
    )
    final = CheckpointCard(
        checkpoint_id=cp.id, position=1, kind="final_comments", prompt="q2",
    )
    db_session.add_all([review, final])
    await db_session.flush()
    # The student answered both live cards on time — but before B5 wired
    # progress writes, so NO work_item_progress row exists.
    db_session.add_all([
        CheckpointResponse(
            checkpoint_id=cp.id, card_id=review.id, user_id=enrolled_student.id,
            confidence=1, status="on_time",
        ),
        CheckpointResponse(
            checkpoint_id=cp.id, card_id=final.id, user_id=enrolled_student.id,
            text_response="ok", status="on_time",
        ),
    ])
    await db_session.commit()
    # The backfilled spine row (no progress).
    wi = await _make_work_item(
        db_session, owned_course, logged_in_user, source_kind="checkpoint",
        source_id=cp.id, title="Pre-backfill CP", due_at=cp.close_at,
    )

    async with _client(db_session, enrolled_student) as ac:
        r = await ac.get(f"/api/courses/{owned_course.id}/checklist")
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    by_id = {row["id"]: row for row in r.json()["data"]}
    # Answered every live card on time → completed (derived from responses).
    assert by_id[str(wi.id)]["status"] == "completed"


@pytest.mark.asyncio
async def test_checklist_non_enrolled_rejected(
    db_session: AsyncSession, owned_course: Course, logged_in_user: User,
):
    await _make_work_item(db_session, owned_course, logged_in_user)
    outsider = User(
        better_auth_id="chkl_outsider", email="chkloutsider@connect.ust.hk",
        full_name="Outsider", role="student",
    )
    db_session.add(outsider)
    await db_session.commit()
    async with _client(db_session, outsider) as ac:
        r = await ac.get(f"/api/courses/{owned_course.id}/checklist")
    app.dependency_overrides.clear()
    assert r.status_code == 403, r.text


# ----- next-action -----


@pytest.mark.asyncio
async def test_next_action_returns_soonest_pending(
    db_session: AsyncSession, owned_course: Course, logged_in_user: User,
    enrolled_student: User,
):
    now = _utcnow()
    done = await _make_work_item(
        db_session, owned_course, logged_in_user, title="Done",
        due_at=now + timedelta(days=1),
    )
    await _set_progress(db_session, done, enrolled_student, "completed")
    soonest = await _make_work_item(
        db_session, owned_course, logged_in_user, title="Do next",
        due_at=now + timedelta(days=2),
    )
    await _make_work_item(
        db_session, owned_course, logged_in_user, title="Later still",
        due_at=now + timedelta(days=3),
    )

    async with _client(db_session, enrolled_student) as ac:
        r = await ac.get(f"/api/courses/{owned_course.id}/next-action")
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data is not None
    assert data["id"] == str(soonest.id)
    assert data["title"] == "Do next"


@pytest.mark.asyncio
async def test_next_action_null_when_all_done(
    db_session: AsyncSession, owned_course: Course, logged_in_user: User,
    enrolled_student: User,
):
    wi = await _make_work_item(db_session, owned_course, logged_in_user)
    await _set_progress(db_session, wi, enrolled_student, "completed")

    async with _client(db_session, enrolled_student) as ac:
        r = await ac.get(f"/api/courses/{owned_course.id}/next-action")
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    assert r.json()["data"] is None


# ----- teacher manager -----


@pytest.mark.asyncio
async def test_teacher_list_work_items_no_progress(
    db_session: AsyncSession, owned_course: Course, logged_in_user: User,
    enrolled_student: User,
):
    wi = await _make_work_item(db_session, owned_course, logged_in_user, title="X")
    await _set_progress(db_session, wi, enrolled_student, "completed")

    async with _client(db_session, logged_in_user) as ac:
        r = await ac.get(f"/api/courses/{owned_course.id}/work-items")
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    assert len(rows) == 1
    assert rows[0]["id"] == str(wi.id)
    # Teacher manager view carries no per-student progress field.
    assert "status" not in rows[0]
    assert rows[0]["created_by"] == str(logged_in_user.id)


@pytest.mark.asyncio
async def test_teacher_create_work_item(
    db_session: AsyncSession, owned_course: Course, logged_in_user: User,
):
    due = _utcnow() + timedelta(days=1)
    async with _client(db_session, logged_in_user) as ac:
        r = await ac.post(
            f"/api/courses/{owned_course.id}/work-items",
            json={"title": "Read chapter 3", "due_at": due.isoformat()},
        )
    app.dependency_overrides.clear()

    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["title"] == "Read chapter 3"
    assert data["created_by"] == str(logged_in_user.id)
    row = (
        await db_session.execute(
            select(WorkItem).where(WorkItem.id == uuid.UUID(data["id"]))
        )
    ).scalar_one()
    assert row.course_id == owned_course.id
    assert row.deleted_at is None


@pytest.mark.asyncio
async def test_teacher_patch_work_item(
    db_session: AsyncSession, owned_course: Course, logged_in_user: User,
):
    wi = await _make_work_item(
        db_session, owned_course, logged_in_user, title="Old", required=True,
    )
    new_vis = _utcnow() + timedelta(days=5)
    async with _client(db_session, logged_in_user) as ac:
        r = await ac.patch(
            f"/api/work-items/{wi.id}",
            json={
                "title": "New title", "required": False,
                "visible_from": new_vis.isoformat(),
            },
        )
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["title"] == "New title"
    assert data["required"] is False
    await db_session.refresh(wi)
    assert wi.title == "New title"
    assert wi.required is False


@pytest.mark.asyncio
async def test_teacher_delete_soft_removes(
    db_session: AsyncSession, owned_course: Course, logged_in_user: User,
):
    wi = await _make_work_item(db_session, owned_course, logged_in_user)
    async with _client(db_session, logged_in_user) as ac:
        r = await ac.delete(f"/api/work-items/{wi.id}")
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    await db_session.refresh(wi)
    assert wi.deleted_at is not None


@pytest.mark.asyncio
async def test_non_owner_teacher_gets_404_on_manager_routes(
    db_session: AsyncSession, owned_course: Course, logged_in_user: User,
):
    wi = await _make_work_item(db_session, owned_course, logged_in_user)
    other_teacher = User(
        better_auth_id="chkl_teacher2", email="teacher2@ust.hk",
        full_name="Other Teacher", role="instructor",
    )
    db_session.add(other_teacher)
    await db_session.commit()

    async with _client(db_session, other_teacher) as ac:
        listing = await ac.get(f"/api/courses/{owned_course.id}/work-items")
        creating = await ac.post(
            f"/api/courses/{owned_course.id}/work-items",
            json={"title": "sneaky"},
        )
        patching = await ac.patch(
            f"/api/work-items/{wi.id}", json={"title": "hijack"}
        )
        deleting = await ac.delete(f"/api/work-items/{wi.id}")
    app.dependency_overrides.clear()

    assert listing.status_code == 404, listing.text
    assert creating.status_code == 404, creating.text
    assert patching.status_code == 404, patching.text
    assert deleting.status_code == 404, deleting.text
