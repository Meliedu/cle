"""Integration tests for POST /api/courses/{id}/canvas/roster/import."""

import pytest
from sqlalchemy import select

from app.models import Enrollment, PendingEnrollment, User
from app.services import canvas_client as canvas_client_svc


@pytest.mark.asyncio
async def test_roster_import_matches_and_pre_provisions(
    async_client, logged_in_user, linked_course_fixture, db_session, monkeypatch
):
    course = linked_course_fixture["meli_course"]

    async def fake_enrollments(self, cid):
        return [
            {
                "user_id": 10,
                "type": "StudentEnrollment",
                "user": {"email": "alice@connect.ust.hk", "name": "Alice"},
            },
            {
                "user_id": 11,
                "type": "StudentEnrollment",
                "user": {"email": "bob@connect.ust.hk", "name": "Bob"},
            },
            {
                "user_id": 12,
                "type": "TaEnrollment",
                "user": {"email": "ta@ust.hk", "name": "TA"},
            },
            {
                "user_id": 13,
                "type": "ObserverEnrollment",
                "user": {"email": "parent@example.com", "name": "Parent"},
            },
            {
                "user_id": 14,
                "type": "DesignerEnrollment",
                "user": {"email": "designer@ust.hk", "name": "Designer"},
            },
        ]

    monkeypatch.setattr(
        canvas_client_svc.CanvasClient, "list_course_enrollments", fake_enrollments
    )

    alice = User(
        clerk_id="clerk_alice",
        email="alice@connect.ust.hk",
        role="student",
        full_name="Alice",
    )
    ta_user = User(
        clerk_id="clerk_ta",
        email="ta@ust.hk",
        role="instructor",
        full_name="TA",
    )
    db_session.add_all([alice, ta_user])
    await db_session.commit()

    resp = await async_client.post(
        f"/api/courses/{course.id}/canvas/roster/import",
        json={"send_invite_emails": False},
    )
    assert resp.status_code == 200, resp.text
    d = resp.json()["data"]
    assert d["added"] == 2  # alice + ta
    assert d["pending"] == 1  # bob
    assert d["skipped_off_domain"] == 1  # observer's parent email (designer is on-domain but skipped role)
    # logged_in_user is the connected instructor — preserve_user_ids keeps
    # their enrollment even though Canvas omits them from the roster.
    assert d["dropped"] == 0

    alice_enr = (
        await db_session.execute(
            select(Enrollment).where(
                Enrollment.user_id == alice.id, Enrollment.course_id == course.id
            )
        )
    ).scalar_one()
    assert alice_enr.role == "student"

    ta_enr = (
        await db_session.execute(
            select(Enrollment).where(
                Enrollment.user_id == ta_user.id, Enrollment.course_id == course.id
            )
        )
    ).scalar_one()
    assert ta_enr.role == "instructor"

    bob_pending = (
        await db_session.execute(
            select(PendingEnrollment).where(
                PendingEnrollment.email == "bob@connect.ust.hk"
            )
        )
    ).scalar_one()
    assert bob_pending.role == "student"
    assert bob_pending.invited_at is None
    assert bob_pending.canvas_user_id == "11"


@pytest.mark.asyncio
async def test_roster_import_hard_deletes_drops(
    async_client, logged_in_user, linked_course_fixture, db_session, monkeypatch
):
    course = linked_course_fixture["meli_course"]

    carol = User(
        clerk_id="c",
        email="carol@connect.ust.hk",
        role="student",
        full_name="Carol",
    )
    db_session.add(carol)
    await db_session.flush()
    carol_enr = Enrollment(
        course_id=course.id, user_id=carol.id, role="student"
    )
    db_session.add(carol_enr)
    await db_session.commit()
    carol_id = carol.id

    async def fake_enrollments(self, cid):
        return []

    monkeypatch.setattr(
        canvas_client_svc.CanvasClient, "list_course_enrollments", fake_enrollments
    )

    resp = await async_client.post(
        f"/api/courses/{course.id}/canvas/roster/import",
        json={"send_invite_emails": False},
    )
    assert resp.status_code == 200, resp.text
    # logged_in_user is the connected instructor — preserved. Only carol is
    # dropped (Canvas roster is empty).
    assert resp.json()["data"]["dropped"] == 1

    # Instructor enrollment must still exist.
    inst_enr = (
        await db_session.execute(
            select(Enrollment).where(
                Enrollment.user_id == logged_in_user.id,
                Enrollment.course_id == course.id,
            )
        )
    ).scalar_one_or_none()
    assert inst_enr is not None

    # Carol's enrollment should be hard-deleted
    carol_enr_after = (
        await db_session.execute(
            select(Enrollment).where(
                Enrollment.user_id == carol_id, Enrollment.course_id == course.id
            )
        )
    ).scalar_one_or_none()
    assert carol_enr_after is None


@pytest.mark.asyncio
async def test_roster_import_idempotent_on_existing(
    async_client, logged_in_user, linked_course_fixture, db_session, monkeypatch
):
    course = linked_course_fixture["meli_course"]

    alice = User(
        clerk_id="clerk_alice2",
        email="alice2@connect.ust.hk",
        role="student",
        full_name="Alice",
    )
    db_session.add(alice)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=alice.id, role="student")
    )
    await db_session.commit()

    async def fake_enrollments(self, cid):
        return [
            {
                "user_id": 10,
                "type": "StudentEnrollment",
                "user": {"email": "alice2@connect.ust.hk", "name": "Alice"},
            },
            # Include the instructor so they aren't dropped
            {
                "user_id": 99,
                "type": "TeacherEnrollment",
                "user": {"email": logged_in_user.email, "name": "Instructor"},
            },
        ]

    monkeypatch.setattr(
        canvas_client_svc.CanvasClient, "list_course_enrollments", fake_enrollments
    )

    resp = await async_client.post(
        f"/api/courses/{course.id}/canvas/roster/import",
        json={"send_invite_emails": False},
    )
    assert resp.status_code == 200
    d = resp.json()["data"]
    assert d["added"] == 0
    assert d["unchanged"] == 2
    assert d["dropped"] == 0
