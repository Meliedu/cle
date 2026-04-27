"""Integration tests for /api/canvas/courses listing endpoint."""

from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import AsyncMock

from app.models import (
    CanvasIntegration,
    CanvasUserCredential,
    Course,
    User,
)
from app.services import canvas_client as canvas_client_svc
from app.services.crypto import encrypt_secret


async def _seed_credential(db_session, user: User, canvas_user_id: str = "1") -> CanvasUserCredential:
    cred = CanvasUserCredential(
        user_id=user.id,
        canvas_base_url="https://canvas.ust.hk",
        canvas_user_id=canvas_user_id,
        access_token_encrypted=encrypt_secret("at"),
        refresh_token_encrypted=encrypt_secret("rt"),
        access_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scopes="x",
        status="active",
    )
    db_session.add(cred)
    await db_session.commit()
    await db_session.refresh(cred)
    return cred


@pytest.mark.asyncio
async def test_list_taught_courses(async_client, logged_in_user, db_session, monkeypatch):
    await _seed_credential(db_session, logged_in_user)

    monkeypatch.setattr(
        canvas_client_svc.CanvasClient,
        "list_my_courses",
        AsyncMock(side_effect=lambda enrollment_type: {
            "teacher": [
                {"id": 111, "name": "Linguistics 101", "course_code": "LING101"},
                {"id": 222, "name": "Phonetics", "course_code": "LING220"},
            ],
            "ta": [],
        }[enrollment_type]),
    )

    resp = await async_client.get("/api/canvas/courses?role=teacher")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data) == 2
    by_id = {c["canvas_course_id"]: c for c in data}
    assert by_id["111"]["name"] == "Linguistics 101"
    assert by_id["111"]["already_linked_meli_course_id"] is None
    assert by_id["222"]["course_code"] == "LING220"


@pytest.mark.asyncio
async def test_list_taught_courses_marks_already_linked(
    async_client, logged_in_user, db_session, monkeypatch
):
    await _seed_credential(db_session, logged_in_user)

    # Pre-create a Meli course + integration that links Canvas course 111
    course = Course(
        name="Existing Meli",
        language="english",
        instructor_id=logged_in_user.id,
        enroll_code="ABCDEFGH",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        CanvasIntegration(
            course_id=course.id,
            connected_by_user_id=logged_in_user.id,
            canvas_course_id="111",
            canvas_base_url="https://canvas.ust.hk",
            sync_status="active",
        )
    )
    await db_session.commit()

    async def fake_list(self, enrollment_type):
        if enrollment_type == "teacher":
            return [{"id": 111, "name": "Already linked", "course_code": "X"}]
        return []

    monkeypatch.setattr(canvas_client_svc.CanvasClient, "list_my_courses", fake_list)

    resp = await async_client.get("/api/canvas/courses?role=teacher")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data[0]["already_linked_meli_course_id"] == str(course.id)


@pytest.mark.asyncio
async def test_list_taught_merges_ta_enrollments(
    async_client, logged_in_user, db_session, monkeypatch
):
    await _seed_credential(db_session, logged_in_user)

    async def fake_list(self, enrollment_type):
        if enrollment_type == "teacher":
            return [{"id": 111, "name": "T", "course_code": None}]
        if enrollment_type == "ta":
            return [
                {"id": 111, "name": "T-dup", "course_code": None},  # dedup
                {"id": 333, "name": "TA-only", "course_code": None},
            ]
        return []

    monkeypatch.setattr(canvas_client_svc.CanvasClient, "list_my_courses", fake_list)

    resp = await async_client.get("/api/canvas/courses?role=teacher")
    assert resp.status_code == 200
    ids = sorted(c["canvas_course_id"] for c in resp.json()["data"])
    assert ids == ["111", "333"]


@pytest.mark.asyncio
async def test_list_courses_student_role(async_client, db_session, monkeypatch):
    # Replace logged_in_user with a student-role user
    student = User(
        better_auth_id="dev_stu_courses",
        email="stu-courses@connect.ust.hk",
        full_name="Stu",
        role="student",
    )
    db_session.add(student)
    await db_session.commit()
    await db_session.refresh(student)
    await _seed_credential(db_session, student)

    from app.api.deps import get_current_user
    from app.main import app as fastapi_app

    async def override_user():
        return student

    fastapi_app.dependency_overrides[get_current_user] = override_user
    try:
        async def fake_list(self, enrollment_type):
            assert enrollment_type == "student"
            return [{"id": 555, "name": "Student-side", "course_code": "S1"}]

        monkeypatch.setattr(canvas_client_svc.CanvasClient, "list_my_courses", fake_list)

        resp = await async_client.get("/api/canvas/courses?role=student")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data[0]["canvas_course_id"] == "555"
    finally:
        # Let async_client teardown clean overrides; restore for safety
        pass


@pytest.mark.asyncio
async def test_list_courses_student_role_marks_already_linked(
    async_client, db_session, monkeypatch
):
    """Student listing must surface ``already_linked_meli_course_id`` for
    courses an instructor has already linked, and leave it null otherwise."""
    student = User(
        better_auth_id="dev_stu_linked",
        email="stu-linked@connect.ust.hk",
        full_name="Stu Linked",
        role="student",
    )
    db_session.add(student)
    await db_session.commit()
    await db_session.refresh(student)
    await _seed_credential(db_session, student)

    # An instructor user already linked Canvas course 777 to a Meli course.
    instructor = User(
        better_auth_id="dev_inst_linked",
        email="inst-linked@ust.hk",
        full_name="Inst",
        role="instructor",
    )
    db_session.add(instructor)
    await db_session.flush()
    linked_course = Course(
        name="Linked Meli",
        language="english",
        instructor_id=instructor.id,
        enroll_code="STULINK1",
    )
    db_session.add(linked_course)
    await db_session.flush()
    db_session.add(
        CanvasIntegration(
            course_id=linked_course.id,
            connected_by_user_id=instructor.id,
            canvas_course_id="777",
            canvas_base_url="https://canvas.ust.hk",
            sync_status="active",
        )
    )
    await db_session.commit()

    from app.api.deps import get_current_user
    from app.main import app as fastapi_app

    async def override_user():
        return student

    fastapi_app.dependency_overrides[get_current_user] = override_user

    async def fake_list(self, enrollment_type):
        assert enrollment_type == "student"
        return [
            {"id": 777, "name": "Already-linked", "course_code": "L1"},
            {"id": 888, "name": "Not-yet-linked", "course_code": "N1"},
        ]

    monkeypatch.setattr(canvas_client_svc.CanvasClient, "list_my_courses", fake_list)

    resp = await async_client.get("/api/canvas/courses?role=student")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    by_id = {c["canvas_course_id"]: c for c in data}
    assert by_id["777"]["already_linked_meli_course_id"] == str(linked_course.id)
    assert by_id["888"]["already_linked_meli_course_id"] is None


@pytest.mark.asyncio
async def test_student_requesting_teacher_role_forbidden(
    async_client, db_session, monkeypatch
):
    student = User(
        better_auth_id="dev_stu_403",
        email="stu403@connect.ust.hk",
        full_name="Stu",
        role="student",
    )
    db_session.add(student)
    await db_session.commit()
    await db_session.refresh(student)
    await _seed_credential(db_session, student)

    from app.api.deps import get_current_user
    from app.main import app as fastapi_app

    async def override_user():
        return student

    fastapi_app.dependency_overrides[get_current_user] = override_user

    resp = await async_client.get("/api/canvas/courses?role=teacher")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_courses_not_connected(async_client, logged_in_user):
    resp = await async_client.get("/api/canvas/courses?role=teacher")
    assert resp.status_code == 409
