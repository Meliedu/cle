import uuid
import pytest
from httpx import AsyncClient

from app.models import Course, InstructorAlert, User


@pytest.mark.asyncio
async def test_list_alerts_default_open_only(
    db_session, async_client: AsyncClient, logged_in_user: User
):
    course = Course(
        name="Alert list",
        language="en",
        instructor_id=logged_in_user.id,
        enroll_code="ALI-1",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add_all([
        InstructorAlert(
            course_id=course.id, instructor_id=logged_in_user.id,
            alert_type="content_gap", severity="info",
            title="open one", reason={}, status="open",
        ),
        InstructorAlert(
            course_id=course.id, instructor_id=logged_in_user.id,
            alert_type="missed_deadline", severity="critical",
            title="resolved one", reason={}, status="resolved",
        ),
    ])
    await db_session.commit()

    res = await async_client.get(f"/api/courses/{course.id}/alerts")
    assert res.status_code == 200
    titles = [a["title"] for a in res.json()["data"]]
    assert "open one" in titles and "resolved one" not in titles


@pytest.mark.asyncio
async def test_patch_alert_resolves(
    db_session, async_client: AsyncClient, logged_in_user: User
):
    course = Course(
        name="Patch alert",
        language="en",
        instructor_id=logged_in_user.id,
        enroll_code="ALI-2",
    )
    db_session.add(course)
    await db_session.flush()
    a = InstructorAlert(
        course_id=course.id, instructor_id=logged_in_user.id,
        alert_type="content_gap", severity="info",
        title="x", reason={}, status="open",
    )
    db_session.add(a)
    await db_session.commit()

    res = await async_client.patch(
        f"/api/courses/{course.id}/alerts/{a.id}",
        json={"status": "resolved"},
    )
    assert res.status_code == 200
    await db_session.refresh(a)
    assert a.status == "resolved"
    assert a.resolved_at is not None and a.resolved_by == logged_in_user.id
