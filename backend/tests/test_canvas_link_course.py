"""Integration tests for POST /api/canvas/courses/{canvas_course_id}/link."""

import pytest
from sqlalchemy import select

from app.models import CanvasIntegration, Course, Enrollment
from app.services import canvas_client as canvas_client_svc


@pytest.mark.asyncio
async def test_link_creates_course_and_integration(
    async_client, logged_in_user, canvas_connected_instructor, db_session, monkeypatch
):
    canvas_user_id = canvas_connected_instructor.canvas_user_id

    async def fake_enrollments(self, cid):
        return [
            {"user_id": int(canvas_user_id), "type": "TeacherEnrollment"},
        ]

    async def fake_get_course(self, cid):
        return {"id": int(cid), "name": "Phonetics", "course_code": "LING220"}

    monkeypatch.setattr(
        canvas_client_svc.CanvasClient, "list_course_enrollments", fake_enrollments
    )
    monkeypatch.setattr(canvas_client_svc.CanvasClient, "get_course", fake_get_course)

    resp = await async_client.post("/api/canvas/courses/777/link")
    assert resp.status_code == 200, resp.text
    meli_course_id = resp.json()["data"]["meli_course_id"]

    integ = (
        await db_session.execute(
            select(CanvasIntegration).where(
                CanvasIntegration.canvas_course_id == "777"
            )
        )
    ).scalar_one()
    assert str(integ.course_id) == meli_course_id
    assert integ.sync_status == "active"
    assert integ.connected_by_user_id == logged_in_user.id

    course = (
        await db_session.execute(select(Course).where(Course.id == integ.course_id))
    ).scalar_one()
    assert course.name == "Phonetics"
    assert course.code == "LING220"
    assert course.instructor_id == logged_in_user.id
    assert course.language == "english"
    assert course.enroll_code  # generated

    enr = (
        await db_session.execute(
            select(Enrollment).where(
                Enrollment.course_id == integ.course_id,
                Enrollment.user_id == logged_in_user.id,
            )
        )
    ).scalar_one()
    assert enr.role == "instructor"


@pytest.mark.asyncio
async def test_link_accepts_ta_enrollment(
    async_client, logged_in_user, canvas_connected_instructor, db_session, monkeypatch
):
    canvas_user_id = canvas_connected_instructor.canvas_user_id

    async def fake_enrollments(self, cid):
        return [{"user_id": int(canvas_user_id), "type": "TaEnrollment"}]

    async def fake_get_course(self, cid):
        return {"id": int(cid), "name": "TA Course"}

    monkeypatch.setattr(
        canvas_client_svc.CanvasClient, "list_course_enrollments", fake_enrollments
    )
    monkeypatch.setattr(canvas_client_svc.CanvasClient, "get_course", fake_get_course)

    resp = await async_client.post("/api/canvas/courses/888/link")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_link_rejects_non_teacher(
    async_client, canvas_connected_instructor, monkeypatch
):
    async def fake_enrollments(self, cid):
        return [{"user_id": 99999, "type": "StudentEnrollment"}]

    monkeypatch.setattr(
        canvas_client_svc.CanvasClient, "list_course_enrollments", fake_enrollments
    )

    resp = await async_client.post("/api/canvas/courses/222/link")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_link_rejects_already_linked(
    async_client,
    logged_in_user,
    canvas_connected_instructor,
    linked_course_fixture,
    db_session,
    monkeypatch,
):
    canvas_user_id = canvas_connected_instructor.canvas_user_id

    async def fake_enrollments(self, cid):
        return [{"user_id": int(canvas_user_id), "type": "TeacherEnrollment"}]

    async def fake_get_course(self, cid):
        return {"id": int(cid), "name": "Dup"}

    monkeypatch.setattr(
        canvas_client_svc.CanvasClient, "list_course_enrollments", fake_enrollments
    )
    monkeypatch.setattr(canvas_client_svc.CanvasClient, "get_course", fake_get_course)

    # linked_course_fixture pre-links canvas_course_id=222
    resp = await async_client.post("/api/canvas/courses/222/link")
    assert resp.status_code == 409
