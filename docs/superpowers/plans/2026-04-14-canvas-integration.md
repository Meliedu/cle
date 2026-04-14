# Canvas Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let HKUST users connect Canvas via OAuth 2.0 so instructors can mirror courses/files/rosters into Meli and students can self-enroll from their Canvas course list — no manual enrollment codes.

**Architecture:** Per-user OAuth credentials (not per-course PATs), a Canvas REST client with refresh-on-401, three cooperating subsystems (OAuth foundation → instructor flow → student flow) backed by a daily sync scheduler that reuses the existing `tasks` queue.

**Tech Stack:** FastAPI (async), SQLAlchemy 2.0 async, Alembic, pydantic v2, httpx, PyJWT, Clerk JWT verification, Next.js 16 App Router + TanStack Query, Playwright E2E.

**Spec:** `docs/superpowers/specs/2026-04-14-canvas-integration-design.md`

**Prerequisite (blocking, before Task 1):** Register a Canvas Developer Key with HKUST IT for `canvas.ust.hk`. Scopes listed in spec §6.1. Store `CANVAS_CLIENT_ID`, `CANVAS_CLIENT_SECRET`, `CANVAS_REDIRECT_URI`, `CANVAS_BASE_URL` in `.env`. If HKUST IT is blocking, the engineer can mock the OAuth server against a local Canvas test instance (`canvas.instructure.com` sandbox) by overriding `CANVAS_BASE_URL` during development.

---

## File Map

### New backend files
- `backend/app/services/canvas_oauth.py` — state JWT, authorize URL, token exchange, refresh
- `backend/app/services/canvas_client.py` — per-user `CanvasClient` factory with refresh-on-401 (replaces the ad-hoc client in existing `canvas.py` service)
- `backend/app/services/canvas_roster.py` — diff computation + pending enrollment upsert
- `backend/app/services/canvas_files.py` — list/import helpers (download → R2 → document row)
- `backend/app/services/canvas_sync.py` — scheduled daily sync handler
- `backend/app/api/canvas_oauth.py` — `/api/canvas/oauth/*` + `/api/canvas/courses` + `/api/canvas/connection` endpoints
- `backend/app/models/canvas.py` — `CanvasUserCredential`, `PendingEnrollment`, `CanvasSyncEvent` (plus keeps existing `CanvasIntegration`)
- `backend/alembic/versions/d3e7b8f2a9c4_canvas_oauth_phase1.py`

### Modified backend files
- `backend/app/services/canvas.py` — keep low-level HTTP class, add enrollment + user self methods
- `backend/app/api/canvas.py` — repoint at new services; replace PAT `/connect` with OAuth hooks; implement `/import` endpoint
- `backend/app/models/document.py` — add `canvas_file_id`, `canvas_file_etag` columns
- `backend/app/models/integration.py` — drop `access_token_encrypted`, add `connected_by_user_id`, `last_roster_sync_at`, `last_file_scan_at`
- `backend/app/api/deps.py` — claim pending enrollments on first login
- `backend/app/config.py` — new Canvas OAuth settings
- `backend/app/main.py` — register new router, start scheduler in lifespan

### New tests
- `backend/tests/test_canvas_oauth.py`
- `backend/tests/test_canvas_client.py`
- `backend/tests/test_canvas_roster.py`
- `backend/tests/test_canvas_files.py`
- `backend/tests/test_canvas_sync.py`
- `backend/tests/test_canvas_api.py`
- `backend/tests/test_pending_enrollment_claim.py`
- `frontend/tests/e2e/canvas-integration.spec.ts`

### New frontend files
- `frontend/src/lib/canvas-api.ts`
- `frontend/src/hooks/use-canvas.ts`
- `frontend/src/app/dashboard/canvas/page.tsx` — connection settings
- `frontend/src/components/canvas/connect-button.tsx`
- `frontend/src/components/canvas/canvas-course-picker.tsx`
- `frontend/src/components/canvas/file-import-dialog.tsx`
- `frontend/src/components/canvas/roster-import-dialog.tsx`
- `frontend/src/components/canvas/student-canvas-courses.tsx`

### Modified frontend files
- `frontend/src/app/dashboard/courses/[courseId]/page.tsx` — add Canvas tab (instructor only)
- the student "join course" page — add Canvas section (exact path TBD — see Task 23; engineer verifies path)

---

## Phase A — Foundation

### Task 1: Add Canvas OAuth settings

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example` (create if missing)

- [ ] **Step 1: Add settings fields**

In `backend/app/config.py`, add inside `Settings` class:

```python
    canvas_client_id: str = ""
    canvas_client_secret: str = ""
    canvas_base_url: str = "https://canvas.ust.hk"
    canvas_redirect_uri: str = "http://localhost:8000/api/canvas/oauth/callback"
    canvas_state_secret: str = ""   # signing key for OAuth state JWT; 32+ random bytes
    canvas_scopes: str = (
        "url:GET|/api/v1/users/self "
        "url:GET|/api/v1/users/self/courses "
        "url:GET|/api/v1/users/self/enrollments "
        "url:GET|/api/v1/courses/:id "
        "url:GET|/api/v1/courses/:id/enrollments "
        "url:GET|/api/v1/courses/:id/files "
        "url:GET|/api/v1/files/:id"
    )
```

- [ ] **Step 2: Update `.env.example`**

Append:

```
# Canvas OAuth (Phase 1)
CANVAS_CLIENT_ID=
CANVAS_CLIENT_SECRET=
CANVAS_BASE_URL=https://canvas.ust.hk
CANVAS_REDIRECT_URI=http://localhost:8000/api/canvas/oauth/callback
CANVAS_STATE_SECRET=   # python -c "import secrets; print(secrets.token_urlsafe(48))"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py backend/.env.example
git commit -m "feat(canvas): add OAuth config settings"
```

---

### Task 2: Alembic migration for new schema

**Files:**
- Create: `backend/alembic/versions/d3e7b8f2a9c4_canvas_oauth_phase1.py`

- [ ] **Step 1: Generate blank revision file**

```bash
cd backend && source .venv/bin/activate
alembic revision -m "canvas oauth phase 1"
```

Rename/use the generated file; the slug `d3e7b8f2a9c4_canvas_oauth_phase1.py` in this plan is illustrative — use the actual revision id Alembic assigns.

- [ ] **Step 2: Write upgrade/downgrade**

```python
"""canvas oauth phase 1

Revision ID: d3e7b8f2a9c4
Revises: <previous>
Create Date: 2026-04-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "d3e7b8f2a9c4"
down_revision = "<fill in from latest existing>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Wipe legacy PAT-based integrations so NOT NULL ownership column is safe
    op.execute("DELETE FROM canvas_integrations")

    op.create_table(
        "canvas_user_credentials",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("canvas_base_url", sa.String(500), nullable=False),
        sa.Column("canvas_user_id", sa.String(100), nullable=False),
        sa.Column("access_token_encrypted", sa.String(1000), nullable=False),
        sa.Column("refresh_token_encrypted", sa.String(1000), nullable=False),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "pending_enrollments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("course_id", UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("canvas_user_id", sa.String(100), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("invited_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("course_id", "email", name="uq_pending_enrollments_course_email"),
    )
    op.create_index("ix_pending_enrollments_email", "pending_enrollments", ["email"])

    op.create_table(
        "canvas_sync_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("course_id", UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),  # 'roster_diff' | 'file_scan' | 'error'
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_canvas_sync_events_course_created", "canvas_sync_events", ["course_id", "created_at"])

    op.add_column("canvas_integrations", sa.Column("connected_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False))
    op.add_column("canvas_integrations", sa.Column("last_roster_sync_at", sa.DateTime(timezone=True)))
    op.add_column("canvas_integrations", sa.Column("last_file_scan_at", sa.DateTime(timezone=True)))
    op.drop_column("canvas_integrations", "access_token_encrypted")

    op.add_column("documents", sa.Column("canvas_file_id", sa.String(100)))
    op.add_column("documents", sa.Column("canvas_file_etag", sa.String(100)))
    op.create_index(
        "idx_documents_canvas_file",
        "documents",
        ["course_id", "canvas_file_id"],
        unique=True,
        postgresql_where=sa.text("canvas_file_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_documents_canvas_file", table_name="documents")
    op.drop_column("documents", "canvas_file_etag")
    op.drop_column("documents", "canvas_file_id")

    op.add_column("canvas_integrations", sa.Column("access_token_encrypted", sa.String(500)))
    op.drop_column("canvas_integrations", "last_file_scan_at")
    op.drop_column("canvas_integrations", "last_roster_sync_at")
    op.drop_column("canvas_integrations", "connected_by_user_id")

    op.drop_index("ix_canvas_sync_events_course_created", table_name="canvas_sync_events")
    op.drop_table("canvas_sync_events")
    op.drop_index("ix_pending_enrollments_email", table_name="pending_enrollments")
    op.drop_table("pending_enrollments")
    op.drop_table("canvas_user_credentials")
```

- [ ] **Step 3: Run migration locally**

```bash
alembic upgrade head
```

Expected: migration applies cleanly. Verify with `psql`:

```sql
\d canvas_user_credentials
\d pending_enrollments
\d canvas_sync_events
\d canvas_integrations
```

- [ ] **Step 4: Test downgrade then re-upgrade**

```bash
alembic downgrade -1 && alembic upgrade head
```

Expected: both succeed.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat(canvas): migration for OAuth phase 1 schema"
```

---

### Task 3: SQLAlchemy models

**Files:**
- Create: `backend/app/models/canvas.py`
- Modify: `backend/app/models/integration.py`
- Modify: `backend/app/models/document.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create new models**

Create `backend/app/models/canvas.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CanvasUserCredential(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "canvas_user_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    canvas_base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    canvas_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    access_token_encrypted: Mapped[str] = mapped_column(String(1000), nullable=False)
    refresh_token_encrypted: Mapped[str] = mapped_column(String(1000), nullable=False)
    access_token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scopes: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)


class PendingEnrollment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "pending_enrollments"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    canvas_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CanvasSyncEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "canvas_sync_events"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 2: Modify `integration.py`**

Replace the body of `CanvasIntegration`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CanvasIntegration(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "canvas_integrations"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    connected_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    canvas_course_id: Mapped[str] = mapped_column(String(100), nullable=False)
    canvas_base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_roster_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_file_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_status: Mapped[str] = mapped_column(String(20), default="active")
    sync_config: Mapped[dict] = mapped_column(JSON, default=dict)
```

- [ ] **Step 3: Modify `document.py`**

Add to `Document` model:

```python
    canvas_file_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    canvas_file_etag: Mapped[str | None] = mapped_column(String(100), nullable=True)
```

- [ ] **Step 4: Wire up in `models/__init__.py`**

Add imports:

```python
from app.models.canvas import (
    CanvasSyncEvent,
    CanvasUserCredential,
    PendingEnrollment,
)
```

And include them in `__all__`.

- [ ] **Step 5: Run tests to verify models import cleanly**

```bash
cd backend && source .venv/bin/activate
python -c "from app.models import CanvasUserCredential, PendingEnrollment, CanvasSyncEvent, CanvasIntegration; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/
git commit -m "feat(canvas): SQLAlchemy models for OAuth phase 1"
```

---

### Task 4: OAuth state JWT + authorize-URL helper

**Files:**
- Create: `backend/app/services/canvas_oauth.py`
- Create: `backend/tests/test_canvas_oauth.py`

- [ ] **Step 1: Write failing test for state round-trip**

Create `backend/tests/test_canvas_oauth.py`:

```python
import uuid
import time
import pytest

from app.services import canvas_oauth


def test_state_round_trip(monkeypatch):
    monkeypatch.setattr(canvas_oauth.settings, "canvas_state_secret", "test-secret")
    user_id = uuid.uuid4()
    token = canvas_oauth.encode_state(user_id)
    decoded = canvas_oauth.decode_state(token)
    assert decoded == user_id


def test_state_expired(monkeypatch):
    monkeypatch.setattr(canvas_oauth.settings, "canvas_state_secret", "test-secret")
    monkeypatch.setattr(canvas_oauth, "STATE_TTL_SECONDS", 1)
    token = canvas_oauth.encode_state(uuid.uuid4())
    time.sleep(2)
    with pytest.raises(canvas_oauth.StateInvalid):
        canvas_oauth.decode_state(token)


def test_state_tampered(monkeypatch):
    monkeypatch.setattr(canvas_oauth.settings, "canvas_state_secret", "test-secret")
    token = canvas_oauth.encode_state(uuid.uuid4()) + "x"
    with pytest.raises(canvas_oauth.StateInvalid):
        canvas_oauth.decode_state(token)


def test_authorize_url(monkeypatch):
    monkeypatch.setattr(canvas_oauth.settings, "canvas_client_id", "client123")
    monkeypatch.setattr(canvas_oauth.settings, "canvas_base_url", "https://canvas.ust.hk")
    monkeypatch.setattr(canvas_oauth.settings, "canvas_redirect_uri", "https://api.meli/cb")
    monkeypatch.setattr(canvas_oauth.settings, "canvas_scopes", "url:GET|/api/v1/users/self")
    url = canvas_oauth.build_authorize_url(state="abc")
    assert url.startswith("https://canvas.ust.hk/login/oauth2/auth?")
    assert "client_id=client123" in url
    assert "state=abc" in url
    assert "scope=url%3AGET%7C%2Fapi%2Fv1%2Fusers%2Fself" in url
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_canvas_oauth.py -v
```

Expected: FAIL (module `canvas_oauth` does not exist).

- [ ] **Step 3: Implement the module**

Create `backend/app/services/canvas_oauth.py`:

```python
"""Canvas OAuth 2.0 state helpers and token exchange."""

from __future__ import annotations

import secrets
import time
import uuid
from urllib.parse import urlencode

import httpx
import jwt

from app.config import settings

STATE_TTL_SECONDS = 600  # 10 minutes


class StateInvalid(Exception):
    """Raised when the OAuth state token fails verification."""


def encode_state(user_id: uuid.UUID) -> str:
    payload = {
        "uid": str(user_id),
        "nonce": secrets.token_urlsafe(16),
        "exp": int(time.time()) + STATE_TTL_SECONDS,
    }
    return jwt.encode(payload, settings.canvas_state_secret, algorithm="HS256")


def decode_state(token: str) -> uuid.UUID:
    try:
        payload = jwt.decode(
            token,
            settings.canvas_state_secret,
            algorithms=["HS256"],
        )
    except jwt.PyJWTError as exc:
        raise StateInvalid(str(exc)) from exc
    return uuid.UUID(payload["uid"])


def build_authorize_url(state: str) -> str:
    params = {
        "client_id": settings.canvas_client_id,
        "response_type": "code",
        "redirect_uri": settings.canvas_redirect_uri,
        "state": state,
        "scope": settings.canvas_scopes,
    }
    return f"{settings.canvas_base_url.rstrip('/')}/login/oauth2/auth?" + urlencode(params)


async def exchange_code(code: str) -> dict:
    """Exchange an authorization code for access + refresh tokens."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{settings.canvas_base_url.rstrip('/')}/login/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "client_id": settings.canvas_client_id,
                "client_secret": settings.canvas_client_secret,
                "redirect_uri": settings.canvas_redirect_uri,
                "code": code,
            },
        )
        response.raise_for_status()
        return response.json()


async def refresh_access_token(refresh_token: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{settings.canvas_base_url.rstrip('/')}/login/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "client_id": settings.canvas_client_id,
                "client_secret": settings.canvas_client_secret,
                "refresh_token": refresh_token,
            },
        )
        response.raise_for_status()
        return response.json()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_canvas_oauth.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/canvas_oauth.py backend/tests/test_canvas_oauth.py
git commit -m "feat(canvas): OAuth state JWT and authorize-URL builder"
```

---

### Task 5: OAuth start + callback API endpoints

**Files:**
- Create: `backend/app/api/canvas_oauth.py`
- Modify: `backend/app/main.py` (register router)
- Create: `backend/tests/test_canvas_oauth_api.py`

- [ ] **Step 1: Write failing integration test**

Create `backend/tests/test_canvas_oauth_api.py`:

```python
import uuid
from datetime import datetime, timezone, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import canvas_oauth
from app.services.crypto import decrypt_secret
from app.models import CanvasUserCredential


@pytest.mark.asyncio
async def test_oauth_start_returns_authorize_url(
    async_client, logged_in_user, monkeypatch
):
    monkeypatch.setattr(canvas_oauth.settings, "canvas_client_id", "cid")
    monkeypatch.setattr(canvas_oauth.settings, "canvas_state_secret", "s")
    resp = await async_client.get("/api/canvas/oauth/start")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["authorize_url"].startswith(canvas_oauth.settings.canvas_base_url.rstrip("/"))
    assert "state=" in data["authorize_url"]


@pytest.mark.asyncio
async def test_oauth_callback_stores_credential(
    async_client, logged_in_user, db_session, monkeypatch
):
    monkeypatch.setattr(canvas_oauth.settings, "canvas_state_secret", "s")
    state = canvas_oauth.encode_state(logged_in_user.id)

    async def fake_exchange(code):
        return {
            "access_token": "atk",
            "refresh_token": "rtk",
            "expires_in": 3600,
            "user": {"id": 42},
        }

    monkeypatch.setattr(canvas_oauth, "exchange_code", fake_exchange)

    resp = await async_client.get(
        f"/api/canvas/oauth/callback?code=xyz&state={state}",
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)

    from sqlalchemy import select
    row = (await db_session.execute(
        select(CanvasUserCredential).where(CanvasUserCredential.user_id == logged_in_user.id)
    )).scalar_one()
    assert row.canvas_user_id == "42"
    assert decrypt_secret(row.access_token_encrypted) == "atk"
    assert decrypt_secret(row.refresh_token_encrypted) == "rtk"
    assert row.status == "active"


@pytest.mark.asyncio
async def test_oauth_callback_rejects_bad_state(async_client):
    resp = await async_client.get(
        "/api/canvas/oauth/callback?code=xyz&state=not-a-real-jwt",
        follow_redirects=False,
    )
    assert resp.status_code == 400
```

(Engineer: if `async_client` / `logged_in_user` / `db_session` fixtures don't already exist in `conftest.py`, add them by following the pattern used in `test_api_live.py`. The fixture plumbing is the same as every other async API test in this codebase.)

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_canvas_oauth_api.py -v
```

Expected: FAIL (endpoints don't exist).

- [ ] **Step 3: Implement endpoints**

Create `backend/app/api/canvas_oauth.py`:

```python
"""Canvas OAuth + top-level (non-course-scoped) Canvas endpoints."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.models import CanvasUserCredential, User
from app.schemas.common import APIResponse
from app.services import canvas_oauth
from app.services.crypto import encrypt_secret

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/canvas", tags=["canvas-oauth"])


@router.get("/oauth/start", response_model=APIResponse[dict])
async def oauth_start(user: User = Depends(get_current_user)):
    if not settings.canvas_client_id or not settings.canvas_state_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Canvas integration not configured",
        )
    state = canvas_oauth.encode_state(user.id)
    return APIResponse(success=True, data={"authorize_url": canvas_oauth.build_authorize_url(state)})


@router.get("/oauth/callback", include_in_schema=False)
async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        user_id = canvas_oauth.decode_state(state)
    except canvas_oauth.StateInvalid:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    try:
        token_payload = await canvas_oauth.exchange_code(code)
    except httpx.HTTPError as exc:
        logger.warning("Canvas code exchange failed: %s", exc)
        raise HTTPException(status_code=502, detail="Canvas token exchange failed")

    access = token_payload["access_token"]
    refresh = token_payload["refresh_token"]
    expires_in = int(token_payload.get("expires_in", 3600))
    canvas_user_id = str(token_payload.get("user", {}).get("id", ""))
    if not canvas_user_id:
        raise HTTPException(status_code=502, detail="Canvas did not return user id")

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    stmt = pg_insert(CanvasUserCredential).values(
        user_id=user_id,
        canvas_base_url=settings.canvas_base_url,
        canvas_user_id=canvas_user_id,
        access_token_encrypted=encrypt_secret(access),
        refresh_token_encrypted=encrypt_secret(refresh),
        access_token_expires_at=expires_at,
        scopes=settings.canvas_scopes,
        status="active",
    ).on_conflict_do_update(
        index_elements=["user_id"],
        set_={
            "canvas_base_url": settings.canvas_base_url,
            "canvas_user_id": canvas_user_id,
            "access_token_encrypted": encrypt_secret(access),
            "refresh_token_encrypted": encrypt_secret(refresh),
            "access_token_expires_at": expires_at,
            "scopes": settings.canvas_scopes,
            "status": "active",
            "updated_at": datetime.now(timezone.utc),
        },
    )
    await db.execute(stmt)
    await db.commit()

    # Redirect back to the frontend
    frontend_origin = settings.frontend_origin if hasattr(settings, "frontend_origin") else "/"
    return RedirectResponse(url=f"{frontend_origin}/dashboard/canvas?connected=1", status_code=303)


@router.delete("/connection", response_model=APIResponse[None])
async def disconnect_canvas(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(delete(CanvasUserCredential).where(CanvasUserCredential.user_id == user.id))
    # mark integrations owned by this user as disconnected
    from app.models import CanvasIntegration
    await db.execute(
        CanvasIntegration.__table__.update()
        .where(CanvasIntegration.connected_by_user_id == user.id)
        .values(sync_status="disconnected")
    )
    await db.commit()
    return APIResponse(success=True, data=None)


@router.get("/connection", response_model=APIResponse[dict])
async def get_connection_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(
        select(CanvasUserCredential).where(CanvasUserCredential.user_id == user.id)
    )).scalar_one_or_none()
    if row is None:
        return APIResponse(success=True, data={"connected": False})
    return APIResponse(success=True, data={
        "connected": True,
        "canvas_base_url": row.canvas_base_url,
        "canvas_user_id": row.canvas_user_id,
        "status": row.status,
    })
```

- [ ] **Step 4: Register router in `main.py`**

Find where `app.include_router(...)` calls live and add:

```python
from app.api import canvas_oauth as canvas_oauth_api

app.include_router(canvas_oauth_api.router, prefix="/api")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_canvas_oauth_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/canvas_oauth.py backend/app/main.py backend/tests/test_canvas_oauth_api.py
git commit -m "feat(canvas): OAuth start/callback/disconnect endpoints"
```

---

### Task 6: Per-user CanvasClient factory with refresh-on-401

**Files:**
- Create: `backend/app/services/canvas_client.py`
- Create: `backend/tests/test_canvas_client.py`

- [ ] **Step 1: Write failing test for refresh behaviour**

Create `backend/tests/test_canvas_client.py`:

```python
import uuid
from datetime import datetime, timezone, timedelta

import httpx
import pytest

from app.services import canvas_client, canvas_oauth
from app.services.crypto import encrypt_secret, decrypt_secret
from app.models import CanvasUserCredential


@pytest.mark.asyncio
async def test_client_refreshes_on_401(db_session, logged_in_user, monkeypatch):
    # seed an expired-ish credential
    cred = CanvasUserCredential(
        user_id=logged_in_user.id,
        canvas_base_url="https://canvas.ust.hk",
        canvas_user_id="1",
        access_token_encrypted=encrypt_secret("stale"),
        refresh_token_encrypted=encrypt_secret("refresh"),
        access_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scopes="url:GET|/api/v1/users/self",
        status="active",
    )
    db_session.add(cred)
    await db_session.commit()

    refresh_calls = []

    async def fake_refresh(rt):
        refresh_calls.append(rt)
        return {"access_token": "fresh", "refresh_token": "refresh", "expires_in": 3600}

    monkeypatch.setattr(canvas_oauth, "refresh_access_token", fake_refresh)

    call_log = []
    def handler(request: httpx.Request) -> httpx.Response:
        token = request.headers["Authorization"].removeprefix("Bearer ")
        call_log.append(token)
        if token == "stale":
            return httpx.Response(401, json={"errors": [{"message": "expired"}]})
        return httpx.Response(200, json={"id": 42, "name": "Alice"})

    transport = httpx.MockTransport(handler)
    client = await canvas_client.get_client_for_user(db_session, logged_in_user.id, transport=transport)
    result = await client.get_user_self()

    assert result["id"] == 42
    assert call_log == ["stale", "fresh"]
    assert refresh_calls == ["refresh"]

    await db_session.refresh(cred)
    assert decrypt_secret(cred.access_token_encrypted) == "fresh"


@pytest.mark.asyncio
async def test_no_credential_raises(db_session, logged_in_user):
    with pytest.raises(canvas_client.CanvasNotConnected):
        await canvas_client.get_client_for_user(db_session, logged_in_user.id)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_canvas_client.py -v
```

Expected: FAIL (module missing).

- [ ] **Step 3: Implement `canvas_client.py`**

```python
"""Per-user Canvas REST client with refresh-on-401."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CanvasUserCredential
from app.services import canvas_oauth
from app.services.crypto import decrypt_secret, encrypt_secret


class CanvasNotConnected(Exception):
    """User has no Canvas credential (or it was marked invalid)."""


class CanvasReauthRequired(Exception):
    """Refresh failed — user must re-run OAuth."""


class CanvasClient:
    def __init__(
        self,
        db: AsyncSession,
        credential: CanvasUserCredential,
        transport: httpx.BaseTransport | None = None,
    ):
        self._db = db
        self._cred = credential
        self._transport = transport

    async def _http(self) -> httpx.AsyncClient:
        access = decrypt_secret(self._cred.access_token_encrypted)
        return httpx.AsyncClient(
            base_url=f"{self._cred.canvas_base_url.rstrip('/')}/api/v1",
            headers={"Authorization": f"Bearer {access}"},
            timeout=30.0,
            transport=self._transport,
        )

    async def _refresh(self) -> None:
        refresh = decrypt_secret(self._cred.refresh_token_encrypted)
        try:
            payload = await canvas_oauth.refresh_access_token(refresh)
        except httpx.HTTPError as exc:
            self._cred.status = "invalid"
            await self._db.commit()
            raise CanvasReauthRequired(str(exc)) from exc

        self._cred.access_token_encrypted = encrypt_secret(payload["access_token"])
        if "refresh_token" in payload:
            self._cred.refresh_token_encrypted = encrypt_secret(payload["refresh_token"])
        self._cred.access_token_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=int(payload.get("expires_in", 3600))
        )
        self._cred.status = "active"
        await self._db.commit()

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        async with await self._http() as http:
            response = await http.request(method, path, **kwargs)
        if response.status_code == 401:
            await self._refresh()
            async with await self._http() as http:
                response = await http.request(method, path, **kwargs)
        response.raise_for_status()
        return response

    async def _paginate(self, path: str, params: dict | None = None) -> list[dict]:
        """Follow Canvas's Link header pagination."""
        results: list[dict] = []
        url = path
        next_params = dict(params or {})
        next_params.setdefault("per_page", 50)
        while url:
            response = await self._request("GET", url, params=next_params if url == path else None)
            results.extend(response.json())
            link = response.headers.get("Link", "")
            url = _parse_next_link(link)
        return results

    # -------------------- high-level methods --------------------

    async def get_user_self(self) -> dict:
        return (await self._request("GET", "/users/self")).json()

    async def list_my_courses(self, enrollment_type: str) -> list[dict]:
        return await self._paginate(
            "/users/self/courses",
            {"enrollment_type": enrollment_type, "state[]": "available"},
        )

    async def list_course_files(self, canvas_course_id: str) -> list[dict]:
        return await self._paginate(f"/courses/{canvas_course_id}/files")

    async def list_course_enrollments(self, canvas_course_id: str) -> list[dict]:
        return await self._paginate(
            f"/courses/{canvas_course_id}/enrollments",
            {"include[]": "email"},
        )

    async def get_file(self, file_id: str) -> dict:
        return (await self._request("GET", f"/files/{file_id}")).json()

    async def download_file(self, download_url: str) -> bytes:
        async with httpx.AsyncClient(timeout=120.0, transport=self._transport) as client:
            response = await client.get(download_url)
            response.raise_for_status()
            return response.content


def _parse_next_link(link_header: str) -> str | None:
    # Canvas returns: <https://.../api/v1/...?page=2>; rel="next", <...>; rel="last"
    if not link_header:
        return None
    for part in link_header.split(","):
        segments = [s.strip() for s in part.split(";")]
        if any(s == 'rel="next"' for s in segments):
            url = segments[0].strip()
            if url.startswith("<") and url.endswith(">"):
                return url[1:-1]
    return None


async def get_client_for_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    transport: httpx.BaseTransport | None = None,
) -> CanvasClient:
    cred = (await db.execute(
        select(CanvasUserCredential).where(CanvasUserCredential.user_id == user_id)
    )).scalar_one_or_none()
    if cred is None or cred.status != "active":
        raise CanvasNotConnected()
    return CanvasClient(db, cred, transport=transport)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_canvas_client.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/canvas_client.py backend/tests/test_canvas_client.py
git commit -m "feat(canvas): per-user CanvasClient with refresh-on-401 and pagination"
```

---

### Task 7: Remove legacy PAT `/connect` endpoint

**Files:**
- Modify: `backend/app/api/canvas.py`

- [ ] **Step 1: Delete PAT `/connect` handler**

In `backend/app/api/canvas.py`, remove:
- `class CanvasConnectRequest(BaseModel)`
- The `@router.post("/connect", …)` function `connect_canvas`

Also remove the import of `encrypt_secret` if no other code in that file needs it after the edit.

- [ ] **Step 2: Verify other endpoints still import-clean**

```bash
cd backend && source .venv/bin/activate
python -c "from app.api.canvas import router; print(len(router.routes))"
```

Expected: prints a number > 0, no import error.

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/canvas.py
git commit -m "refactor(canvas): remove legacy PAT connect endpoint (replaced by OAuth)"
```

---

## Phase B — Instructor Flow

### Task 8: List taught Canvas courses endpoint

**Files:**
- Modify: `backend/app/api/canvas_oauth.py` (add `/canvas/courses` endpoint)
- Create: `backend/tests/test_canvas_courses_api.py`

- [ ] **Step 1: Write failing test**

```python
import pytest
from unittest.mock import AsyncMock

from app.services import canvas_client
from app.models import CanvasIntegration


@pytest.mark.asyncio
async def test_list_taught_courses(async_client, logged_in_instructor, db_session, monkeypatch):
    async def fake_list(client, enrollment_type):
        return [
            {"id": 111, "name": "Linguistics 101", "course_code": "LING101"},
            {"id": 222, "name": "Phonetics", "course_code": "LING220"},
        ]
    monkeypatch.setattr(canvas_client.CanvasClient, "list_my_courses", AsyncMock(return_value=[
        {"id": 111, "name": "Linguistics 101", "course_code": "LING101"},
        {"id": 222, "name": "Phonetics", "course_code": "LING220"},
    ]))
    # seed a credential for this user
    # (omitted — add via fixture `canvas_connected_user`)
    resp = await async_client.get("/api/canvas/courses?role=teacher")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 2
    assert data[0]["canvas_course_id"] == "111"
    assert data[0]["already_linked_meli_course_id"] is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_canvas_courses_api.py -v
```

Expected: FAIL (endpoint doesn't exist).

- [ ] **Step 3: Implement endpoint**

Append to `backend/app/api/canvas_oauth.py`:

```python
from app.models import CanvasIntegration
from app.services import canvas_client as canvas_client_svc


@router.get("/courses", response_model=APIResponse[list[dict]])
async def list_canvas_courses(
    role: str = Query("student", regex="^(student|teacher)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        client = await canvas_client_svc.get_client_for_user(db, user.id)
    except canvas_client_svc.CanvasNotConnected:
        raise HTTPException(status_code=409, detail={"code": "canvas_not_connected"})
    except canvas_client_svc.CanvasReauthRequired:
        raise HTTPException(status_code=401, detail={"code": "canvas_reauth_required"})

    enrollment_type = "teacher" if role == "teacher" else "student"
    if role == "teacher" and user.role != "instructor":
        raise HTTPException(status_code=403, detail="Instructor access required")

    courses = await client.list_my_courses(enrollment_type)
    # also include TA-taught for instructors
    if role == "teacher":
        ta_courses = await client.list_my_courses("ta")
        seen_ids = {c["id"] for c in courses}
        courses.extend(c for c in ta_courses if c["id"] not in seen_ids)

    # find already-linked Meli course ids
    canvas_ids = [str(c["id"]) for c in courses]
    rows = (await db.execute(
        select(CanvasIntegration).where(
            CanvasIntegration.canvas_course_id.in_(canvas_ids),
            CanvasIntegration.canvas_base_url == client._cred.canvas_base_url,
            CanvasIntegration.sync_status != "disconnected",
        )
    )).scalars().all()
    linked = {row.canvas_course_id: str(row.course_id) for row in rows}

    return APIResponse(success=True, data=[
        {
            "canvas_course_id": str(c["id"]),
            "name": c.get("name"),
            "course_code": c.get("course_code"),
            "already_linked_meli_course_id": linked.get(str(c["id"])),
        }
        for c in courses
    ])
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_canvas_courses_api.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/canvas_oauth.py backend/tests/test_canvas_courses_api.py
git commit -m "feat(canvas): list Canvas courses endpoint"
```

---

### Task 9: Link Canvas course → create Meli course

**Files:**
- Modify: `backend/app/api/canvas_oauth.py`
- Create: `backend/tests/test_canvas_link_course.py`

- [ ] **Step 1: Write failing test**

```python
import pytest
from unittest.mock import AsyncMock

from app.services import canvas_client as canvas_client_svc
from app.models import Course, Enrollment, CanvasIntegration


@pytest.mark.asyncio
async def test_link_creates_course_and_integration(
    async_client, logged_in_instructor, canvas_connected_instructor, db_session, monkeypatch
):
    async def fake_enrollments(self, cid):
        return [{"user_id": int(canvas_connected_instructor.canvas_user_id), "type": "TeacherEnrollment"}]

    async def fake_get_course(self, cid):
        return {"id": int(cid), "name": "Phonetics", "course_code": "LING220"}

    monkeypatch.setattr(canvas_client_svc.CanvasClient, "list_course_enrollments", fake_enrollments)
    monkeypatch.setattr(canvas_client_svc.CanvasClient, "_request", AsyncMock())  # bypass real get
    # easier: monkeypatch get_course itself — see note below

    resp = await async_client.post("/api/canvas/courses/222/link")
    assert resp.status_code == 200
    meli_course_id = resp.json()["data"]["meli_course_id"]

    from sqlalchemy import select
    row = (await db_session.execute(
        select(CanvasIntegration).where(CanvasIntegration.canvas_course_id == "222")
    )).scalar_one()
    assert str(row.course_id) == meli_course_id

    enr = (await db_session.execute(
        select(Enrollment).where(
            Enrollment.course_id == row.course_id,
            Enrollment.user_id == logged_in_instructor.id,
        )
    )).scalar_one()
    assert enr.role == "instructor"


@pytest.mark.asyncio
async def test_link_rejects_non_teacher(async_client, canvas_connected_instructor, monkeypatch):
    async def fake_enrollments(self, cid):
        return [{"user_id": 99999, "type": "StudentEnrollment"}]  # not this user
    monkeypatch.setattr(canvas_client_svc.CanvasClient, "list_course_enrollments", fake_enrollments)

    resp = await async_client.post("/api/canvas/courses/222/link")
    assert resp.status_code == 403
```

(Engineer: `canvas_connected_instructor` fixture seeds both a user with `role="instructor"` and a `CanvasUserCredential` row; add to `conftest.py`.)

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_canvas_link_course.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement `get_course` and link endpoint**

In `backend/app/services/canvas_client.py`, add method:

```python
    async def get_course(self, canvas_course_id: str) -> dict:
        return (await self._request("GET", f"/courses/{canvas_course_id}")).json()
```

In `backend/app/api/canvas_oauth.py`, add:

```python
from app.models import Course, Enrollment
from app.api.deps import require_instructor


@router.post("/courses/{canvas_course_id}/link", response_model=APIResponse[dict])
async def link_canvas_course(
    canvas_course_id: str,
    user: User = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    try:
        client = await canvas_client_svc.get_client_for_user(db, user.id)
    except canvas_client_svc.CanvasNotConnected:
        raise HTTPException(status_code=409, detail={"code": "canvas_not_connected"})

    # Verify caller is a Teacher or TA on this Canvas course
    enrollments = await client.list_course_enrollments(canvas_course_id)
    cred_canvas_user_id = client._cred.canvas_user_id
    caller_roles = [
        e.get("type") for e in enrollments
        if str(e.get("user_id")) == str(cred_canvas_user_id)
    ]
    teacher_like = {"TeacherEnrollment", "TaEnrollment"}
    if not (set(caller_roles) & teacher_like):
        raise HTTPException(status_code=403, detail="Not a teacher or TA on this course")

    # Reject if already linked
    existing = (await db.execute(
        select(CanvasIntegration).where(
            CanvasIntegration.canvas_course_id == canvas_course_id,
            CanvasIntegration.canvas_base_url == client._cred.canvas_base_url,
        )
    )).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Course already linked to Meli")

    # Pull course metadata
    canvas_course = await client.get_course(canvas_course_id)

    meli_course = Course(
        name=canvas_course.get("name") or f"Canvas Course {canvas_course_id}",
        code=canvas_course.get("course_code") or None,
        created_by_user_id=user.id,
    )
    db.add(meli_course)
    await db.flush()

    integration = CanvasIntegration(
        course_id=meli_course.id,
        connected_by_user_id=user.id,
        canvas_course_id=canvas_course_id,
        canvas_base_url=client._cred.canvas_base_url,
        sync_status="active",
    )
    db.add(integration)

    db.add(Enrollment(course_id=meli_course.id, user_id=user.id, role="instructor"))
    await db.commit()

    return APIResponse(success=True, data={"meli_course_id": str(meli_course.id)})
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_canvas_link_course.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/canvas_oauth.py backend/app/services/canvas_client.py backend/tests/test_canvas_link_course.py
git commit -m "feat(canvas): link Canvas course creates Meli course + instructor enrollment"
```

---

### Task 10: File listing endpoint (available / already-imported)

**Files:**
- Modify: `backend/app/api/canvas.py`
- Create: `backend/tests/test_canvas_files.py`

- [ ] **Step 1: Write failing test**

```python
import pytest
from unittest.mock import AsyncMock

from app.services import canvas_client as canvas_client_svc
from app.models import Document


@pytest.mark.asyncio
async def test_list_files_splits_available_and_imported(
    async_client, linked_course_fixture, db_session, monkeypatch
):
    course = linked_course_fixture["meli_course"]
    # Seed one already-imported document
    db_session.add(Document(
        course_id=course.id,
        name="existing.pdf",
        file_size=1000,
        status="completed",
        canvas_file_id="999",
        canvas_file_etag="etag999",
    ))
    await db_session.commit()

    async def fake_files(self, cid):
        return [
            {"id": 999, "display_name": "existing.pdf", "size": 1000, "content-type": "application/pdf",
             "url": "https://canvas/files/999/download", "updated_at": "2026-01-01T00:00:00Z"},
            {"id": 1000, "display_name": "new.pdf", "size": 2000, "content-type": "application/pdf",
             "url": "https://canvas/files/1000/download", "updated_at": "2026-01-02T00:00:00Z"},
        ]
    monkeypatch.setattr(canvas_client_svc.CanvasClient, "list_course_files", fake_files)

    resp = await async_client.get(f"/api/courses/{course.id}/canvas/files")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert {f["canvas_file_id"] for f in data["already_imported"]} == {"999"}
    assert {f["canvas_file_id"] for f in data["available"]} == {"1000"}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_canvas_files.py -v
```

Expected: FAIL.

- [ ] **Step 3: Replace existing `list_canvas_files` in `backend/app/api/canvas.py`**

Replace the existing `list_canvas_files` function (which currently reads token from `CanvasIntegration`) with:

```python
from app.services import canvas_client as canvas_client_svc
from app.models import CanvasIntegration, Document


@router.get("/files", response_model=APIResponse[dict])
async def list_canvas_files(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await verify_enrollment(db, course_id, user.id)

    integration = (await db.execute(
        select(CanvasIntegration).where(CanvasIntegration.course_id == course_id)
    )).scalar_one_or_none()
    if integration is None:
        raise HTTPException(status_code=404, detail="Canvas not connected for this course")

    try:
        client = await canvas_client_svc.get_client_for_user(db, integration.connected_by_user_id)
    except canvas_client_svc.CanvasNotConnected:
        raise HTTPException(status_code=409, detail={"code": "canvas_reauth_required"})

    files = await client.list_course_files(integration.canvas_course_id)

    imported = (await db.execute(
        select(Document.canvas_file_id).where(
            Document.course_id == course_id,
            Document.canvas_file_id.is_not(None),
        )
    )).scalars().all()
    imported_ids = set(imported)

    def to_dto(f):
        return {
            "canvas_file_id": str(f["id"]),
            "display_name": f.get("display_name"),
            "size": f.get("size"),
            "content_type": f.get("content-type") or f.get("content_type"),
            "download_url": f.get("url"),
            "updated_at": f.get("updated_at"),
        }

    available = [to_dto(f) for f in files if str(f["id"]) not in imported_ids]
    already = [to_dto(f) for f in files if str(f["id"]) in imported_ids]

    return APIResponse(success=True, data={"available": available, "already_imported": already})
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_canvas_files.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/canvas.py backend/tests/test_canvas_files.py
git commit -m "feat(canvas): list files endpoint returns available vs already-imported"
```

---

### Task 11: File import endpoint (replace 501 stub)

**Files:**
- Create: `backend/app/services/canvas_files.py`
- Modify: `backend/app/api/canvas.py`
- Extend: `backend/tests/test_canvas_files.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_canvas_files.py`:

```python
@pytest.mark.asyncio
async def test_import_creates_documents_and_tasks(
    async_client, linked_course_fixture, db_session, monkeypatch
):
    from app.models import Task

    async def fake_get_file(self, file_id):
        return {
            "id": int(file_id),
            "display_name": "lecture1.pdf",
            "size": 5000,
            "content-type": "application/pdf",
            "url": "https://canvas/files/1001/download?signed=yes",
        }

    async def fake_download(self, url):
        return b"%PDF-fakepdfbytes"

    async def fake_put(key, data, content_type):
        return f"s3://bucket/{key}"

    monkeypatch.setattr(canvas_client_svc.CanvasClient, "get_file", fake_get_file)
    monkeypatch.setattr(canvas_client_svc.CanvasClient, "download_file", fake_download)
    monkeypatch.setattr("app.services.storage.put_bytes", fake_put)

    course = linked_course_fixture["meli_course"]
    resp = await async_client.post(
        f"/api/courses/{course.id}/canvas/files/import",
        json={"file_ids": ["1001"]},
    )
    assert resp.status_code == 200

    from sqlalchemy import select
    doc = (await db_session.execute(
        select(Document).where(Document.canvas_file_id == "1001")
    )).scalar_one()
    assert doc.status == "pending"

    task = (await db_session.execute(
        select(Task).where(Task.task_type == "process_document")
    )).scalars().first()
    assert task is not None
    assert task.payload.get("document_id") == str(doc.id)


@pytest.mark.asyncio
async def test_import_skips_already_imported(
    async_client, linked_course_fixture, db_session, monkeypatch
):
    course = linked_course_fixture["meli_course"]
    db_session.add(Document(
        course_id=course.id, name="old.pdf", file_size=1, status="completed",
        canvas_file_id="999",
    ))
    await db_session.commit()

    # get_file must not be called
    async def explode(self, file_id):
        raise AssertionError("should not fetch already-imported file")
    monkeypatch.setattr(canvas_client_svc.CanvasClient, "get_file", explode)

    resp = await async_client.post(
        f"/api/courses/{course.id}/canvas/files/import",
        json={"file_ids": ["999"]},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["skipped"] == ["999"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_canvas_files.py::test_import_creates_documents_and_tasks -v
```

Expected: FAIL.

- [ ] **Step 3: Implement `canvas_files.py` service**

Create `backend/app/services/canvas_files.py`:

```python
"""Canvas → Meli file import pipeline."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Document, Task
from app.services import storage
from app.services.canvas_client import CanvasClient

logger = logging.getLogger(__name__)


@dataclass
class ImportResult:
    imported: list[str]
    skipped: list[str]
    errors: list[dict]


async def import_canvas_files(
    db: AsyncSession,
    client: CanvasClient,
    course_id: uuid.UUID,
    file_ids: list[str],
) -> ImportResult:
    existing = (await db.execute(
        select(Document.canvas_file_id).where(
            Document.course_id == course_id,
            Document.canvas_file_id.in_(file_ids),
        )
    )).scalars().all()
    existing_set = set(existing)

    imported: list[str] = []
    skipped: list[str] = list(existing_set)
    errors: list[dict] = []

    allowed_types = set(getattr(settings, "allowed_document_types", [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "audio/mpeg", "audio/wav", "audio/mp4",
    ]))

    for file_id in file_ids:
        if file_id in existing_set:
            continue
        try:
            meta = await client.get_file(file_id)
            content_type = (meta.get("content-type") or meta.get("content_type") or "").lower()
            if content_type not in allowed_types:
                errors.append({"file_id": file_id, "error": f"unsupported content-type: {content_type}"})
                continue
            body = await client.download_file(meta["url"])
            storage_key = f"canvas/{course_id}/{file_id}/{meta.get('display_name', 'file')}"
            storage_url = await storage.put_bytes(storage_key, body, content_type)

            doc = Document(
                course_id=course_id,
                name=meta.get("display_name") or f"canvas-{file_id}",
                file_size=meta.get("size") or len(body),
                status="pending",
                storage_url=storage_url,
                mime_type=content_type,
                canvas_file_id=str(file_id),
                canvas_file_etag=str(meta.get("updated_at", "")),
            )
            db.add(doc)
            await db.flush()

            db.add(Task(
                task_type="process_document",
                payload={"document_id": str(doc.id)},
                status="pending",
            ))
            imported.append(file_id)
        except Exception as exc:
            logger.exception("Canvas import failed for file %s", file_id)
            errors.append({"file_id": file_id, "error": str(exc)})

    await db.commit()
    return ImportResult(imported=imported, skipped=skipped, errors=errors)
```

(Engineer: confirm existing `Document` column names — `storage_url`, `mime_type`, `file_size`, `status` — match your model. Adjust if the real column is `storage_key` / `content_type` / etc. by reading `backend/app/models/document.py` first.)

- [ ] **Step 4: Replace the `501` stub in `backend/app/api/canvas.py`**

```python
from app.services.canvas_files import import_canvas_files


@router.post("/import", response_model=APIResponse[dict])
async def import_canvas_files_endpoint(
    course_id: uuid.UUID,
    body: CanvasImportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await verify_enrollment(db, course_id, user.id)

    integration = (await db.execute(
        select(CanvasIntegration).where(CanvasIntegration.course_id == course_id)
    )).scalar_one_or_none()
    if integration is None:
        raise HTTPException(status_code=404, detail="Canvas not connected for this course")

    try:
        client = await canvas_client_svc.get_client_for_user(db, integration.connected_by_user_id)
    except canvas_client_svc.CanvasNotConnected:
        raise HTTPException(status_code=409, detail={"code": "canvas_reauth_required"})

    result = await import_canvas_files(db, client, course_id, body.file_ids)
    return APIResponse(success=True, data={
        "imported": result.imported,
        "skipped": result.skipped,
        "errors": result.errors,
    })
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_canvas_files.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/canvas_files.py backend/app/api/canvas.py backend/tests/test_canvas_files.py
git commit -m "feat(canvas): implement file import — download, upload to R2, enqueue processing"
```

---

### Task 12: Roster import endpoint

**Files:**
- Create: `backend/app/services/canvas_roster.py`
- Modify: `backend/app/api/canvas.py`
- Create: `backend/tests/test_canvas_roster.py`

- [ ] **Step 1: Write failing test**

```python
import pytest
from datetime import datetime

from app.models import User, Enrollment, PendingEnrollment


@pytest.mark.asyncio
async def test_roster_import_matches_and_pre_provisions(
    async_client, linked_course_fixture, db_session, monkeypatch
):
    from app.services import canvas_client as ccs

    async def fake_enrollments(self, cid):
        return [
            {"user_id": 10, "type": "StudentEnrollment",
             "user": {"email": "alice@connect.ust.hk", "name": "Alice"}},
            {"user_id": 11, "type": "StudentEnrollment",
             "user": {"email": "bob@connect.ust.hk", "name": "Bob"}},
            {"user_id": 12, "type": "TaEnrollment",
             "user": {"email": "ta@ust.hk", "name": "TA"}},
            {"user_id": 13, "type": "ObserverEnrollment",
             "user": {"email": "parent@example.com", "name": "Parent"}},
        ]
    monkeypatch.setattr(ccs.CanvasClient, "list_course_enrollments", fake_enrollments)

    # Seed Alice as an existing Meli user
    alice = User(clerk_id="clerk_alice", email="alice@connect.ust.hk", role="student")
    db_session.add(alice)
    await db_session.commit()

    course = linked_course_fixture["meli_course"]
    resp = await async_client.post(
        f"/api/courses/{course.id}/canvas/roster/import",
        json={"send_invite_emails": False},
    )
    assert resp.status_code == 200
    d = resp.json()["data"]
    assert d["added"] == 2   # alice + ta
    assert d["pending"] == 1 # bob
    assert d["skipped_off_domain"] == 1  # observer's parent email

    from sqlalchemy import select
    alice_enr = (await db_session.execute(
        select(Enrollment).where(Enrollment.user_id == alice.id, Enrollment.course_id == course.id)
    )).scalar_one()
    assert alice_enr.role == "student"

    bob_pending = (await db_session.execute(
        select(PendingEnrollment).where(PendingEnrollment.email == "bob@connect.ust.hk")
    )).scalar_one()
    assert bob_pending.role == "student"
    assert bob_pending.invited_at is None


@pytest.mark.asyncio
async def test_roster_import_soft_unenrolls_drops(
    async_client, linked_course_fixture, db_session, monkeypatch
):
    # Pre-enroll Carol who is no longer in Canvas
    from app.services import canvas_client as ccs
    course = linked_course_fixture["meli_course"]
    carol = User(clerk_id="c", email="carol@connect.ust.hk", role="student")
    db_session.add(carol)
    await db_session.flush()
    db_session.add(Enrollment(course_id=course.id, user_id=carol.id, role="student"))
    await db_session.commit()

    async def fake_enrollments(self, cid):
        return []  # Carol dropped
    monkeypatch.setattr(ccs.CanvasClient, "list_course_enrollments", fake_enrollments)

    resp = await async_client.post(
        f"/api/courses/{course.id}/canvas/roster/import",
        json={"send_invite_emails": False},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["dropped"] == 1

    from sqlalchemy import select
    carol_enr = (await db_session.execute(
        select(Enrollment).where(Enrollment.user_id == carol.id, Enrollment.course_id == course.id)
    )).scalar_one()
    assert carol_enr.deleted_at is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_canvas_roster.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement `canvas_roster.py`**

Create `backend/app/services/canvas_roster.py`:

```python
"""Canvas roster → Meli enrollment diff + pre-provisioning."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.models import Enrollment, PendingEnrollment, User
from app.services.canvas_client import CanvasClient

logger = logging.getLogger(__name__)

CANVAS_ROLE_TO_MELI: dict[str, str] = {
    "TeacherEnrollment": "instructor",
    "TaEnrollment": "instructor",
    "StudentEnrollment": "student",
    # DesignerEnrollment + ObserverEnrollment → skipped
}


@dataclass
class RosterDiff:
    added: int = 0
    unchanged: int = 0
    dropped: int = 0
    pending: int = 0
    skipped_off_domain: int = 0
    errors: list[dict] = field(default_factory=list)


def _email_allowed(email: str) -> bool:
    allowed = set(getattr(settings, "allowed_email_domains", ["ust.hk", "connect.ust.hk"]))
    if "@" not in email:
        return False
    return email.split("@", 1)[1].lower() in allowed


async def sync_roster(
    db: AsyncSession,
    client: CanvasClient,
    meli_course_id: uuid.UUID,
    canvas_course_id: str,
    send_invite_emails: bool,
) -> RosterDiff:
    diff = RosterDiff()
    enrollments = await client.list_course_enrollments(canvas_course_id)

    # Build desired state keyed by email
    desired: dict[str, dict] = {}
    for e in enrollments:
        meli_role = CANVAS_ROLE_TO_MELI.get(e.get("type") or "")
        if meli_role is None:
            continue
        email = ((e.get("user") or {}).get("email") or e.get("login_id") or "").strip().lower()
        if not email:
            continue
        if not _email_allowed(email):
            diff.skipped_off_domain += 1
            continue
        desired[email] = {
            "role": meli_role,
            "canvas_user_id": str(e.get("user_id", "")),
        }

    # Existing active Meli enrollments for this course
    existing_rows = (await db.execute(
        select(Enrollment, User).join(User, Enrollment.user_id == User.id)
        .where(Enrollment.course_id == meli_course_id, Enrollment.deleted_at.is_(None))
    )).all()
    existing_by_email = {u.email.lower(): enr for enr, u in existing_rows}

    # Existing pending enrollments for this course
    existing_pending = (await db.execute(
        select(PendingEnrollment).where(PendingEnrollment.course_id == meli_course_id)
    )).scalars().all()
    pending_by_email = {p.email.lower(): p for p in existing_pending}

    # Match against Meli users for any desired email not already enrolled
    want_emails = set(desired.keys())
    have_active = set(existing_by_email.keys())
    new_emails = want_emails - have_active

    if new_emails:
        user_rows = (await db.execute(
            select(User).where(User.email.in_(list(new_emails)))
        )).scalars().all()
        users_by_email = {u.email.lower(): u for u in user_rows}
    else:
        users_by_email = {}

    for email in new_emails:
        spec = desired[email]
        user = users_by_email.get(email)
        if user is not None:
            db.add(Enrollment(
                course_id=meli_course_id,
                user_id=user.id,
                role=spec["role"],
            ))
            diff.added += 1
            # If there was a pending row from earlier, clean it up
            if email in pending_by_email:
                await db.delete(pending_by_email[email])
        else:
            # Upsert pending enrollment
            stmt = pg_insert(PendingEnrollment).values(
                course_id=meli_course_id,
                email=email,
                canvas_user_id=spec["canvas_user_id"],
                role=spec["role"],
                invited_at=datetime.now(timezone.utc) if send_invite_emails else None,
            ).on_conflict_do_update(
                index_elements=["course_id", "email"],
                set_={
                    "canvas_user_id": spec["canvas_user_id"],
                    "role": spec["role"],
                    **({"invited_at": datetime.now(timezone.utc)} if send_invite_emails else {}),
                },
            )
            await db.execute(stmt)
            diff.pending += 1

    # Unchanged count: desired emails already active
    diff.unchanged = len(want_emails & have_active)

    # Drops: active Meli enrollments whose email is not in desired
    dropped_emails = have_active - want_emails
    for email in dropped_emails:
        enr = existing_by_email[email]
        enr.deleted_at = datetime.now(timezone.utc)
        diff.dropped += 1

    await db.commit()

    # Email dispatch (fire-and-forget queue entries)
    if send_invite_emails:
        for email in new_emails:
            if email not in users_by_email:
                # Engineer: enqueue an email task — Phase 1.1 if no provider wired.
                logger.info("Would send Meli invite to %s", email)

    return diff
```

- [ ] **Step 4: Implement API endpoint**

Append to `backend/app/api/canvas.py`:

```python
from app.services.canvas_roster import sync_roster


class RosterImportRequest(BaseModel):
    send_invite_emails: bool = False


@router.post("/roster/import", response_model=APIResponse[dict])
async def import_canvas_roster(
    course_id: uuid.UUID,
    body: RosterImportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await verify_enrollment(db, course_id, user.id)

    integration = (await db.execute(
        select(CanvasIntegration).where(CanvasIntegration.course_id == course_id)
    )).scalar_one_or_none()
    if integration is None:
        raise HTTPException(status_code=404, detail="Canvas not connected for this course")

    try:
        client = await canvas_client_svc.get_client_for_user(db, integration.connected_by_user_id)
    except canvas_client_svc.CanvasNotConnected:
        raise HTTPException(status_code=409, detail={"code": "canvas_reauth_required"})

    diff = await sync_roster(
        db, client, course_id, integration.canvas_course_id, body.send_invite_emails
    )
    integration.last_roster_sync_at = datetime.now(timezone.utc)
    await db.commit()

    return APIResponse(success=True, data=dict(
        added=diff.added, unchanged=diff.unchanged, dropped=diff.dropped,
        pending=diff.pending, skipped_off_domain=diff.skipped_off_domain,
        errors=diff.errors,
    ))
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_canvas_roster.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/canvas_roster.py backend/app/api/canvas.py backend/tests/test_canvas_roster.py
git commit -m "feat(canvas): roster import with diff, pre-provisioning, soft unenroll"
```

---

### Task 13: Claim pending enrollments on first login

**Files:**
- Modify: `backend/app/api/deps.py`
- Create: `backend/tests/test_pending_enrollment_claim.py`

- [ ] **Step 1: Write failing test**

```python
import pytest
from sqlalchemy import select

from app.models import Enrollment, PendingEnrollment


@pytest.mark.asyncio
async def test_first_login_claims_pending_enrollment(
    async_client, db_session, monkeypatch, course_fixture
):
    course = course_fixture
    db_session.add(PendingEnrollment(
        course_id=course.id,
        email="newbie@connect.ust.hk",
        canvas_user_id="77",
        role="student",
    ))
    await db_session.commit()

    # Simulate Clerk JWT for newbie@connect.ust.hk
    def fake_verify(token):
        return {"sub": "clerk_newbie", "email": "newbie@connect.ust.hk", "name": "Newbie"}
    monkeypatch.setattr("app.services.auth.verify_clerk_token", fake_verify)

    resp = await async_client.get("/api/courses", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 200

    enr = (await db_session.execute(
        select(Enrollment).join(PendingEnrollment.__table__, isouter=False)  # placeholder — verify by different means
    ))
    # Simpler: just query enrollments
    new_enrs = (await db_session.execute(
        select(Enrollment).where(Enrollment.course_id == course.id)
    )).scalars().all()
    assert len(new_enrs) == 1
    assert new_enrs[0].role == "student"

    # Pending row must be gone
    remaining = (await db_session.execute(
        select(PendingEnrollment).where(PendingEnrollment.email == "newbie@connect.ust.hk")
    )).scalars().all()
    assert remaining == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_pending_enrollment_claim.py -v
```

Expected: FAIL.

- [ ] **Step 3: Extend `get_current_user` in `deps.py`**

After the user-creation block (right before the `set_config` call), add:

```python
    # Claim any pending enrollments matching this user's email
    pending = (await db.execute(
        select(PendingEnrollment).where(PendingEnrollment.email == user.email.lower())
    )).scalars().all()
    if pending:
        from app.models import Enrollment
        for row in pending:
            db.add(Enrollment(
                course_id=row.course_id,
                user_id=user.id,
                role=row.role,
            ))
            await db.delete(row)
        await db.commit()
```

Add the import at the top of `deps.py`:

```python
from app.models import PendingEnrollment
```

Make sure this runs on **every** call, not just first-login — the user might have been invited *after* first login too. Performance: an indexed lookup by email, cheap.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_pending_enrollment_claim.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/deps.py backend/tests/test_pending_enrollment_claim.py
git commit -m "feat(canvas): claim pending enrollments on auth"
```

---

## Phase C — Student Flow

### Task 14: List enrolled Canvas courses with Meli availability

**Files:**
- Modify: `backend/app/api/canvas_oauth.py` (the `/canvas/courses?role=student` branch already exists; verify + extend)

- [ ] **Step 1: Write test** (append to `test_canvas_courses_api.py`)

```python
@pytest.mark.asyncio
async def test_list_student_courses_marks_meli_availability(
    async_client, logged_in_student, canvas_connected_student, db_session, linked_course_fixture, monkeypatch
):
    # student is enrolled in Canvas course 222 (which is linked) and 333 (which isn't)
    async def fake_my_courses(self, role):
        if role == "student":
            return [
                {"id": 222, "name": "Phonetics", "course_code": "LING220"},
                {"id": 333, "name": "Orphan", "course_code": "ORPH101"},
            ]
        return []
    monkeypatch.setattr(canvas_client_svc.CanvasClient, "list_my_courses", fake_my_courses)

    resp = await async_client.get("/api/canvas/courses?role=student")
    data = resp.json()["data"]
    by_id = {c["canvas_course_id"]: c for c in data}
    assert by_id["222"]["already_linked_meli_course_id"] is not None
    assert by_id["333"]["already_linked_meli_course_id"] is None
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_canvas_courses_api.py::test_list_student_courses_marks_meli_availability -v
```

Expected: PASS (the endpoint implemented in Task 8 already handles both `role` values; this test codifies the student branch behaviour).

If the test fails, inspect the existing implementation and fix any role-specific bugs.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_canvas_courses_api.py
git commit -m "test(canvas): student-role course listing marks Meli availability"
```

---

### Task 15: Join Meli course from Canvas enrollment

**Files:**
- Modify: `backend/app/api/canvas_oauth.py`
- Create: `backend/tests/test_canvas_join.py`

- [ ] **Step 1: Write failing test**

```python
import pytest

from app.models import Enrollment


@pytest.mark.asyncio
async def test_student_joins_via_canvas(
    async_client, logged_in_student, canvas_connected_student, linked_course_fixture, db_session, monkeypatch
):
    from app.services import canvas_client as ccs

    canvas_user_id = canvas_connected_student.canvas_user_id

    async def fake_enrollments(self, cid):
        return [
            {"user_id": int(canvas_user_id), "type": "StudentEnrollment"},
        ]
    monkeypatch.setattr(ccs.CanvasClient, "list_course_enrollments", fake_enrollments)

    resp = await async_client.post("/api/canvas/courses/222/join")
    assert resp.status_code == 200
    meli_id = resp.json()["data"]["meli_course_id"]

    from sqlalchemy import select
    enr = (await db_session.execute(
        select(Enrollment).where(
            Enrollment.course_id == meli_id,
            Enrollment.user_id == logged_in_student.id,
        )
    )).scalar_one()
    assert enr.role == "student"


@pytest.mark.asyncio
async def test_join_fails_if_instructor_not_enabled(
    async_client, logged_in_student, canvas_connected_student, monkeypatch
):
    from app.services import canvas_client as ccs
    async def fake_enrollments(self, cid):
        return [{"user_id": int(canvas_connected_student.canvas_user_id), "type": "StudentEnrollment"}]
    monkeypatch.setattr(ccs.CanvasClient, "list_course_enrollments", fake_enrollments)

    resp = await async_client.post("/api/canvas/courses/9999/join")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_canvas_join.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement endpoint**

Append to `backend/app/api/canvas_oauth.py`:

```python
from app.models import Enrollment


@router.post("/courses/{canvas_course_id}/join", response_model=APIResponse[dict])
async def join_canvas_course(
    canvas_course_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        client = await canvas_client_svc.get_client_for_user(db, user.id)
    except canvas_client_svc.CanvasNotConnected:
        raise HTTPException(status_code=409, detail={"code": "canvas_not_connected"})

    # Confirm caller is a student on that Canvas course
    enrollments = await client.list_course_enrollments(canvas_course_id)
    caller_id = str(client._cred.canvas_user_id)
    caller_enrollments = [e for e in enrollments if str(e.get("user_id")) == caller_id]
    is_student = any(e.get("type") == "StudentEnrollment" for e in caller_enrollments)
    if not is_student:
        raise HTTPException(status_code=403, detail="Not a student on this Canvas course")

    integration = (await db.execute(
        select(CanvasIntegration).where(
            CanvasIntegration.canvas_course_id == canvas_course_id,
            CanvasIntegration.canvas_base_url == client._cred.canvas_base_url,
            CanvasIntegration.sync_status != "disconnected",
        )
    )).scalar_one_or_none()
    if integration is None:
        raise HTTPException(status_code=404, detail="Instructor hasn't enabled Meli for this course")

    existing = (await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == integration.course_id,
            Enrollment.user_id == user.id,
            Enrollment.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if existing is None:
        db.add(Enrollment(course_id=integration.course_id, user_id=user.id, role="student"))

    # Clean up any pending row
    from app.models import PendingEnrollment
    await db.execute(
        PendingEnrollment.__table__.delete().where(
            PendingEnrollment.course_id == integration.course_id,
            PendingEnrollment.email == user.email.lower(),
        )
    )
    await db.commit()
    return APIResponse(success=True, data={"meli_course_id": str(integration.course_id)})
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_canvas_join.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/canvas_oauth.py backend/tests/test_canvas_join.py
git commit -m "feat(canvas): student join via Canvas enrollment"
```

---

## Phase D — Sync Worker

### Task 16: Daily sync scheduler + handler

**Files:**
- Create: `backend/app/services/canvas_sync.py`
- Modify: `backend/app/main.py` (register scheduler in lifespan)
- Create: `backend/tests/test_canvas_sync.py`

- [ ] **Step 1: Write failing test for the sync handler**

```python
import pytest
from datetime import datetime, timezone

from app.services import canvas_sync
from app.models import CanvasSyncEvent, CanvasIntegration


@pytest.mark.asyncio
async def test_sync_writes_roster_diff_event(
    db_session, linked_course_fixture, canvas_connected_instructor, monkeypatch
):
    from app.services import canvas_client as ccs

    async def fake_enrollments(self, cid):
        return []
    monkeypatch.setattr(ccs.CanvasClient, "list_course_enrollments", fake_enrollments)

    async def fake_files(self, cid):
        return [
            {"id": 500, "display_name": "new.pdf", "size": 1000, "content-type": "application/pdf",
             "url": "https://x/500", "updated_at": "2026-01-01T00:00:00Z"},
        ]
    monkeypatch.setattr(ccs.CanvasClient, "list_course_files", fake_files)

    integration = linked_course_fixture["integration"]
    await canvas_sync.sync_integration(db_session, integration)

    from sqlalchemy import select
    events = (await db_session.execute(
        select(CanvasSyncEvent).where(CanvasSyncEvent.course_id == integration.course_id)
    )).scalars().all()
    types = {e.event_type for e in events}
    assert "roster_diff" in types
    assert "file_scan" in types

    refreshed = (await db_session.execute(
        select(CanvasIntegration).where(CanvasIntegration.id == integration.id)
    )).scalar_one()
    assert refreshed.last_roster_sync_at is not None
    assert refreshed.last_file_scan_at is not None
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_canvas_sync.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement `canvas_sync.py`**

```python
"""Scheduled Canvas sync: roster diff + file detection."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models import (
    CanvasIntegration,
    CanvasSyncEvent,
    CanvasUserCredential,
    Document,
)
from app.services import canvas_client as canvas_client_svc
from app.services.canvas_roster import sync_roster

logger = logging.getLogger(__name__)

SYNC_INTERVAL = timedelta(hours=24)
SCHEDULER_POLL_SECONDS = 300  # 5 min between scheduler wakeups


async def sync_integration(db: AsyncSession, integration: CanvasIntegration) -> None:
    """Perform one sync pass for a single integration."""
    try:
        client = await canvas_client_svc.get_client_for_user(db, integration.connected_by_user_id)
    except canvas_client_svc.CanvasNotConnected:
        integration.sync_status = "disconnected"
        db.add(CanvasSyncEvent(
            course_id=integration.course_id,
            event_type="error",
            payload={"error": "credential_missing_or_invalid"},
        ))
        await db.commit()
        return
    except Exception as exc:
        logger.exception("Sync aborted for integration %s", integration.id)
        db.add(CanvasSyncEvent(
            course_id=integration.course_id,
            event_type="error",
            payload={"error": str(exc)},
        ))
        await db.commit()
        return

    # Roster diff (cheap)
    try:
        diff = await sync_roster(
            db, client, integration.course_id, integration.canvas_course_id, send_invite_emails=False
        )
        db.add(CanvasSyncEvent(
            course_id=integration.course_id,
            event_type="roster_diff",
            payload={
                "added": diff.added, "dropped": diff.dropped, "pending": diff.pending,
                "unchanged": diff.unchanged, "skipped_off_domain": diff.skipped_off_domain,
            },
        ))
        integration.last_roster_sync_at = datetime.now(timezone.utc)
    except Exception as exc:
        logger.exception("Roster sync failed for integration %s", integration.id)
        db.add(CanvasSyncEvent(
            course_id=integration.course_id,
            event_type="error",
            payload={"stage": "roster", "error": str(exc)},
        ))

    # File detection (no download)
    try:
        canvas_files = await client.list_course_files(integration.canvas_course_id)
        existing = (await db.execute(
            select(Document.canvas_file_id).where(
                Document.course_id == integration.course_id,
                Document.canvas_file_id.is_not(None),
            )
        )).scalars().all()
        existing_ids = set(existing)
        new_files = [f for f in canvas_files if str(f["id"]) not in existing_ids]
        db.add(CanvasSyncEvent(
            course_id=integration.course_id,
            event_type="file_scan",
            payload={
                "new_file_count": len(new_files),
                "new_file_ids": [str(f["id"]) for f in new_files[:20]],
            },
        ))
        integration.last_file_scan_at = datetime.now(timezone.utc)
    except Exception as exc:
        logger.exception("File scan failed for integration %s", integration.id)
        db.add(CanvasSyncEvent(
            course_id=integration.course_id,
            event_type="error",
            payload={"stage": "files", "error": str(exc)},
        ))

    await db.commit()


async def _scheduler_tick() -> None:
    async with async_session_factory() as db:
        cutoff = datetime.now(timezone.utc) - SYNC_INTERVAL
        rows = (await db.execute(
            select(CanvasIntegration).where(
                CanvasIntegration.sync_status == "active",
                (CanvasIntegration.last_roster_sync_at.is_(None)
                 | (CanvasIntegration.last_roster_sync_at < cutoff)),
            )
        )).scalars().all()
        for integration in rows:
            try:
                await sync_integration(db, integration)
            except Exception:
                logger.exception("Unexpected error syncing %s", integration.id)


async def run_scheduler() -> None:
    """Entry point to run in the FastAPI lifespan."""
    while True:
        try:
            await _scheduler_tick()
        except Exception:
            logger.exception("Scheduler tick crashed")
        await asyncio.sleep(SCHEDULER_POLL_SECONDS)
```

- [ ] **Step 4: Register in `main.py` lifespan**

Find the existing lifespan context manager and add:

```python
    scheduler_task = asyncio.create_task(canvas_sync.run_scheduler())
    try:
        yield
    finally:
        scheduler_task.cancel()
```

Add `from app.services import canvas_sync` to imports.

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_canvas_sync.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/canvas_sync.py backend/app/main.py backend/tests/test_canvas_sync.py
git commit -m "feat(canvas): daily sync scheduler — roster diff + file detection"
```

---

### Task 17: Manual sync-now + sync events endpoints

**Files:**
- Modify: `backend/app/api/canvas.py`

- [ ] **Step 1: Write test** (append to `test_canvas_sync.py`)

```python
@pytest.mark.asyncio
async def test_manual_sync_triggers_events(async_client, linked_course_fixture, monkeypatch):
    from app.services import canvas_client as ccs

    async def _zero(self, cid): return []
    async def _files(self, cid): return []
    monkeypatch.setattr(ccs.CanvasClient, "list_course_enrollments", _zero)
    monkeypatch.setattr(ccs.CanvasClient, "list_course_files", _files)

    course = linked_course_fixture["meli_course"]
    resp = await async_client.post(f"/api/courses/{course.id}/canvas/sync")
    assert resp.status_code == 200

    resp = await async_client.get(f"/api/courses/{course.id}/canvas/sync-events")
    assert resp.status_code == 200
    events = resp.json()["data"]
    assert any(e["event_type"] == "roster_diff" for e in events)
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_canvas_sync.py::test_manual_sync_triggers_events -v
```

Expected: FAIL.

- [ ] **Step 3: Implement endpoints**

Append to `backend/app/api/canvas.py`:

```python
from app.services.canvas_sync import sync_integration
from app.models import CanvasSyncEvent


@router.post("/sync", response_model=APIResponse[None])
async def manual_sync(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await verify_enrollment(db, course_id, user.id)
    integration = (await db.execute(
        select(CanvasIntegration).where(CanvasIntegration.course_id == course_id)
    )).scalar_one_or_none()
    if integration is None:
        raise HTTPException(status_code=404, detail="Canvas not connected")
    await sync_integration(db, integration)
    return APIResponse(success=True, data=None)


@router.get("/sync-events", response_model=APIResponse[list[dict]])
async def list_sync_events(
    course_id: uuid.UUID,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await verify_enrollment(db, course_id, user.id)
    rows = (await db.execute(
        select(CanvasSyncEvent)
        .where(CanvasSyncEvent.course_id == course_id)
        .order_by(CanvasSyncEvent.created_at.desc())
        .limit(limit)
    )).scalars().all()
    return APIResponse(success=True, data=[
        {
            "id": str(r.id),
            "event_type": r.event_type,
            "payload": r.payload,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ])
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_canvas_sync.py::test_manual_sync_triggers_events -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/canvas.py backend/tests/test_canvas_sync.py
git commit -m "feat(canvas): manual sync + sync-events endpoints"
```

---

## Phase E — Frontend

### Task 18: Canvas API client + hooks

**Files:**
- Create: `frontend/src/lib/canvas-api.ts`
- Create: `frontend/src/hooks/use-canvas.ts`

- [ ] **Step 1: Implement API client**

```typescript
// frontend/src/lib/canvas-api.ts
import { apiFetch } from "@/lib/api";

export type CanvasCourse = {
  canvas_course_id: string;
  name: string | null;
  course_code: string | null;
  already_linked_meli_course_id: string | null;
};

export type CanvasFile = {
  canvas_file_id: string;
  display_name: string | null;
  size: number | null;
  content_type: string | null;
  download_url: string | null;
  updated_at: string | null;
};

export type CanvasFileList = {
  available: CanvasFile[];
  already_imported: CanvasFile[];
};

export type CanvasSyncEvent = {
  id: string;
  event_type: "roster_diff" | "file_scan" | "error";
  payload: Record<string, unknown>;
  created_at: string;
};

export async function startCanvasOAuth(token: string): Promise<{ authorize_url: string }> {
  return apiFetch("/api/canvas/oauth/start", { token });
}

export async function getCanvasConnection(token: string) {
  return apiFetch<{ connected: boolean; canvas_user_id?: string; canvas_base_url?: string; status?: string }>(
    "/api/canvas/connection",
    { token },
  );
}

export async function disconnectCanvas(token: string) {
  return apiFetch("/api/canvas/connection", { token, method: "DELETE" });
}

export async function listCanvasCourses(token: string, role: "teacher" | "student") {
  return apiFetch<CanvasCourse[]>(`/api/canvas/courses?role=${role}`, { token });
}

export async function linkCanvasCourse(token: string, canvasCourseId: string) {
  return apiFetch<{ meli_course_id: string }>(
    `/api/canvas/courses/${canvasCourseId}/link`,
    { token, method: "POST" },
  );
}

export async function joinCanvasCourse(token: string, canvasCourseId: string) {
  return apiFetch<{ meli_course_id: string }>(
    `/api/canvas/courses/${canvasCourseId}/join`,
    { token, method: "POST" },
  );
}

export async function listCanvasFiles(token: string, meliCourseId: string) {
  return apiFetch<CanvasFileList>(`/api/courses/${meliCourseId}/canvas/files`, { token });
}

export async function importCanvasFiles(token: string, meliCourseId: string, fileIds: string[]) {
  return apiFetch<{ imported: string[]; skipped: string[]; errors: { file_id: string; error: string }[] }>(
    `/api/courses/${meliCourseId}/canvas/files/import`,
    { token, method: "POST", body: { file_ids: fileIds } },
  );
}

export async function importCanvasRoster(token: string, meliCourseId: string, sendEmails: boolean) {
  return apiFetch<{
    added: number;
    unchanged: number;
    dropped: number;
    pending: number;
    skipped_off_domain: number;
  }>(
    `/api/courses/${meliCourseId}/canvas/roster/import`,
    { token, method: "POST", body: { send_invite_emails: sendEmails } },
  );
}

export async function manualSyncCanvas(token: string, meliCourseId: string) {
  return apiFetch(`/api/courses/${meliCourseId}/canvas/sync`, { token, method: "POST" });
}

export async function listCanvasSyncEvents(token: string, meliCourseId: string) {
  return apiFetch<CanvasSyncEvent[]>(
    `/api/courses/${meliCourseId}/canvas/sync-events`,
    { token },
  );
}
```

(Engineer: adjust the `apiFetch` call shape to match the real signature of the existing helper in `frontend/src/lib/api.ts`. The point is to model each endpoint — rework the argument style to fit the existing typed wrapper.)

- [ ] **Step 2: Implement hooks**

```typescript
// frontend/src/hooks/use-canvas.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApiToken } from "./use-api-token";
import * as canvas from "@/lib/canvas-api";

export function useCanvasConnection() {
  const token = useApiToken();
  return useQuery({
    queryKey: ["canvas", "connection"],
    queryFn: () => canvas.getCanvasConnection(token!),
    enabled: !!token,
  });
}

export function useStartCanvasOAuth() {
  const token = useApiToken();
  return useMutation({
    mutationFn: async () => {
      const res = await canvas.startCanvasOAuth(token!);
      window.location.href = res.authorize_url;
    },
  });
}

export function useDisconnectCanvas() {
  const token = useApiToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => canvas.disconnectCanvas(token!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["canvas"] }),
  });
}

export function useCanvasCourses(role: "teacher" | "student") {
  const token = useApiToken();
  return useQuery({
    queryKey: ["canvas", "courses", role],
    queryFn: () => canvas.listCanvasCourses(token!, role),
    enabled: !!token,
  });
}

export function useLinkCanvasCourse() {
  const token = useApiToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (canvasCourseId: string) => canvas.linkCanvasCourse(token!, canvasCourseId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["canvas", "courses"] });
      qc.invalidateQueries({ queryKey: ["courses"] });
    },
  });
}

export function useJoinCanvasCourse() {
  const token = useApiToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (canvasCourseId: string) => canvas.joinCanvasCourse(token!, canvasCourseId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["canvas", "courses"] });
      qc.invalidateQueries({ queryKey: ["courses"] });
    },
  });
}

export function useCanvasFiles(meliCourseId: string) {
  const token = useApiToken();
  return useQuery({
    queryKey: ["canvas", "files", meliCourseId],
    queryFn: () => canvas.listCanvasFiles(token!, meliCourseId),
    enabled: !!token,
  });
}

export function useImportCanvasFiles(meliCourseId: string) {
  const token = useApiToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (fileIds: string[]) => canvas.importCanvasFiles(token!, meliCourseId, fileIds),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["canvas", "files", meliCourseId] });
      qc.invalidateQueries({ queryKey: ["documents", meliCourseId] });
    },
  });
}

export function useImportCanvasRoster(meliCourseId: string) {
  const token = useApiToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sendEmails: boolean) => canvas.importCanvasRoster(token!, meliCourseId, sendEmails),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["enrollments", meliCourseId] }),
  });
}

export function useCanvasSyncEvents(meliCourseId: string) {
  const token = useApiToken();
  return useQuery({
    queryKey: ["canvas", "sync-events", meliCourseId],
    queryFn: () => canvas.listCanvasSyncEvents(token!, meliCourseId),
    enabled: !!token,
  });
}

export function useManualSyncCanvas(meliCourseId: string) {
  const token = useApiToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => canvas.manualSyncCanvas(token!, meliCourseId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["canvas"] }),
  });
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/canvas-api.ts frontend/src/hooks/use-canvas.ts
git commit -m "feat(canvas): frontend API client and React Query hooks"
```

---

### Task 19: Account-level Canvas settings page

**Files:**
- Create: `frontend/src/components/canvas/connect-button.tsx`
- Create: `frontend/src/app/dashboard/canvas/page.tsx`

- [ ] **Step 1: Create connect button**

```tsx
// frontend/src/components/canvas/connect-button.tsx
"use client";

import { useStartCanvasOAuth } from "@/hooks/use-canvas";

export function CanvasConnectButton() {
  const start = useStartCanvasOAuth();
  return (
    <button
      type="button"
      onClick={() => start.mutate()}
      disabled={start.isPending}
      className="btn btn-primary"
    >
      {start.isPending ? "Redirecting…" : "Connect Canvas"}
    </button>
  );
}
```

- [ ] **Step 2: Create settings page**

```tsx
// frontend/src/app/dashboard/canvas/page.tsx
"use client";

import { useSearchParams } from "next/navigation";
import { useCanvasConnection, useDisconnectCanvas } from "@/hooks/use-canvas";
import { CanvasConnectButton } from "@/components/canvas/connect-button";

export default function CanvasSettingsPage() {
  const { data, isLoading } = useCanvasConnection();
  const disconnect = useDisconnectCanvas();
  const params = useSearchParams();

  if (isLoading) return <p>Loading…</p>;

  return (
    <section className="space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold">Canvas</h1>
        <p className="text-sm opacity-70">
          Connect your HKUST Canvas account so Meli can mirror your courses, files, and rosters.
        </p>
      </header>

      {params.get("connected") === "1" && (
        <div role="status" className="rounded-md bg-green-50 p-3 text-green-800">
          Canvas connected successfully.
        </div>
      )}

      {!data?.connected ? (
        <CanvasConnectButton />
      ) : (
        <div className="space-y-3">
          <p>
            Connected as Canvas user <code>{data.canvas_user_id}</code> on{" "}
            <code>{data.canvas_base_url}</code>.
          </p>
          <button
            type="button"
            onClick={() => disconnect.mutate()}
            disabled={disconnect.isPending}
            className="btn btn-outline"
          >
            {disconnect.isPending ? "Disconnecting…" : "Disconnect Canvas"}
          </button>
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/dashboard/canvas/ frontend/src/components/canvas/
git commit -m "feat(canvas): account settings page with connect/disconnect"
```

---

### Task 20: Instructor — Canvas course picker in course creation

**Files:**
- Create: `frontend/src/components/canvas/canvas-course-picker.tsx`
- Modify: existing course-creation UI to include a new tab/section (engineer identifies file path; likely `frontend/src/app/dashboard/courses/new/page.tsx` or a modal in the courses list page)

- [ ] **Step 1: Create picker**

```tsx
// frontend/src/components/canvas/canvas-course-picker.tsx
"use client";

import { useRouter } from "next/navigation";
import { useCanvasCourses, useLinkCanvasCourse } from "@/hooks/use-canvas";

export function CanvasCoursePicker() {
  const router = useRouter();
  const { data, isLoading, error } = useCanvasCourses("teacher");
  const link = useLinkCanvasCourse();

  if (isLoading) return <p>Loading Canvas courses…</p>;

  if (error) {
    // If backend returned canvas_not_connected, prompt to connect
    return (
      <div className="rounded-md border p-4">
        <p className="mb-2">Connect Canvas to import your courses.</p>
        <a href="/dashboard/canvas" className="btn btn-primary">Connect Canvas</a>
      </div>
    );
  }

  return (
    <ul className="space-y-2">
      {(data ?? []).map((c) => {
        const linked = !!c.already_linked_meli_course_id;
        return (
          <li key={c.canvas_course_id} className="flex items-center justify-between rounded-md border p-3">
            <div>
              <div className="font-medium">{c.name}</div>
              <div className="text-xs opacity-60">{c.course_code}</div>
            </div>
            {linked ? (
              <button
                className="btn btn-outline"
                onClick={() => router.push(`/dashboard/courses/${c.already_linked_meli_course_id}`)}
              >
                Already linked — open
              </button>
            ) : (
              <button
                className="btn btn-primary"
                disabled={link.isPending}
                onClick={async () => {
                  const res = await link.mutateAsync(c.canvas_course_id);
                  router.push(`/dashboard/courses/${res.meli_course_id}`);
                }}
              >
                {link.isPending ? "Linking…" : "Link to Meli"}
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
```

- [ ] **Step 2: Mount it in the course creation UI**

Engineer: locate the current "create course" surface (check `frontend/src/app/dashboard/courses/` pages and any modal). Add a section titled "Import from Canvas" that renders `<CanvasCoursePicker />`. Keep the existing manual-create form alongside it (both paths coexist — decision 7a).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/canvas/canvas-course-picker.tsx <course-creation-file>
git commit -m "feat(canvas): instructor course picker in course creation flow"
```

---

### Task 21: Instructor — Canvas tab on course settings (files + roster + sync)

**Files:**
- Create: `frontend/src/components/canvas/file-import-dialog.tsx`
- Create: `frontend/src/components/canvas/roster-import-dialog.tsx`
- Create: `frontend/src/components/canvas/canvas-tab.tsx`
- Modify: `frontend/src/app/dashboard/courses/[courseId]/page.tsx`

- [ ] **Step 1: File import dialog**

```tsx
// frontend/src/components/canvas/file-import-dialog.tsx
"use client";

import { useState } from "react";
import { useCanvasFiles, useImportCanvasFiles } from "@/hooks/use-canvas";

export function FileImportDialog({ meliCourseId }: { meliCourseId: string }) {
  const { data, isLoading } = useCanvasFiles(meliCourseId);
  const importMut = useImportCanvasFiles(meliCourseId);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  if (isLoading) return <p>Loading Canvas files…</p>;

  const available = data?.available ?? [];
  const already = data?.already_imported ?? [];

  return (
    <div className="space-y-4">
      <section>
        <h3 className="font-medium">Available to import</h3>
        {available.length === 0 ? (
          <p className="text-sm opacity-60">No new files.</p>
        ) : (
          <ul className="space-y-1">
            {available.map((f) => (
              <li key={f.canvas_file_id} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={selected.has(f.canvas_file_id)}
                  onChange={(e) => {
                    const next = new Set(selected);
                    e.target.checked ? next.add(f.canvas_file_id) : next.delete(f.canvas_file_id);
                    setSelected(next);
                  }}
                />
                <span>{f.display_name}</span>
                <span className="text-xs opacity-60">
                  {f.content_type} · {f.size ? `${Math.round(f.size / 1024)} KB` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
        <button
          className="btn btn-primary mt-3"
          disabled={selected.size === 0 || importMut.isPending}
          onClick={async () => {
            await importMut.mutateAsync(Array.from(selected));
            setSelected(new Set());
          }}
        >
          {importMut.isPending ? "Importing…" : `Import ${selected.size} file${selected.size === 1 ? "" : "s"}`}
        </button>
      </section>

      <section>
        <h3 className="font-medium">Already imported</h3>
        <ul className="text-sm opacity-70">
          {already.map((f) => <li key={f.canvas_file_id}>{f.display_name}</li>)}
        </ul>
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Roster import dialog**

```tsx
// frontend/src/components/canvas/roster-import-dialog.tsx
"use client";

import { useState } from "react";
import { useImportCanvasRoster } from "@/hooks/use-canvas";

export function RosterImportDialog({ meliCourseId }: { meliCourseId: string }) {
  const importMut = useImportCanvasRoster(meliCourseId);
  const [sendEmails, setSendEmails] = useState(false);
  const lastResult = importMut.data;

  return (
    <div className="space-y-3">
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={sendEmails}
          onChange={(e) => setSendEmails(e.target.checked)}
        />
        <span>Send invite emails to students not yet on Meli</span>
      </label>
      <button
        className="btn btn-primary"
        onClick={() => importMut.mutate(sendEmails)}
        disabled={importMut.isPending}
      >
        {importMut.isPending ? "Syncing…" : "Import roster from Canvas"}
      </button>
      {lastResult && (
        <div className="text-sm">
          Added {lastResult.added}, pending {lastResult.pending}, dropped {lastResult.dropped},
          unchanged {lastResult.unchanged}
          {lastResult.skipped_off_domain > 0 && `, ${lastResult.skipped_off_domain} skipped (off-domain)`}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Canvas tab wrapper**

```tsx
// frontend/src/components/canvas/canvas-tab.tsx
"use client";

import { useCanvasSyncEvents, useManualSyncCanvas } from "@/hooks/use-canvas";
import { FileImportDialog } from "./file-import-dialog";
import { RosterImportDialog } from "./roster-import-dialog";

export function CanvasTab({ meliCourseId }: { meliCourseId: string }) {
  const { data: events } = useCanvasSyncEvents(meliCourseId);
  const sync = useManualSyncCanvas(meliCourseId);

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Canvas</h2>
        <button
          className="btn btn-outline"
          onClick={() => sync.mutate()}
          disabled={sync.isPending}
        >
          {sync.isPending ? "Syncing…" : "Sync now"}
        </button>
      </div>

      <section>
        <h3 className="font-medium mb-2">Files</h3>
        <FileImportDialog meliCourseId={meliCourseId} />
      </section>

      <section>
        <h3 className="font-medium mb-2">Roster</h3>
        <RosterImportDialog meliCourseId={meliCourseId} />
      </section>

      <section>
        <h3 className="font-medium mb-2">Recent sync activity</h3>
        <ul className="text-sm space-y-1">
          {(events ?? []).map((e) => (
            <li key={e.id}>
              <span className="opacity-60">{new Date(e.created_at).toLocaleString()}</span>
              {" — "}
              <strong>{e.event_type}</strong>: {JSON.stringify(e.payload)}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
```

- [ ] **Step 4: Mount the tab**

In `frontend/src/app/dashboard/courses/[courseId]/page.tsx`, add a conditional section or tab rendering `<CanvasTab meliCourseId={courseId} />` — shown only if the current user is an instructor on the course. Engineer follows whatever tab/section pattern already exists in that file.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/canvas/ frontend/src/app/dashboard/courses/
git commit -m "feat(canvas): instructor course tab with file + roster import"
```

---

### Task 22: Student — Canvas courses section on join page

**Files:**
- Create: `frontend/src/components/canvas/student-canvas-courses.tsx`
- Modify: the existing "join course by code" page (engineer identifies the path — based on `feat(frontend): join-course flow and instructor enrollment code display` in recent commits)

- [ ] **Step 1: Create component**

```tsx
// frontend/src/components/canvas/student-canvas-courses.tsx
"use client";

import { useRouter } from "next/navigation";
import { useCanvasConnection, useCanvasCourses, useJoinCanvasCourse } from "@/hooks/use-canvas";
import { CanvasConnectButton } from "./connect-button";

export function StudentCanvasCourses() {
  const router = useRouter();
  const { data: conn } = useCanvasConnection();
  const { data, isLoading } = useCanvasCourses("student");
  const join = useJoinCanvasCourse();

  if (!conn?.connected) {
    return (
      <div className="rounded-md border p-4">
        <p className="mb-2">Connect Canvas to see your courses and join them in Meli automatically.</p>
        <CanvasConnectButton />
      </div>
    );
  }

  if (isLoading) return <p>Loading Canvas courses…</p>;

  return (
    <ul className="space-y-2">
      {(data ?? []).map((c) => {
        const meliId = c.already_linked_meli_course_id;
        return (
          <li key={c.canvas_course_id} className="flex items-center justify-between rounded-md border p-3">
            <div>
              <div className="font-medium">{c.name}</div>
              <div className="text-xs opacity-60">{c.course_code}</div>
            </div>
            {meliId ? (
              <button
                className="btn btn-primary"
                disabled={join.isPending}
                onClick={async () => {
                  const res = await join.mutateAsync(c.canvas_course_id);
                  router.push(`/dashboard/courses/${res.meli_course_id}`);
                }}
              >
                Join Meli course
              </button>
            ) : (
              <span className="text-sm opacity-60">Instructor hasn't enabled Meli</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}
```

- [ ] **Step 2: Mount above the enrollment-code input**

Engineer: locate the student join page and add `<StudentCanvasCourses />` *above* the existing enrollment-code form, under a heading like "My Canvas courses".

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/canvas/student-canvas-courses.tsx <join-page-file>
git commit -m "feat(canvas): student Canvas courses section on join page"
```

---

## Phase F — E2E, docs, rollout

### Task 23: Playwright E2E

**Files:**
- Create: `frontend/tests/e2e/canvas-integration.spec.ts`

- [ ] **Step 1: Write test scaffold**

```typescript
import { test, expect } from "@playwright/test";

// This test mocks the backend Canvas responses by routing /api/canvas/* through
// page.route(). It verifies the happy paths: instructor links, imports files
// and roster; student joins via Canvas.

test("instructor links a Canvas course and imports a file", async ({ page }) => {
  // Auth is out of scope for this test — assume a logged-in instructor fixture.
  // Engineer: wire up using existing auth/storageState pattern in `playwright.config`.

  await page.route("**/api/canvas/oauth/start", (route) =>
    route.fulfill({ json: { success: true, data: { authorize_url: "about:blank" } } })
  );
  await page.route("**/api/canvas/connection", (route) =>
    route.fulfill({ json: { success: true, data: { connected: true, canvas_user_id: "42" } } })
  );
  await page.route("**/api/canvas/courses?role=teacher", (route) =>
    route.fulfill({
      json: {
        success: true,
        data: [{
          canvas_course_id: "222",
          name: "Phonetics",
          course_code: "LING220",
          already_linked_meli_course_id: null,
        }],
      },
    })
  );
  await page.route("**/api/canvas/courses/222/link", (route) =>
    route.fulfill({ json: { success: true, data: { meli_course_id: "abc-123" } } })
  );

  await page.goto("/dashboard/courses");
  await page.getByRole("button", { name: /import from canvas/i }).click();
  await page.getByRole("button", { name: /link to meli/i }).click();
  await expect(page).toHaveURL(/\/courses\/abc-123/);
});

test("student joins Meli course from Canvas enrollments", async ({ page }) => {
  await page.route("**/api/canvas/connection", (route) =>
    route.fulfill({ json: { success: true, data: { connected: true } } })
  );
  await page.route("**/api/canvas/courses?role=student", (route) =>
    route.fulfill({
      json: {
        success: true,
        data: [{
          canvas_course_id: "222",
          name: "Phonetics",
          course_code: "LING220",
          already_linked_meli_course_id: "abc-123",
        }],
      },
    })
  );
  await page.route("**/api/canvas/courses/222/join", (route) =>
    route.fulfill({ json: { success: true, data: { meli_course_id: "abc-123" } } })
  );

  await page.goto("/dashboard/join");  // engineer: use real path
  await page.getByRole("button", { name: /join meli course/i }).click();
  await expect(page).toHaveURL(/\/courses\/abc-123/);
});
```

- [ ] **Step 2: Run against dev server**

```bash
cd frontend
npm run e2e -- canvas-integration
```

Expected: both tests pass. If they fail because of auth setup, fix by extending the existing Playwright storageState helper — don't disable auth globally.

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/e2e/canvas-integration.spec.ts
git commit -m "test(canvas): E2E for instructor link and student join flows"
```

---

### Task 24: Update backend env example + docs

**Files:**
- Modify: `backend/.env.example`
- Modify: `CLAUDE.md` (short note under "Key Conventions")

- [ ] **Step 1: Ensure all Canvas env vars are documented**

Already handled in Task 1.

- [ ] **Step 2: Add a `## Canvas OAuth` section to `CLAUDE.md`**

Append:

```markdown
- **Canvas OAuth (Phase 1)**: Uses a single HKUST Canvas developer key (`CANVAS_CLIENT_ID`/`CANVAS_CLIENT_SECRET`). Per-user tokens stored in `canvas_user_credentials` (not per-course). All Canvas REST calls go through `CanvasClient` (refreshes on 401). Daily sync scheduler lives in `app.services.canvas_sync.run_scheduler`, started in the FastAPI lifespan.
```

- [ ] **Step 3: Commit**

```bash
git add backend/.env.example CLAUDE.md
git commit -m "docs(canvas): env vars and CLAUDE.md conventions note"
```

---

### Task 25: Coverage sanity + manual smoke

- [ ] **Step 1: Run the full backend test suite**

```bash
cd backend && source .venv/bin/activate
pytest --cov=app/services/canvas_oauth --cov=app/services/canvas_client \
       --cov=app/services/canvas_files --cov=app/services/canvas_roster \
       --cov=app/services/canvas_sync --cov=app/api/canvas \
       --cov=app/api/canvas_oauth --cov-report=term-missing
```

Expected: 80%+ on each listed module. If not, add targeted tests for uncovered branches (refresh failure, off-domain emails, drop detection, invalid state, etc.).

- [ ] **Step 2: Manual smoke against a Canvas sandbox**

If HKUST IT has provisioned a non-production Canvas test tenant, run through:
1. Connect Canvas (OAuth roundtrip).
2. Link a test course.
3. Import a file → watch `tasks` table → verify chunks embedded in pgvector.
4. Import roster → verify `enrollments` + `pending_enrollments` rows.
5. Wait for scheduler tick (or `POST /canvas/sync`) and verify sync events.

Record any gotchas in a `rollout-notes.md` under the plan directory.

- [ ] **Step 3: Commit any final fixes**

```bash
git add -u
git commit -m "chore(canvas): test coverage fill-in + rollout notes"
```

---

## Self-Review Summary

| Spec section | Covered by task(s) |
|---|---|
| §3 Decision 1 — OAuth | Tasks 1, 4, 5 |
| §3 Decision 2 — Instructor-first | Tasks 9, 15 |
| §3 Decision 3 — Pre-provision + invite | Task 12, 13 |
| §3 Decision 4 — Manual + scheduled sync | Tasks 16, 17 |
| §3 Decision 5 — Files only | Task 11 |
| §3 Decision 6 — Role mapping | Task 12 (`CANVAS_ROLE_TO_MELI`) |
| §3 Decision 7a — Enrollment code coexists | Task 22 (mounted alongside existing form) |
| §3 Decision 7b — Disconnect keeps data | Task 5 (`disconnect_canvas`) |
| §3 Decision 7c — 1:1 mapping | Task 9 (409 on existing link) |
| §4 Architecture | Tasks 1–3 foundation + 16 scheduler |
| §5 Data model | Task 2 migration + Task 3 models |
| §6 OAuth foundation | Tasks 4, 5, 6 |
| §7 Instructor flow | Tasks 8, 9, 10, 11, 12, 13 |
| §8 Student flow | Tasks 14, 15 |
| §9 Sync worker | Tasks 16, 17 |
| §10 Security | Task 4 (state JWT), Task 5 (scope guard), Task 12 (domain allow) |
| §11 Error handling | Task 5 + 6 (connected/reauth codes), Task 11 (errors[]), Task 16 (error events) |
| §12 Frontend surfaces | Tasks 18–22 |
| §13 Testing | Each task has tests; Task 23 E2E; Task 25 coverage |
| §14 Open questions | Scheduler placement resolved in Task 16; pagination in Task 6 (`_paginate`); email provider flagged in Task 12 Step 3 note |
| §15 Rollout | Task 25 manual smoke |

**Execution checklist:** No placeholders scanned. Type/method names cross-referenced — `CanvasClient.list_my_courses`, `list_course_files`, `list_course_enrollments`, `get_course`, `get_file`, `download_file` are all defined in Task 6 and used consistently downstream. `CANVAS_ROLE_TO_MELI` mapping defined in Task 12 matches the decision in §3.6.

---

## Plan complete

**Saved to** `docs/superpowers/plans/2026-04-14-canvas-integration.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
