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
async def test_import_creates_documents_and_tasks(
    async_client, logged_in_user, linked_course_fixture, db_session, monkeypatch
):
    from app.models import Task

    course = linked_course_fixture["meli_course"]

    async def fake_get_file(self, file_id):
        return {
            "id": int(file_id),
            "display_name": "lecture1.pdf",
            "size": 5000,
            "content-type": "application/pdf",
            "url": "https://canvas/files/1001/download?signed=yes",
            "updated_at": "2026-02-01T00:00:00Z",
        }

    async def fake_download(self, url):
        return b"%PDF-fakepdfbytes"

    upload_calls: list[tuple] = []

    def fake_upload(r2_key, data, content_type):
        upload_calls.append((r2_key, data, content_type))

    monkeypatch.setattr(canvas_client_svc.CanvasClient, "get_file", fake_get_file)
    monkeypatch.setattr(canvas_client_svc.CanvasClient, "download_file", fake_download)
    monkeypatch.setattr("app.services.storage.upload_file", fake_upload)

    resp = await async_client.post(
        f"/api/courses/{course.id}/canvas/files/import",
        json={"file_ids": ["1001"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["imported"] == ["1001"]
    assert body["skipped"] == []
    assert body["errors"] == []

    doc = (
        await db_session.execute(
            select(Document).where(Document.canvas_file_id == "1001")
        )
    ).scalar_one()
    assert doc.status == "pending"
    assert doc.filename == "lecture1.pdf"
    assert doc.file_type == "pdf"
    assert doc.file_size == 5000
    assert doc.uploaded_by == logged_in_user.id
    assert doc.r2_key.startswith(f"courses/{course.id}/documents/")
    assert doc.canvas_file_etag == "2026-02-01T00:00:00Z"

    assert upload_calls and upload_calls[0][2] == "application/pdf"

    task = (
        await db_session.execute(
            select(Task).where(Task.task_type == "process_document")
        )
    ).scalars().first()
    assert task is not None
    assert task.payload.get("document_id") == str(doc.id)


@pytest.mark.asyncio
async def test_import_skips_already_imported(
    async_client, logged_in_user, linked_course_fixture, db_session, monkeypatch
):
    course = linked_course_fixture["meli_course"]
    db_session.add(
        Document(
            course_id=course.id,
            uploaded_by=logged_in_user.id,
            filename="old.pdf",
            file_type="pdf",
            file_size=1,
            r2_key=f"courses/{course.id}/documents/old/old.pdf",
            status="completed",
            canvas_file_id="999",
        )
    )
    await db_session.commit()

    async def explode(self, file_id):
        raise AssertionError("should not fetch already-imported file")

    monkeypatch.setattr(canvas_client_svc.CanvasClient, "get_file", explode)

    resp = await async_client.post(
        f"/api/courses/{course.id}/canvas/files/import",
        json={"file_ids": ["999"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["skipped"] == ["999"]
    assert resp.json()["data"]["imported"] == []


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
