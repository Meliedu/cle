"""Integration tests for POST /api/canvas/courses/{canvas_course_id}/join."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import (
    CanvasIntegration,
    CanvasUserCredential,
    Course,
    Enrollment,
    PendingEnrollment,
    User,
)
from app.services import canvas_client as canvas_client_svc
from app.services.crypto import encrypt_secret


async def _seed_student(db_session) -> User:
    """Replace the default logged-in instructor with a student user."""
    student = User(
        clerk_id="clerk_join_student",
        email="join-student@connect.ust.hk",
        full_name="Joiner",
        role="student",
    )
    db_session.add(student)
    await db_session.commit()
    await db_session.refresh(student)

    cred = CanvasUserCredential(
        user_id=student.id,
        canvas_base_url="https://canvas.ust.hk",
        canvas_user_id="9001",
        access_token_encrypted=encrypt_secret("at"),
        refresh_token_encrypted=encrypt_secret("rt"),
        access_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scopes="x",
        status="active",
    )
    db_session.add(cred)
    await db_session.commit()
    return student


def _override_user(student: User) -> None:
    from app.api.deps import get_current_user
    from app.main import app as fastapi_app

    async def override():
        return student

    fastapi_app.dependency_overrides[get_current_user] = override


@pytest.mark.asyncio
async def test_join_creates_enrollment_and_clears_pending(
    async_client, db_session, monkeypatch
):
    student = await _seed_student(db_session)
    _override_user(student)

    # Instructor pre-linked Canvas course 555 to a Meli course.
    instructor = User(
        clerk_id="clerk_join_inst",
        email="join-inst@ust.hk",
        full_name="Inst",
        role="instructor",
    )
    db_session.add(instructor)
    await db_session.flush()
    course = Course(
        name="Joinable",
        language="english",
        instructor_id=instructor.id,
        enroll_code="JOINABLE",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        CanvasIntegration(
            course_id=course.id,
            connected_by_user_id=instructor.id,
            canvas_course_id="555",
            canvas_base_url="https://canvas.ust.hk",
            sync_status="active",
        )
    )
    db_session.add(
        PendingEnrollment(
            course_id=course.id,
            email=student.email.lower(),
            canvas_user_id="9001",
            role="student",
        )
    )
    await db_session.commit()

    async def fake_enrollments(self, cid):
        return [{"user_id": 9001, "type": "StudentEnrollment"}]

    monkeypatch.setattr(
        canvas_client_svc.CanvasClient,
        "list_course_enrollments",
        fake_enrollments,
    )

    resp = await async_client.post("/api/canvas/courses/555/join")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["meli_course_id"] == str(course.id)

    enr = (
        await db_session.execute(
            select(Enrollment).where(
                Enrollment.course_id == course.id,
                Enrollment.user_id == student.id,
            )
        )
    ).scalar_one()
    assert enr.role == "student"

    pending = (
        await db_session.execute(
            select(PendingEnrollment).where(
                PendingEnrollment.course_id == course.id,
                PendingEnrollment.email == student.email.lower(),
            )
        )
    ).scalar_one_or_none()
    assert pending is None


@pytest.mark.asyncio
async def test_join_404_when_no_integration(async_client, db_session, monkeypatch):
    student = await _seed_student(db_session)
    _override_user(student)

    async def fake_enrollments(self, cid):
        return [{"user_id": 9001, "type": "StudentEnrollment"}]

    monkeypatch.setattr(
        canvas_client_svc.CanvasClient,
        "list_course_enrollments",
        fake_enrollments,
    )

    resp = await async_client.post("/api/canvas/courses/9999/join")
    assert resp.status_code == 404
    assert "Meli" in resp.json()["detail"]
