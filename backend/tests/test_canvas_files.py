"""Integration tests for Canvas file listing + import endpoints."""

import pytest
from sqlalchemy import select

from app.models import Document
from app.services import canvas_client as canvas_client_svc


@pytest.mark.asyncio
async def test_list_files_splits_available_and_imported(
    async_client, logged_in_user, linked_course_fixture, db_session, monkeypatch
):
    course = linked_course_fixture["meli_course"]

    db_session.add(
        Document(
            course_id=course.id,
            uploaded_by=logged_in_user.id,
            filename="existing.pdf",
            file_type="pdf",
            file_size=1000,
            r2_key=f"courses/{course.id}/documents/existing/existing.pdf",
            status="completed",
            canvas_file_id="999",
            canvas_file_etag="etag999",
        )
    )
    await db_session.commit()

    async def fake_files(self, cid):
        return [
            {
                "id": 999,
                "display_name": "existing.pdf",
                "size": 1000,
                "content-type": "application/pdf",
                "url": "https://canvas/files/999/download",
                "updated_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": 1000,
                "display_name": "new.pdf",
                "size": 2000,
                "content-type": "application/pdf",
                "url": "https://canvas/files/1000/download",
                "updated_at": "2026-01-02T00:00:00Z",
            },
        ]

    monkeypatch.setattr(
        canvas_client_svc.CanvasClient, "list_course_files", fake_files
    )

    resp = await async_client.get(f"/api/courses/{course.id}/canvas/files")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert {f["canvas_file_id"] for f in data["already_imported"]} == {"999"}
    assert {f["canvas_file_id"] for f in data["available"]} == {"1000"}
    avail = data["available"][0]
    assert avail["display_name"] == "new.pdf"
    assert avail["content_type"] == "application/pdf"
    assert avail["download_url"] == "https://canvas/files/1000/download"


@pytest.mark.asyncio
async def test_list_files_404_when_not_connected(
    async_client, logged_in_user, db_session
):
    from app.models.course import Course, Enrollment

    course = Course(
        name="No Canvas",
        language="english",
        instructor_id=logged_in_user.id,
        enroll_code="NOCANVAS",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor")
    )
    await db_session.commit()

    resp = await async_client.get(f"/api/courses/{course.id}/canvas/files")
    assert resp.status_code == 404
