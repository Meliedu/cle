import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course, Document, SyllabusImport, User
from app.models.course import Enrollment


@pytest_asyncio.fixture
async def own_course(db_session: AsyncSession, logged_in_user: User) -> Course:
    c = Course(
        name="T",
        language="english",
        instructor_id=logged_in_user.id,
        enroll_code="SYLLABUS",
    )
    db_session.add(c)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=c.id, user_id=logged_in_user.id, role="instructor")
    )
    await db_session.commit()
    await db_session.refresh(c)
    return c


@pytest_asyncio.fixture
async def syllabus_doc(
    db_session: AsyncSession,
    own_course: Course,
    logged_in_user: User,
) -> Document:
    d = Document(
        course_id=own_course.id,
        uploaded_by=logged_in_user.id,
        filename="syllabus.pdf",
        file_type="pdf",
        file_size=1,
        r2_key="x",
        r2_url="x",
        status="completed",
        kind="syllabus",
    )
    db_session.add(d)
    await db_session.commit()
    await db_session.refresh(d)
    return d


@pytest.mark.asyncio
async def test_trigger_creates_pending_import(
    async_client: AsyncClient,
    own_course: Course,
    syllabus_doc: Document,
):
    r = await async_client.post(
        f"/api/courses/{own_course.id}/syllabus/imports",
        json={"document_id": str(syllabus_doc.id)},
    )
    assert r.status_code == 202
    assert r.json()["data"]["status"] == "pending"


@pytest.mark.asyncio
async def test_apply_only_works_on_parsed_status(
    async_client: AsyncClient,
    db_session: AsyncSession,
    own_course: Course,
    logged_in_user: User,
):
    imp = SyllabusImport(
        course_id=own_course.id,
        raw_text="x",
        parsed_payload={},
        status="pending",
        created_by=logged_in_user.id,
    )
    db_session.add(imp)
    await db_session.commit()
    await db_session.refresh(imp)
    r = await async_client.post(
        f"/api/courses/{own_course.id}/syllabus/imports/{imp.id}/apply",
        json={
            "parsed_payload": {
                "modules": [],
                "meetings": [],
                "objectives": [],
                "assignments": [],
                "schema_version": "v1",
            }
        },
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_apply_creates_entities(
    async_client: AsyncClient,
    db_session: AsyncSession,
    own_course: Course,
    logged_in_user: User,
):
    imp = SyllabusImport(
        course_id=own_course.id,
        raw_text="x",
        parsed_payload={"schema_version": "v1"},
        status="parsed",
        created_by=logged_in_user.id,
    )
    db_session.add(imp)
    await db_session.commit()
    await db_session.refresh(imp)
    payload = {
        "modules": [{"name": "W1", "order_index": 1}],
        "meetings": [
            {
                "module_index": 1,
                "meeting_index": 1,
                "scheduled_at": "2026-09-01T10:00:00Z",
                "title": "Intro",
                "objective_statements": [],
            }
        ],
        "objectives": [
            {"scope": "course", "statement": "x", "bloom_level": "apply"}
        ],
        "assignments": [],
        "schema_version": "v1",
    }
    r = await async_client.post(
        f"/api/courses/{own_course.id}/syllabus/imports/{imp.id}/apply",
        json={"parsed_payload": payload},
    )
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "applied"
