"""The Retry-parsing endpoint and the guard that protects it.

`POST /courses/{id}/documents/{doc_id}/reprocess` is the server side of the
"Retry parsing" action the approved course setup requires beside a failed
source. These tests pin the three properties that make it safe to expose:

  1. it is reachable only by an ACTIVE instructor of THAT course,
  2. it only ever re-runs a genuinely failed source, atomically, and
  3. it cannot be looped for free.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from contextlib import asynccontextmanager
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.deps import get_current_user, get_db
from app.main import app

from app.api.documents import REPROCESS_COOLDOWN
from app.models.course import Course, Enrollment
from app.models.document import Document
from app.models.task import Task
from app.models.user import User


@pytest.fixture
def client_for(db_session):
    """Build an authenticated client for an arbitrary user.

    Mirrors the suite's `authed_client` fixture but lets one test act as
    several different users, which is what an authorization test needs. It is a
    SYNC fixture returning an async context manager: an async fixture returning
    a factory confuses pytest-asyncio's session-scoped loop handling and the
    request never completes.
    """

    @asynccontextmanager
    async def _for(user: User):
        async def override_get_db():
            yield db_session

        async def override_get_current_user():
            return user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer test-token"},
            ) as ac:
                yield ac
        finally:
            app.dependency_overrides.clear()

    return _for


async def _mk_user(session, email: str, role: str) -> User:
    user = User(
        better_auth_id=f"ba-{uuid.uuid4()}",
        email=email,
        full_name=email.split("@")[0],
        role=role,
    )
    session.add(user)
    await session.flush()
    return user


async def _mk_course(session, owner: User) -> Course:
    course = Course(
        name="LANG1512",
        code="LANG1512",
        language="english",
        instructor_id=owner.id,
        enroll_code=uuid.uuid4().hex[:8].upper(),
    )
    session.add(course)
    await session.flush()
    return course


async def _enroll(session, course: Course, user: User, role: str, status: str):
    enrollment = Enrollment(
        course_id=course.id, user_id=user.id, role=role, status=status
    )
    session.add(enrollment)
    await session.flush()
    return enrollment


async def _mk_document(session, course: Course, uploader: User, status: str):
    document = Document(
        course_id=course.id,
        uploaded_by=uploader.id,
        filename="Week 1 reading.pdf",
        file_type="pdf",
        r2_key=f"courses/{course.id}/{uuid.uuid4()}.pdf",
        status=status,
        error_code="unreadable_file" if status == "failed" else None,
        kind="reading",
    )
    session.add(document)
    await session.flush()
    return document


@pytest.mark.asyncio
class TestReprocessAuthorization:
    async def test_pending_instructor_enrollment_is_rejected(
        self, db_session, client_for
    ):
        """A `code_plus_approval` course can leave an instructor-role
        enrollment in `pending`. That must NOT clear the gate: the previous
        local guard omitted the status check, so an un-admitted instructor
        reached every write route in this module.
        """
        owner = await _mk_user(db_session, "owner@ust.hk", "instructor")
        course = await _mk_course(db_session, owner)
        await _enroll(db_session, course, owner, "instructor", "active")

        intruder = await _mk_user(db_session, "intruder@ust.hk", "instructor")
        await _enroll(db_session, course, intruder, "instructor", "pending")

        document = await _mk_document(db_session, course, owner, "failed")
        await db_session.commit()

        async with client_for(intruder) as client:
            response = await client.post(
                f"/api/courses/{course.id}/documents/{document.id}/reprocess"
            )
        assert response.status_code == 403

    async def test_instructor_of_another_course_is_rejected(
        self, db_session, client_for
    ):
        owner = await _mk_user(db_session, "owner@ust.hk", "instructor")
        course = await _mk_course(db_session, owner)
        await _enroll(db_session, course, owner, "instructor", "active")

        other = await _mk_user(db_session, "other@ust.hk", "instructor")
        other_course = await _mk_course(db_session, other)
        await _enroll(db_session, other_course, other, "instructor", "active")

        document = await _mk_document(db_session, course, owner, "failed")
        await db_session.commit()

        async with client_for(other) as client:
            response = await client.post(
                f"/api/courses/{course.id}/documents/{document.id}/reprocess"
            )
        assert response.status_code == 403

    async def test_active_instructor_is_allowed(self, db_session, client_for):
        owner = await _mk_user(db_session, "owner@ust.hk", "instructor")
        course = await _mk_course(db_session, owner)
        await _enroll(db_session, course, owner, "instructor", "active")
        document = await _mk_document(db_session, course, owner, "failed")
        # Age the row past the cooldown.
        document.updated_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        await db_session.commit()

        async with client_for(owner) as client:
            response = await client.post(
                f"/api/courses/{course.id}/documents/{document.id}/reprocess"
            )
        assert response.status_code == 200


@pytest.mark.asyncio
class TestReprocessStateMachine:
    async def test_only_a_failed_source_may_be_retried(
        self, db_session, client_for
    ):
        owner = await _mk_user(db_session, "owner@ust.hk", "instructor")
        course = await _mk_course(db_session, owner)
        await _enroll(db_session, course, owner, "instructor", "active")
        document = await _mk_document(db_session, course, owner, "ready")
        await db_session.commit()

        async with client_for(owner) as client:
            response = await client.post(
                f"/api/courses/{course.id}/documents/{document.id}/reprocess"
            )
        # Re-queuing a completed document would discard good output.
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "not_retryable"

    async def test_retry_clears_the_typed_code_and_enqueues_once(
        self, db_session, client_for
    ):
        owner = await _mk_user(db_session, "owner@ust.hk", "instructor")
        course = await _mk_course(db_session, owner)
        await _enroll(db_session, course, owner, "instructor", "active")
        document = await _mk_document(db_session, course, owner, "failed")
        document.updated_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        await db_session.commit()
        document_id = document.id

        async with client_for(owner) as client:
            response = await client.post(
                f"/api/courses/{course.id}/documents/{document_id}/reprocess"
            )
        assert response.status_code == 200

        await db_session.commit()
        refreshed = (
            await db_session.execute(
                select(Document).where(Document.id == document_id)
            )
        ).scalar_one()
        # Back to pending, with stale recovery copy cleared.
        assert refreshed.status == "pending"
        assert refreshed.error_code is None

        tasks = (
            await db_session.execute(
                select(Task).where(Task.task_type == "process_document")
            )
        ).scalars().all()
        matching = [
            t for t in tasks if t.payload.get("document_id") == str(document_id)
        ]
        assert len(matching) == 1, "exactly one pipeline task per retry"

    async def test_the_stored_file_is_never_deleted_by_a_retry(
        self, db_session, client_for
    ):
        """Files are preserved: retry re-reads the SAME object."""
        owner = await _mk_user(db_session, "owner@ust.hk", "instructor")
        course = await _mk_course(db_session, owner)
        await _enroll(db_session, course, owner, "instructor", "active")
        document = await _mk_document(db_session, course, owner, "failed")
        document.updated_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        original_key = document.r2_key
        await db_session.commit()

        async with client_for(owner) as client:
            await client.post(
                f"/api/courses/{course.id}/documents/{document.id}/reprocess"
            )

        await db_session.commit()
        refreshed = (
            await db_session.execute(
                select(Document).where(Document.id == document.id)
            )
        ).scalar_one()
        assert refreshed.r2_key == original_key
        assert refreshed.deleted_at is None


@pytest.mark.asyncio
class TestReprocessCooldown:
    async def test_a_second_retry_within_the_cooldown_is_throttled(
        self, db_session, client_for
    ):
        """Each retry re-runs billed parsing/embedding work and this route sits
        outside the `/api/rag/*` rate limiter, so the floor lives on the route.
        """
        owner = await _mk_user(db_session, "owner@ust.hk", "instructor")
        course = await _mk_course(db_session, owner)
        await _enroll(db_session, course, owner, "instructor", "active")
        document = await _mk_document(db_session, course, owner, "failed")
        # Just failed, i.e. inside the cooldown window.
        document.updated_at = datetime.now(timezone.utc)
        await db_session.commit()

        async with client_for(owner) as client:
            response = await client.post(
                f"/api/courses/{course.id}/documents/{document.id}/reprocess"
            )
        assert response.status_code == 429
        assert response.json()["detail"]["code"] == "rate_limited"

    async def test_cooldown_is_a_bounded_window_not_a_permanent_block(self):
        assert timedelta(seconds=0) < REPROCESS_COOLDOWN <= timedelta(minutes=5)
