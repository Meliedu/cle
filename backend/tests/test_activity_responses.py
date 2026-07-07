"""P5 B9 — student activity response submission (PARTICIPATION-ONLY seam).

Covers the student-facing half of the activity loop (spec §4.4, Decision 5):

* ``POST /activities/{id}/responses`` — enrollment-scoped via ``verify_enrollment``
  (active-only); upserts one row per ``(activity_id, user_id)`` (a resubmit
  updates in place), derives ``on_time``/``late`` from ``close_at``, writes
  ``work_item_progress`` on the response's OWN commit, and — for a
  ``comment_reaction`` activity — STACKS multiple reactions inside ``payload``.
  Only ``published``/``live`` activities accept responses.
* ``GET /activities/{id}/results`` — owner-guarded teacher evidence/aggregate.

The evidence seam is PARTICIPATION-ONLY (like attendance, P3): after the response
is committed a single ``LearningEvent`` (``stage='during_class'``,
``source_kind='activity'``) is written and **NEVER** an ``update_concept_mastery``
Task. The event write is best-effort: a failure there must never lose the
already-committed response or its progress row.
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
from app.models.activity import Activity, ActivityResponse
from app.models.evidence import LearningEvent
from app.models.task import Task
from app.models.work_item import WorkItem, WorkItemProgress


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def owned_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="Activity Responses", language="english",
        instructor_id=logged_in_user.id, enroll_code="ACTR0001",
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
        better_auth_id="actr_student_01", email="actrstudent@connect.ust.hk",
        full_name="Actr Student", role="student",
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


async def _seed_activity(db_session, course, **over) -> Activity:
    defaults = dict(
        course_id=course.id, format="swipe", title="Warm-up",
        config={"prompts": ["Agree or disagree?"]}, status="published",
    )
    defaults.update(over)
    act = Activity(**defaults)
    db_session.add(act)
    await db_session.commit()
    await db_session.refresh(act)
    return act


async def _make_work_item(
    db_session: AsyncSession, course: Course, act: Activity
) -> WorkItem:
    """The `activity` work_item the publish path (B8) would have created."""
    wi = WorkItem(
        course_id=course.id,
        source_kind="activity",
        source_id=act.id,
        title=act.title,
        required=act.score_bearing,
        score_bearing=act.score_bearing,
        due_at=act.due_at,
        close_at=act.close_at,
        created_by=course.instructor_id,
    )
    db_session.add(wi)
    await db_session.commit()
    await db_session.refresh(wi)
    return wi


async def _progress_rows(
    db_session: AsyncSession, wi_id: uuid.UUID
) -> list[WorkItemProgress]:
    return list(
        (
            await db_session.execute(
                select(WorkItemProgress).where(
                    WorkItemProgress.work_item_id == wi_id
                )
            )
        ).scalars().all()
    )


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


# ----- submit: basic upsert + progress -----

@pytest.mark.asyncio
async def test_submit_creates_response(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    act = await _seed_activity(db_session, owned_course)
    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.post(
            f"/api/activities/{act.id}/responses",
            json={"payload": {"prompt_index": 0, "direction": "left"}},
        )
        assert r.status_code in (200, 201), r.text
    app.dependency_overrides.clear()

    rows = (
        await db_session.execute(
            select(ActivityResponse).where(
                ActivityResponse.activity_id == act.id,
                ActivityResponse.user_id == enrolled_student.id,
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].payload == {"prompt_index": 0, "direction": "left"}
    assert rows[0].status == "on_time"


@pytest.mark.asyncio
async def test_submit_resubmit_upserts_in_place(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    # A swipe/vote resubmit REPLACES the payload in place (one row).
    act = await _seed_activity(db_session, owned_course, format="vote",
                               config={"options": ["A", "B"]})
    async with _student_client(db_session, enrolled_student) as ac:
        r1 = await ac.post(
            f"/api/activities/{act.id}/responses",
            json={"payload": {"choice": "A"}},
        )
        assert r1.status_code in (200, 201), r1.text
        r2 = await ac.post(
            f"/api/activities/{act.id}/responses",
            json={"payload": {"choice": "B"}},
        )
        assert r2.status_code in (200, 201), r2.text
    app.dependency_overrides.clear()

    rows = (
        await db_session.execute(
            select(ActivityResponse).where(
                ActivityResponse.activity_id == act.id,
                ActivityResponse.user_id == enrolled_student.id,
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].payload == {"choice": "B"}


@pytest.mark.asyncio
async def test_submit_comment_reaction_stacks(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    # comment_reaction STACKS successive reactions inside payload (§4.4).
    act = await _seed_activity(
        db_session, owned_course, format="comment_reaction",
        config={"reactions": ["👍", "❤️"]},
    )
    async with _student_client(db_session, enrolled_student) as ac:
        r1 = await ac.post(
            f"/api/activities/{act.id}/responses",
            json={"payload": {"reaction": "👍"}},
        )
        assert r1.status_code in (200, 201), r1.text
        r2 = await ac.post(
            f"/api/activities/{act.id}/responses",
            json={"payload": {"reaction": "❤️"}},
        )
        assert r2.status_code in (200, 201), r2.text
    app.dependency_overrides.clear()

    rows = (
        await db_session.execute(
            select(ActivityResponse).where(
                ActivityResponse.activity_id == act.id,
                ActivityResponse.user_id == enrolled_student.id,
            )
        )
    ).scalars().all()
    assert len(rows) == 1  # still one row (upsert)
    entries = rows[0].payload["entries"]
    assert entries == [{"reaction": "👍"}, {"reaction": "❤️"}]


@pytest.mark.asyncio
async def test_submit_writes_progress_completed(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    act = await _seed_activity(db_session, owned_course)
    wi = await _make_work_item(db_session, owned_course, act)
    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.post(
            f"/api/activities/{act.id}/responses",
            json={"payload": {"direction": "right"}},
        )
        assert r.status_code in (200, 201), r.text
    app.dependency_overrides.clear()

    rows = await _progress_rows(db_session, wi.id)
    assert len(rows) == 1
    assert rows[0].user_id == enrolled_student.id
    assert rows[0].status == "completed"


@pytest.mark.asyncio
async def test_submit_late_when_past_close_at(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    act = await _seed_activity(
        db_session, owned_course, close_at=_utcnow() - timedelta(minutes=5)
    )
    wi = await _make_work_item(db_session, owned_course, act)
    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.post(
            f"/api/activities/{act.id}/responses",
            json={"payload": {"direction": "left"}},
        )
        assert r.status_code in (200, 201), r.text
    app.dependency_overrides.clear()

    resp = (
        await db_session.execute(
            select(ActivityResponse).where(ActivityResponse.activity_id == act.id)
        )
    ).scalar_one()
    assert resp.status == "late"
    rows = await _progress_rows(db_session, wi.id)
    assert rows[0].status == "late"


@pytest.mark.asyncio
async def test_submit_missing_work_item_is_noop(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    # No work_item (unpublished-preview) — submission still succeeds, no 500.
    act = await _seed_activity(db_session, owned_course)
    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.post(
            f"/api/activities/{act.id}/responses",
            json={"payload": {"direction": "left"}},
        )
    app.dependency_overrides.clear()
    assert r.status_code in (200, 201), r.text
    prog = (
        await db_session.execute(
            select(WorkItemProgress).where(
                WorkItemProgress.user_id == enrolled_student.id
            )
        )
    ).scalars().all()
    assert prog == []


# ----- evidence seam: participation-only -----

@pytest.mark.asyncio
async def test_submit_writes_learning_event(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    act = await _seed_activity(db_session, owned_course)
    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.post(
            f"/api/activities/{act.id}/responses",
            json={"payload": {"direction": "right"}},
        )
        assert r.status_code in (200, 201), r.text
    app.dependency_overrides.clear()

    events = (
        await db_session.execute(
            select(LearningEvent).where(LearningEvent.course_id == owned_course.id)
        )
    ).scalars().all()
    assert len(events) == 1
    ev = events[0]
    assert ev.source_kind == "activity"
    assert ev.source_id == act.id
    assert ev.stage == "during_class"
    assert ev.user_id == enrolled_student.id


@pytest.mark.asyncio
async def test_submit_never_enqueues_mastery(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    # PARTICIPATION-ONLY: an activity submission NEVER enqueues mastery.
    act = await _seed_activity(db_session, owned_course)
    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.post(
            f"/api/activities/{act.id}/responses",
            json={"payload": {"direction": "left"}},
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
async def test_submit_progress_survives_evidence_failure(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User,
    monkeypatch,
):
    # Progress rides the RESPONSE's commit, NOT the best-effort evidence block.
    act = await _seed_activity(db_session, owned_course)
    wi = await _make_work_item(db_session, owned_course, act)
    act_id = act.id
    student_id = enrolled_student.id
    wi_id = wi.id

    async def _boom(*args, **kwargs):
        raise RuntimeError("evidence seam down")

    monkeypatch.setattr(
        "app.services.activity_responses.record_attempt_event", _boom
    )

    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.post(
            f"/api/activities/{act_id}/responses",
            json={"payload": {"direction": "left"}},
        )
    app.dependency_overrides.clear()
    assert r.status_code in (200, 201), r.text

    resp = (
        await db_session.execute(
            select(ActivityResponse).where(
                ActivityResponse.activity_id == act_id,
                ActivityResponse.user_id == student_id,
            )
        )
    ).scalar_one()
    assert resp.payload == {"direction": "left"}
    rows = await _progress_rows(db_session, wi_id)
    assert len(rows) == 1
    assert rows[0].status == "completed"


# ----- authz + gate -----

@pytest.mark.asyncio
async def test_submit_not_enrolled_403(
    db_session: AsyncSession, owned_course: Course
):
    act = await _seed_activity(db_session, owned_course)
    outsider = User(
        better_auth_id="actr_outsider", email="actroutsider@connect.ust.hk",
        full_name="Outsider", role="student",
    )
    db_session.add(outsider)
    await db_session.commit()
    async with _student_client(db_session, outsider) as ac:
        r = await ac.post(
            f"/api/activities/{act.id}/responses",
            json={"payload": {"direction": "left"}},
        )
    app.dependency_overrides.clear()
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_submit_draft_activity_rejected(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    act = await _seed_activity(db_session, owned_course, status="draft")
    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.post(
            f"/api/activities/{act.id}/responses",
            json={"payload": {"direction": "left"}},
        )
    app.dependency_overrides.clear()
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ACTIVITY_NOT_OPEN"


@pytest.mark.asyncio
async def test_submit_live_activity_accepted(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    act = await _seed_activity(db_session, owned_course, status="live")
    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.post(
            f"/api/activities/{act.id}/responses",
            json={"payload": {"direction": "left"}},
        )
    app.dependency_overrides.clear()
    assert r.status_code in (200, 201), r.text


@pytest.mark.asyncio
async def test_submit_progress_user_id_is_authenticated_caller(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    # A wrong-owner cannot write another student's row — the progress/response
    # user_id is the authenticated caller only.
    act = await _seed_activity(db_session, owned_course)
    wi = await _make_work_item(db_session, owned_course, act)

    other = User(
        better_auth_id="actr_student_02", email="actrstudent2@connect.ust.hk",
        full_name="Actr Student Two", role="student",
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
    await db_session.refresh(other)

    act_id = act.id
    async with _student_client(db_session, enrolled_student) as ac:
        await ac.post(
            f"/api/activities/{act_id}/responses",
            json={"payload": {"direction": "left"}},
        )
    app.dependency_overrides.clear()
    async with _student_client(db_session, other) as ac:
        await ac.post(
            f"/api/activities/{act_id}/responses",
            json={"payload": {"direction": "right"}},
        )
    app.dependency_overrides.clear()

    rows = await _progress_rows(db_session, wi.id)
    assert {row.user_id for row in rows} == {enrolled_student.id, other.id}
    assert len(rows) == 2


# ----- teacher results -----

@pytest.mark.asyncio
async def test_results_owner_view(
    async_client: AsyncClient, db_session: AsyncSession,
    owned_course: Course, enrolled_student: User,
):
    act = await _seed_activity(db_session, owned_course)
    # Seed one student submission directly (using the student client here would
    # clear the async_client fixture's dependency overrides).
    db_session.add(
        ActivityResponse(
            activity_id=act.id, user_id=enrolled_student.id,
            payload={"direction": "left"}, status="on_time",
        )
    )
    await db_session.commit()

    r = await async_client.get(f"/api/activities/{act.id}/results")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["activity_id"] == str(act.id)
    assert data["submission_count"] == 1
    assert len(data["responses"]) == 1


@pytest.mark.asyncio
async def test_results_non_owner_404(
    async_client: AsyncClient, db_session: AsyncSession
):
    other = User(
        better_auth_id="actr_other_instr", email="actrother@ust.hk",
        full_name="Other", role="instructor",
    )
    db_session.add(other)
    await db_session.flush()
    course = Course(
        name="Foreign", language="english",
        instructor_id=other.id, enroll_code="ACTRFOR1",
    )
    db_session.add(course)
    await db_session.commit()
    act = await _seed_activity(db_session, course)
    r = await async_client.get(f"/api/activities/{act.id}/results")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_results_student_forbidden(
    db_session: AsyncSession, owned_course: Course, enrolled_student: User
):
    act = await _seed_activity(db_session, owned_course)
    async with _student_client(db_session, enrolled_student) as ac:
        r = await ac.get(f"/api/activities/{act.id}/results")
    app.dependency_overrides.clear()
    assert r.status_code == 403
