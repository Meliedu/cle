"""P5 B8: activities.py router — teacher builder CRUD + gated publish.

Owner-guarded CRUD (a student gets 403, a non-owner instructor 404 so course
existence never leaks). ``config`` is shape-validated per ``format`` (swipe →
``prompts``, vote → ``options``, comment_reaction → ``reactions``). Publish runs
the activity status transition and, for a SCORE-BEARING activity, the shared
``assert_score_policy_complete`` gate (422 ``SCORE_POLICY_INCOMPLETE``) BEFORE
flipping state — else it writes an ``activity`` work_item transactionally +
idempotently. A participation-only activity publishes WITHOUT the gate.

Adapted to the real conftest fixtures (``async_client`` = ``logged_in_user``
instructor; ``db_session``). Mirrors ``test_checkpoints_api.py``.
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
from app.models.activity import Activity
from app.models.score import ScoreCategory
from app.models.work_item import WorkItem


@pytest_asyncio.fixture
async def owned_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    course = Course(
        name="Activity Test", language="english",
        instructor_id=logged_in_user.id, enroll_code="ACTV0001",
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
    cat = ScoreCategory(course_id=owned_course.id, name="Participation", sort=0)
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


def _swipe_body(**over):
    body = {
        "format": "swipe",
        "title": "Warm-up swipe",
        "config": {"prompts": ["Agree or disagree?", "Same or different?"]},
    }
    body.update(over)
    return body


def _work_items_for(db_session: AsyncSession, activity_id: uuid.UUID):
    return db_session.execute(
        select(WorkItem).where(WorkItem.source_id == activity_id)
    )


async def _seed_activity(db_session, course, **over):
    defaults = dict(
        course_id=course.id, format="swipe", title="Seeded",
        config={"prompts": ["A?"]}, status="draft",
    )
    defaults.update(over)
    act = Activity(**defaults)
    db_session.add(act)
    await db_session.commit()
    await db_session.refresh(act)
    return act


# ----- create -----

@pytest.mark.asyncio
async def test_create_swipe_activity(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course
):
    r = await async_client.post(
        f"/api/courses/{owned_course.id}/activities", json=_swipe_body()
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["format"] == "swipe"
    assert data["status"] == "draft"
    assert data["title"] == "Warm-up swipe"
    act = await db_session.get(Activity, uuid.UUID(data["id"]))
    assert act is not None
    assert act.course_id == owned_course.id


@pytest.mark.asyncio
async def test_create_swipe_bad_config_422(
    async_client: AsyncClient, owned_course: Course
):
    r = await async_client.post(
        f"/api/courses/{owned_course.id}/activities",
        json=_swipe_body(config={"options": ["x"]}),  # swipe needs `prompts`
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "ACTIVITY_CONFIG_INVALID"


@pytest.mark.asyncio
async def test_create_vote_requires_options(
    async_client: AsyncClient, owned_course: Course
):
    ok = await async_client.post(
        f"/api/courses/{owned_course.id}/activities",
        json={"format": "vote", "title": "Vote", "config": {"options": ["A", "B"]}},
    )
    assert ok.status_code == 201, ok.text
    bad = await async_client.post(
        f"/api/courses/{owned_course.id}/activities",
        json={"format": "vote", "title": "Vote", "config": {"prompts": ["A"]}},
    )
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "ACTIVITY_CONFIG_INVALID"


@pytest.mark.asyncio
async def test_create_comment_reaction_requires_reactions(
    async_client: AsyncClient, owned_course: Course
):
    ok = await async_client.post(
        f"/api/courses/{owned_course.id}/activities",
        json={
            "format": "comment_reaction",
            "title": "React",
            "config": {"reactions": ["👍", "❤️"]},
        },
    )
    assert ok.status_code == 201, ok.text
    bad = await async_client.post(
        f"/api/courses/{owned_course.id}/activities",
        json={"format": "comment_reaction", "title": "React", "config": {}},
    )
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "ACTIVITY_CONFIG_INVALID"


@pytest.mark.asyncio
async def test_create_student_forbidden(
    db_session: AsyncSession, owned_course: Course
):
    student = User(
        better_auth_id="actv_student_01", email="actvstudent@connect.ust.hk",
        full_name="Student", role="student",
    )
    db_session.add(student)
    await db_session.commit()

    async def override_db():
        yield db_session

    async def override_user():
        return student

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer x"},
        ) as ac:
            r = await ac.post(
                f"/api/courses/{owned_course.id}/activities", json=_swipe_body()
            )
            assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_non_owner_404(
    async_client: AsyncClient, db_session: AsyncSession
):
    other = User(
        better_auth_id="actv_other_instr", email="actvother@ust.hk",
        full_name="Other", role="instructor",
    )
    db_session.add(other)
    await db_session.flush()
    course = Course(
        name="Foreign", language="english",
        instructor_id=other.id, enroll_code="ACTVFOR1",
    )
    db_session.add(course)
    await db_session.commit()
    r = await async_client.post(
        f"/api/courses/{course.id}/activities", json=_swipe_body()
    )
    assert r.status_code == 404


# ----- list / get -----

@pytest.mark.asyncio
async def test_list_activities(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course
):
    await _seed_activity(db_session, owned_course, title="One")
    await _seed_activity(db_session, owned_course, title="Two", format="vote",
                         config={"options": ["a"]})
    r = await async_client.get(f"/api/courses/{owned_course.id}/activities")
    assert r.status_code == 200
    titles = sorted(a["title"] for a in r.json()["data"])
    assert titles == ["One", "Two"]


@pytest.mark.asyncio
async def test_get_activity(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course
):
    act = await _seed_activity(db_session, owned_course)
    r = await async_client.get(f"/api/activities/{act.id}")
    assert r.status_code == 200
    assert r.json()["data"]["id"] == str(act.id)


@pytest.mark.asyncio
async def test_get_activity_non_owner_404(
    async_client: AsyncClient, db_session: AsyncSession
):
    other = User(
        better_auth_id="actv_other_2", email="actvother2@ust.hk",
        full_name="Other", role="instructor",
    )
    db_session.add(other)
    await db_session.flush()
    course = Course(
        name="Foreign2", language="english",
        instructor_id=other.id, enroll_code="ACTVFOR2",
    )
    db_session.add(course)
    await db_session.commit()
    act = await _seed_activity(db_session, course)
    r = await async_client.get(f"/api/activities/{act.id}")
    assert r.status_code == 404


# ----- patch -----

@pytest.mark.asyncio
async def test_patch_activity(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course
):
    act = await _seed_activity(db_session, owned_course, title="Old")
    r = await async_client.patch(
        f"/api/activities/{act.id}",
        json={"title": "New", "config": {"prompts": ["Q1", "Q2"]}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["title"] == "New"
    await db_session.refresh(act)
    assert act.title == "New"
    assert act.config == {"prompts": ["Q1", "Q2"]}


@pytest.mark.asyncio
async def test_patch_bad_config_422(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course
):
    act = await _seed_activity(db_session, owned_course)
    r = await async_client.patch(
        f"/api/activities/{act.id}", json={"config": {"nope": True}}
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "ACTIVITY_CONFIG_INVALID"


# ----- delete -----

@pytest.mark.asyncio
async def test_delete_activity_soft_deletes(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course
):
    act = await _seed_activity(db_session, owned_course)
    r = await async_client.delete(f"/api/activities/{act.id}")
    assert r.status_code == 200
    await db_session.refresh(act)
    assert act.deleted_at is not None


# ----- publish: participation-only (no gate) -----

@pytest.mark.asyncio
async def test_publish_participation_only_skips_gate(
    async_client: AsyncClient, db_session: AsyncSession,
    logged_in_user: User, owned_course: Course,
):
    # score_bearing=False, no score fields at all — must publish freely.
    act = await _seed_activity(db_session, owned_course, score_bearing=False)
    r = await async_client.post(f"/api/activities/{act.id}/publish")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "published"

    rows = (await _work_items_for(db_session, act.id)).scalars().all()
    assert len(rows) == 1
    wi = rows[0]
    assert wi.source_kind == "activity"
    assert wi.required is False
    assert wi.score_bearing is False
    assert wi.created_by == logged_in_user.id
    assert wi.title == act.title


# ----- publish: score-bearing gate -----

@pytest.mark.asyncio
async def test_publish_score_bearing_incomplete_422(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course
):
    # score_bearing but missing category/points/grading_mode/deadline.
    act = await _seed_activity(db_session, owned_course, score_bearing=True)
    r = await async_client.post(f"/api/activities/{act.id}/publish")
    assert r.status_code == 422
    body = r.json()["detail"]
    assert body["code"] == "SCORE_POLICY_INCOMPLETE"
    assert set(body["missing"]) >= {
        "score_category_id", "points", "grading_mode", "deadline"
    }
    # Nothing published, no work_item written (atomicity).
    await db_session.refresh(act)
    assert act.status == "draft"
    rows = (await _work_items_for(db_session, act.id)).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_publish_score_bearing_complete(
    async_client: AsyncClient, db_session: AsyncSession,
    owned_course: Course, score_category: ScoreCategory,
):
    close = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=3)
    act = await _seed_activity(
        db_session, owned_course, format="vote", config={"options": ["A", "B"]},
        score_bearing=True, score_category_id=score_category.id,
        points=10, grading_mode="participation", close_at=close,
    )
    r = await async_client.post(f"/api/activities/{act.id}/publish")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "published"

    rows = (await _work_items_for(db_session, act.id)).scalars().all()
    assert len(rows) == 1
    wi = rows[0]
    assert wi.source_kind == "activity"
    assert wi.required is True
    assert wi.score_bearing is True
    assert wi.close_at == close


@pytest.mark.asyncio
async def test_republish_idempotent(
    async_client: AsyncClient, db_session: AsyncSession, owned_course: Course
):
    act = await _seed_activity(db_session, owned_course, score_bearing=False)
    r1 = await async_client.post(f"/api/activities/{act.id}/publish")
    assert r1.status_code == 200, r1.text
    r2 = await async_client.post(f"/api/activities/{act.id}/publish")
    assert r2.status_code == 200, r2.text
    rows = (await _work_items_for(db_session, act.id)).scalars().all()
    assert len(rows) == 1  # no duplicate — idempotent on (course, kind, source)


@pytest.mark.asyncio
async def test_publish_non_owner_404(
    async_client: AsyncClient, db_session: AsyncSession
):
    other = User(
        better_auth_id="actv_other_pub", email="actvotherpub@ust.hk",
        full_name="Other", role="instructor",
    )
    db_session.add(other)
    await db_session.flush()
    course = Course(
        name="ForeignPub", language="english",
        instructor_id=other.id, enroll_code="ACTVPUB1",
    )
    db_session.add(course)
    await db_session.commit()
    act = await _seed_activity(db_session, course)
    r = await async_client.post(f"/api/activities/{act.id}/publish")
    assert r.status_code == 404
