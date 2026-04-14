"""Tests for auto-claim of PendingEnrollment rows on every authenticated call."""

import pytest
from sqlalchemy import select

from app.models import Enrollment, PendingEnrollment, User
from app.models.course import Course


@pytest.mark.asyncio
async def test_login_claims_pending_enrollment(client, db_session, monkeypatch):
    instructor = User(
        clerk_id="clerk_owner",
        email="owner@ust.hk",
        role="instructor",
        full_name="Owner",
    )
    db_session.add(instructor)
    await db_session.flush()

    course = Course(
        name="Pending Course",
        language="english",
        instructor_id=instructor.id,
        enroll_code="PENDING1",
    )
    db_session.add(course)
    await db_session.flush()

    db_session.add(
        PendingEnrollment(
            course_id=course.id,
            email="newbie@connect.ust.hk",
            canvas_user_id="77",
            role="student",
        )
    )
    await db_session.commit()

    def fake_verify(token):
        return {
            "sub": "clerk_newbie",
            "email": "newbie@connect.ust.hk",
            "name": "Newbie",
        }

    monkeypatch.setattr("app.api.deps.verify_clerk_token", fake_verify)

    resp = await client.get(
        "/api/courses", headers={"Authorization": "Bearer fake"}
    )
    assert resp.status_code == 200, resp.text

    new_user = (
        await db_session.execute(
            select(User).where(User.clerk_id == "clerk_newbie")
        )
    ).scalar_one()

    enrs = (
        await db_session.execute(
            select(Enrollment).where(Enrollment.user_id == new_user.id)
        )
    ).scalars().all()
    assert len(enrs) == 1
    assert enrs[0].course_id == course.id
    assert enrs[0].role == "student"

    remaining = (
        await db_session.execute(
            select(PendingEnrollment).where(
                PendingEnrollment.email == "newbie@connect.ust.hk"
            )
        )
    ).scalars().all()
    assert remaining == []


@pytest.mark.asyncio
async def test_existing_user_also_claims_on_subsequent_call(
    client, db_session, monkeypatch
):
    """Pending claim must run on every auth, not just first login."""
    instructor = User(
        clerk_id="clerk_owner2",
        email="owner2@ust.hk",
        role="instructor",
        full_name="Owner",
    )
    db_session.add(instructor)
    await db_session.flush()

    course = Course(
        name="Later Course",
        language="english",
        instructor_id=instructor.id,
        enroll_code="LATER001",
    )
    db_session.add(course)
    await db_session.flush()

    # Existing student user — already provisioned previously
    student = User(
        clerk_id="clerk_existing",
        email="existing@connect.ust.hk",
        role="student",
        full_name="Existing",
    )
    db_session.add(student)
    await db_session.flush()

    # Pending row added AFTER the user already exists (e.g. instructor imported
    # roster after the student first logged in).
    db_session.add(
        PendingEnrollment(
            course_id=course.id,
            email="existing@connect.ust.hk",
            canvas_user_id="42",
            role="student",
        )
    )
    await db_session.commit()

    def fake_verify(token):
        return {
            "sub": "clerk_existing",
            "email": "existing@connect.ust.hk",
            "name": "Existing",
        }

    monkeypatch.setattr("app.api.deps.verify_clerk_token", fake_verify)

    resp = await client.get(
        "/api/courses", headers={"Authorization": "Bearer fake"}
    )
    assert resp.status_code == 200, resp.text

    enr = (
        await db_session.execute(
            select(Enrollment).where(
                Enrollment.user_id == student.id,
                Enrollment.course_id == course.id,
            )
        )
    ).scalar_one()
    assert enr.role == "student"

    remaining = (
        await db_session.execute(
            select(PendingEnrollment).where(
                PendingEnrollment.email == "existing@connect.ust.hk"
            )
        )
    ).scalars().all()
    assert remaining == []
