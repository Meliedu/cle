import asyncio
import os
import sys
import warnings
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Ensure an encryption key is set BEFORE settings/crypto modules are imported
# anywhere in the test session.
os.environ.setdefault("INTEGRATIONS_ENCRYPTION_KEY", Fernet.generate_key().decode())

from app.api.deps import get_current_user  # noqa: E402
from app.config import settings as app_settings  # noqa: E402
from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.models.user import User  # noqa: E402

# Override settings field too — pydantic-settings caches the value at import.
app_settings.integrations_encryption_key = os.environ["INTEGRATIONS_ENCRYPTION_KEY"]

# Overridable so two runs can be isolated from each other. The suite builds and
# drops the whole schema per test, so two concurrent runs against one database
# race `create_all` and leave a half-built schema behind -- which surfaces as
# `duplicate key ... pg_type_typname_nsp_index` followed by `relation ... does
# not exist` for every later test, and can deadlock outright.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/langassistant_test",
)

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
test_session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop_policy():
    """Event loop policy used by pytest-asyncio for the whole session.

    On Windows the default ``ProactorEventLoop`` lacks ``add_reader``/
    ``add_writer`` support that asyncpg requires, which surfaces as
    ``OSError: could not get source code`` / ``another operation is in
    progress`` errors. Force the selector-based policy there; keep the stock
    policy everywhere else so Linux/macOS behavior is unchanged.
    """
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.get_event_loop_policy()


def _installed_loop(policy) -> asyncio.AbstractEventLoop | None:
    """The thread's current event loop, observed WITHOUT installing one.

    ``policy.get_event_loop()`` is not usable here: when no loop is set it
    creates one as a side effect, which would leak an unclosed loop and flip
    the policy's ``_set_called`` flag on the first sync test of the session.
    We read the same slot that ``get_event_loop`` reads. If a future Python
    reshapes that internal, this degrades to None and the guard below becomes
    an inert no-op rather than an error.
    """
    local = getattr(policy, "_local", None)
    return getattr(local, "_loop", None) if local is not None else None


@pytest.fixture(autouse=True)
def _preserve_current_event_loop():
    """Restore the thread's current event loop if a test detaches it.

    pytest-asyncio installs its session-scoped loop exactly once, so anything
    that calls ``asyncio.run`` (or ``asyncio.set_event_loop(None)``) leaves
    ``_local._loop is None`` with ``_set_called`` already True. From that point
    ``asyncio.get_event_loop()`` raises ``RuntimeError: There is no current
    event loop``, and pytest-asyncio fails EVERY async test collected after the
    offender rather than just the offending one. Re-installing the loop we
    entered the test with keeps one bad test from cascading into the suite.

    See tests/test_event_loop_guard.py for the regression this pins.
    """
    entry_loop = _installed_loop(asyncio.get_event_loop_policy())

    yield

    # Re-read the policy: on the session's first async test the global policy
    # swaps (default to the selector policy from ``event_loop_policy``), so the
    # object captured at setup can be stale by teardown.
    policy = asyncio.get_event_loop_policy()
    if entry_loop is None or entry_loop.is_closed():
        return
    if _installed_loop(policy) is not entry_loop:
        policy.set_event_loop(entry_loop)
        # Repair AND report. Silently healing would mean the next stray
        # ``asyncio.run`` costs nothing observable and is never found; failing
        # here would resurrect the cascade this guard exists to stop. The
        # warning names the offending test, which is what triage needs.
        warnings.warn(
            "this test detached the thread's current event loop (a stray "
            "asyncio.run?); it was reinstalled so later async tests still run",
            RuntimeWarning,
            stacklevel=2,
        )


@pytest_asyncio.fixture
async def async_engine():
    from app.database import engine
    yield engine


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_session_factory() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_instructor(db_session: AsyncSession) -> User:
    user = User(
        better_auth_id="dev_instructor_001",
        email="instructor@ust.hk",
        full_name="Test Instructor",
        role="instructor",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_student(db_session: AsyncSession) -> User:
    user = User(
        better_auth_id="dev_student_001",
        email="student@connect.ust.hk",
        full_name="Test Student",
        role="student",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def logged_in_user(db_session: AsyncSession) -> User:
    """Default authenticated user (instructor) for API tests."""
    user = User(
        better_auth_id="dev_logged_in_001",
        email="logged-in@ust.hk",
        full_name="Logged In User",
        role="instructor",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def canvas_connected_instructor(db_session: AsyncSession, logged_in_user: User):
    """The default ``logged_in_user`` plus an active CanvasUserCredential row."""
    from datetime import datetime, timedelta, timezone

    from app.models import CanvasUserCredential
    from app.services.crypto import encrypt_secret

    cred = CanvasUserCredential(
        user_id=logged_in_user.id,
        canvas_base_url="https://canvas.ust.hk",
        canvas_user_id="42",
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


@pytest_asyncio.fixture
async def linked_course_fixture(
    db_session: AsyncSession,
    logged_in_user: User,
    canvas_connected_instructor,
):
    """A Meli Course + CanvasIntegration linked to canvas_course_id=222."""
    from app.models import CanvasIntegration
    from app.models.course import Course, Enrollment

    course = Course(
        name="Phonetics",
        code="LING220",
        language="english",
        instructor_id=logged_in_user.id,
        enroll_code="LINKED01",
    )
    db_session.add(course)
    await db_session.flush()
    db_session.add(
        Enrollment(course_id=course.id, user_id=logged_in_user.id, role="instructor")
    )
    integration = CanvasIntegration(
        course_id=course.id,
        connected_by_user_id=logged_in_user.id,
        canvas_course_id="222",
        canvas_base_url="https://canvas.ust.hk",
        sync_status="active",
    )
    db_session.add(integration)
    await db_session.commit()
    await db_session.refresh(course)
    await db_session.refresh(integration)
    return {"meli_course": course, "integration": integration}


@pytest_asyncio.fixture
async def async_client(
    db_session: AsyncSession, logged_in_user: User
) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient with get_db + get_current_user overridden for the logged-in user.

    Sends a dummy Bearer header to satisfy the AuthMiddleware fast-path; the real
    JWT verification dependency is replaced with a fixture that returns
    ``logged_in_user`` directly.
    """

    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return logged_in_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer test-token"},
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
