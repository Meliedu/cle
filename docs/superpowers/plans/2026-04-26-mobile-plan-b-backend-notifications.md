# Plan B: Backend Notification System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a full server-side notification system to the FastAPI backend: device registration, in-app notification feed, instructor announcements, and per-user APNs/FCM push delivery for live-quiz invites, course updates, content-ready, and announcement events.

**Architecture:** Three new tables (`notification_devices`, `notifications`, `announcements`) + a `notifier` service that fans out events to APNs/FCM and persists feed entries. Existing trigger sites (`live.py` session start, `worker.py` async generation completion, `documents.py` ingestion) call `notifier.dispatch(...)`. Throttling/batching for course updates runs as a periodic task in the existing worker loop. Daily 8am announcement-digest flush piggybacks on the existing `canvas_sync.py` scheduler pattern.

**Tech Stack:** FastAPI 0.115, SQLAlchemy 2.0 async, Alembic, pytest-asyncio, `aioapns` (APNs), `firebase-admin` (FCM HTTP v1), pydantic v2.

**Spec reference:** `docs/superpowers/specs/2026-04-26-mobile-app-design.md` §7.1, §7.2, §7.3.

**Independent of Plan A.** Can be built in parallel by a backend engineer; the endpoints are immediately exercisable from `curl` and from the existing web frontend (in-app feed loading is built in Plan C).

---

## File Structure

```
backend/
├── alembic/versions/
│   └── 20260427_add_notifications.py        NEW: 3 new tables
├── app/models/
│   ├── notification.py                       NEW: NotificationDevice, Notification, Announcement
│   └── __init__.py                           MOD: register new models
├── app/schemas/
│   ├── notification.py                       NEW: pydantic schemas
│   └── __init__.py                           MOD: re-export
├── app/services/
│   ├── notifier.py                           NEW: dispatch + APNs + FCM clients
│   ├── notification_throttle.py              NEW: course-update batching, send-mode resolution
│   └── worker.py                             MOD: add periodic batch task + announcement-digest task
├── app/api/
│   ├── notifications.py                      NEW: device + feed endpoints
│   ├── announcements.py                      NEW: instructor compose endpoints
│   └── __init__.py                           MOD: include the two new routers
├── app/api/live.py                           MOD: call notifier on session start
├── app/api/documents.py                      MOD: call notifier on document ready
├── app/api/quizzes.py                        MOD: call notifier on async generation completion
├── app/api/flashcards.py                     MOD: same — content-ready notifications
├── app/api/rag.py                            MOD: same for summaries
├── app/config.py                             MOD: APNs/FCM env vars
└── tests/
    ├── test_notifier.py                      NEW
    ├── test_notification_throttle.py         NEW
    ├── test_api_notifications.py             NEW
    ├── test_api_announcements.py             NEW
    └── test_notification_integration.py      NEW
```

---

## Task B1: Models — `notification_devices`, `notifications`, `announcements`

**Files:**
- Create: `backend/app/models/notification.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Write `backend/app/models/notification.py`**

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DevicePlatform(str, enum.Enum):
    ios = "ios"
    android = "android"


class NotificationType(str, enum.Enum):
    live_quiz_invite = "live_quiz_invite"
    announcement = "announcement"
    course_update = "course_update"
    content_ready = "content_ready"


class AnnouncementSendMode(str, enum.Enum):
    now = "now"
    digest = "digest"


class NotificationDevice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notification_devices"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[DevicePlatform] = mapped_column(
        SQLEnum(DevicePlatform, name="device_platform"), nullable=False
    )
    push_token: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    app_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_notification_devices_user", "user_id"),
    )


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[NotificationType] = mapped_column(
        SQLEnum(NotificationType, name="notification_type"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    deep_link: Mapped[str] = mapped_column(String(500), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index("ix_notifications_user_unread", "user_id", "read_at"),
    )


class Announcement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "announcements"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    send_mode: Mapped[AnnouncementSendMode] = mapped_column(
        SQLEnum(AnnouncementSendMode, name="announcement_send_mode"),
        nullable=False,
        default=AnnouncementSendMode.now,
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retracted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_announcements_course_created", "course_id", "created_at"),
    )
```

- [ ] **Step 2: Re-export from `app/models/__init__.py`**

Add to `backend/app/models/__init__.py`:

```python
from app.models.notification import (  # noqa: F401
    Announcement,
    AnnouncementSendMode,
    DevicePlatform,
    Notification,
    NotificationDevice,
    NotificationType,
)
```

- [ ] **Step 3: Confirm imports compile**

```bash
cd backend
source .venv/bin/activate
python -c "from app.models import Notification, NotificationDevice, Announcement; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/notification.py backend/app/models/__init__.py
git commit -m "feat(backend): notification + announcement SQLAlchemy models"
```

---

## Task B2: Alembic migration

**Files:**
- Create: `backend/alembic/versions/20260427_add_notifications.py`

- [ ] **Step 1: Generate migration scaffold**

```bash
cd backend
source .venv/bin/activate
alembic revision --autogenerate -m "add notifications + announcements + devices"
```

Note the generated filename. Open it and **replace its contents** with the explicit migration below (autogenerate output is a starting point but we want full control of indexes and enum names).

- [ ] **Step 2: Write the migration body**

```python
"""add notifications + announcements + devices

Revision ID: <set by alembic>
Revises: <previous head>
Create Date: 2026-04-27 ...

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "<filled in>"
down_revision: Union[str, None] = "<previous head>"
branch_labels = None
depends_on = None


device_platform = postgresql.ENUM(
    "ios", "android", name="device_platform"
)
notification_type = postgresql.ENUM(
    "live_quiz_invite", "announcement", "course_update", "content_ready",
    name="notification_type",
)
announcement_send_mode = postgresql.ENUM(
    "now", "digest", name="announcement_send_mode"
)


def upgrade() -> None:
    bind = op.get_bind()
    device_platform.create(bind, checkfirst=True)
    notification_type.create(bind, checkfirst=True)
    announcement_send_mode.create(bind, checkfirst=True)

    op.create_table(
        "notification_devices",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "platform",
            postgresql.ENUM("ios", "android", name="device_platform", create_type=False),
            nullable=False,
        ),
        sa.Column("push_token", sa.Text(), nullable=False),
        sa.Column("app_version", sa.String(length=32), nullable=True),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("push_token"),
    )
    op.create_index(
        "ix_notification_devices_user", "notification_devices", ["user_id"]
    )

    op.create_table(
        "notifications",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "type",
            postgresql.ENUM(
                "live_quiz_invite", "announcement", "course_update", "content_ready",
                name="notification_type", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("deep_link", sa.String(length=500), nullable=False),
        sa.Column(
            "data", postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notifications_user_created", "notifications", ["user_id", "created_at"]
    )
    op.create_index(
        "ix_notifications_user_unread", "notifications", ["user_id", "read_at"]
    )

    op.create_table(
        "announcements",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), nullable=False,
        ),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "send_mode",
            postgresql.ENUM(
                "now", "digest", name="announcement_send_mode", create_type=False
            ),
            nullable=False, server_default=sa.text("'now'"),
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_announcements_course_created", "announcements", ["course_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_announcements_course_created", table_name="announcements")
    op.drop_table("announcements")
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_notification_devices_user", table_name="notification_devices")
    op.drop_table("notification_devices")
    bind = op.get_bind()
    sa.Enum(name="announcement_send_mode").drop(bind, checkfirst=True)
    sa.Enum(name="notification_type").drop(bind, checkfirst=True)
    sa.Enum(name="device_platform").drop(bind, checkfirst=True)
```

- [ ] **Step 3: Apply on dev DB and verify**

```bash
alembic upgrade head
psql "postgresql://postgres:postgres@localhost:5432/langassistant" -c "\dt notification*; \dt announcements"
```

Expected output lists `notification_devices`, `notifications`, `announcements`.

- [ ] **Step 4: Test the downgrade and re-upgrade roundtrip**

```bash
alembic downgrade -1
alembic upgrade head
```

Expected: no errors.

- [ ] **Step 5: Apply on test DB**

```bash
PGDATABASE=langassistant_test alembic upgrade head
```

(If using the same connection string but different DB, set the env var or temporarily edit alembic.ini.)

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat(backend): migration for notifications + announcements + devices"
```

---

## Task B3: Pydantic schemas

**Files:**
- Create: `backend/app/schemas/notification.py`
- Modify: `backend/app/schemas/__init__.py`

- [ ] **Step 1: Write `backend/app/schemas/notification.py`**

```python
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.notification import (
    AnnouncementSendMode,
    DevicePlatform,
    NotificationType,
)


class DeviceRegister(BaseModel):
    push_token: Annotated[str, Field(min_length=1, max_length=2048)]
    platform: DevicePlatform
    app_version: str | None = Field(default=None, max_length=32)


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    platform: DevicePlatform
    app_version: str | None
    last_seen_at: datetime


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    type: NotificationType
    title: str
    body: str
    deep_link: str
    data: dict[str, Any]
    read_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime


class NotificationFeedCursor(BaseModel):
    """Opaque cursor — base64 of created_at timestamp + id tiebreaker."""
    cursor: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


class UnreadCountResponse(BaseModel):
    unread: int


class AnnouncementCreate(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=200)]
    body: Annotated[str, Field(min_length=1, max_length=10000)]
    send_mode: AnnouncementSendMode = AnnouncementSendMode.now


class AnnouncementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    course_id: uuid.UUID
    author_id: uuid.UUID
    title: str
    body: str
    send_mode: AnnouncementSendMode
    scheduled_at: datetime | None
    sent_at: datetime | None
    retracted_at: datetime | None
    created_at: datetime
```

- [ ] **Step 2: Re-export**

Add to `backend/app/schemas/__init__.py` (or wherever the project re-exports — check the existing pattern):

```python
from app.schemas.notification import (  # noqa: F401
    AnnouncementCreate,
    AnnouncementResponse,
    DeviceRegister,
    DeviceResponse,
    NotificationFeedCursor,
    NotificationResponse,
    UnreadCountResponse,
)
```

- [ ] **Step 3: Verify imports**

```bash
cd backend && source .venv/bin/activate
python -c "from app.schemas import NotificationResponse, AnnouncementCreate; print('ok')"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/notification.py backend/app/schemas/__init__.py
git commit -m "feat(backend): pydantic schemas for notifications + announcements"
```

---

## Task B4: APNs and FCM clients (with config)

**Files:**
- Modify: `backend/app/config.py`
- Create: `backend/app/services/push/__init__.py`
- Create: `backend/app/services/push/apns.py`
- Create: `backend/app/services/push/fcm.py`
- Create: `backend/app/services/push/types.py`
- Modify: `backend/pyproject.toml` or `requirements.txt` (whichever the project uses)

- [ ] **Step 0: Identify dependency manager**

```bash
ls backend/pyproject.toml backend/requirements*.txt 2>&1 | head
```

Use the file that exists. Snippets below assume `pyproject.toml` with `[project.dependencies]`. Adapt if it's a flat `requirements.txt`.

- [ ] **Step 1: Add APNs + FCM dependencies**

In `backend/pyproject.toml` under `[project.dependencies]` (or in `requirements.txt`):

```toml
"aioapns>=3.2,<4",
"firebase-admin>=6.5,<7",
```

- [ ] **Step 2: Install**

```bash
cd backend
source .venv/bin/activate
pip install -e .  # or pip install -r requirements.txt
```

- [ ] **Step 3: Add config keys to `backend/app/config.py`**

In the `Settings` class, add:

```python
# APNs (iOS push)
apns_key_id: str | None = None
apns_team_id: str | None = None
apns_auth_key_path: str | None = None  # path to .p8 file
apns_topic: str = "hk.ust.meli"
apns_use_sandbox: bool = True  # true for TestFlight, false for App Store

# FCM (Android push)
fcm_service_account_json: str | None = None  # full JSON contents OR path

# Push behavior
push_send_enabled: bool = True  # set to False in dev/staging to skip real send
```

- [ ] **Step 4: Add to `.env.example`**

Append to `backend/.env.example`:

```bash
# APNs
APNS_KEY_ID=
APNS_TEAM_ID=
APNS_AUTH_KEY_PATH=secrets/apns_key.p8
APNS_TOPIC=hk.ust.meli
APNS_USE_SANDBOX=true

# FCM (Firebase Cloud Messaging)
FCM_SERVICE_ACCOUNT_JSON=

# Push toggle (false = log only, no real send — useful in dev)
PUSH_SEND_ENABLED=true
```

- [ ] **Step 5: Write `backend/app/services/push/types.py`**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class PushPayload:
    title: str
    body: str
    deep_link: str
    data: dict[str, str]


class PushTokenInvalid(Exception):
    """Raised when APNs/FCM responds with 'unregistered' / 'not found'."""


class PushSendError(Exception):
    """Transient send error — retryable."""
```

- [ ] **Step 6: Write `backend/app/services/push/apns.py`**

```python
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from aioapns import APNs, NotificationRequest, PushType
from aioapns.exceptions import (
    APNsConnectionError,
    APNsResponseException,
)

from app.config import settings
from app.services.push.types import PushPayload, PushSendError, PushTokenInvalid

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

_client: APNs | None = None


def _get_client() -> APNs:
    global _client
    if _client is not None:
        return _client
    if not all([settings.apns_key_id, settings.apns_team_id, settings.apns_auth_key_path]):
        raise RuntimeError("APNs not configured — see APNS_* env vars")
    _client = APNs(
        key=str(Path(settings.apns_auth_key_path).read_text()),
        key_id=settings.apns_key_id,
        team_id=settings.apns_team_id,
        topic=settings.apns_topic,
        use_sandbox=settings.apns_use_sandbox,
    )
    return _client


async def send(token: str, payload: PushPayload) -> None:
    if not settings.push_send_enabled:
        log.info("push_send_enabled=False — skipping APNs send to %s", token[:12])
        return
    request = NotificationRequest(
        device_token=token,
        message={
            "aps": {
                "alert": {"title": payload.title, "body": payload.body},
                "sound": "default",
                "badge": 1,
            },
            "deep_link": payload.deep_link,
            **payload.data,
        },
        push_type=PushType.ALERT,
    )
    try:
        result = await _get_client().send_notification(request)
    except APNsConnectionError as e:
        raise PushSendError(f"APNs connection error: {e}") from e
    except APNsResponseException as e:
        # 410 Gone or 400 BadDeviceToken → invalid token
        if e.status in (400, 410):
            raise PushTokenInvalid(f"APNs invalidated token: {e}") from e
        raise PushSendError(f"APNs error: {e}") from e
    if not result.is_successful:
        if result.status == "410" or result.description == "Unregistered":
            raise PushTokenInvalid(result.description)
        raise PushSendError(result.description)
```

- [ ] **Step 7: Write `backend/app/services/push/fcm.py`**

```python
from __future__ import annotations

import json
import logging
import os
import threading

import firebase_admin
from firebase_admin import credentials, messaging

from app.config import settings
from app.services.push.types import PushPayload, PushSendError, PushTokenInvalid

log = logging.getLogger(__name__)

_init_lock = threading.Lock()
_initialized = False


def _ensure_initialized() -> None:
    global _initialized
    with _init_lock:
        if _initialized:
            return
        if not settings.fcm_service_account_json:
            raise RuntimeError("FCM not configured — set FCM_SERVICE_ACCOUNT_JSON")
        raw = settings.fcm_service_account_json
        # Allow either inline JSON or a path
        if os.path.exists(raw):
            cred = credentials.Certificate(raw)
        else:
            cred = credentials.Certificate(json.loads(raw))
        firebase_admin.initialize_app(cred, name="meli-fcm")
        _initialized = True


def _app() -> firebase_admin.App:
    _ensure_initialized()
    return firebase_admin.get_app("meli-fcm")


async def send(token: str, payload: PushPayload) -> None:
    if not settings.push_send_enabled:
        log.info("push_send_enabled=False — skipping FCM send to %s", token[:12])
        return
    msg = messaging.Message(
        token=token,
        notification=messaging.Notification(title=payload.title, body=payload.body),
        data={"deep_link": payload.deep_link, **payload.data},
        android=messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(sound="default", default_sound=True),
        ),
    )
    try:
        # firebase-admin is sync; run in threadpool. Keeping it inline is acceptable
        # because the call is short and the worker pool absorbs concurrency.
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: messaging.send(msg, app=_app()))
    except messaging.UnregisteredError as e:
        raise PushTokenInvalid(str(e)) from e
    except messaging.SenderIdMismatchError as e:
        raise PushTokenInvalid(str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise PushSendError(f"FCM send failed: {e}") from e
```

- [ ] **Step 8: Write `backend/app/services/push/__init__.py`**

```python
from app.models.notification import DevicePlatform
from app.services.push import apns, fcm
from app.services.push.types import PushPayload, PushSendError, PushTokenInvalid


async def send(token: str, platform: DevicePlatform, payload: PushPayload) -> None:
    """Dispatch a single push to the right transport based on platform."""
    if platform == DevicePlatform.ios:
        await apns.send(token, payload)
    elif platform == DevicePlatform.android:
        await fcm.send(token, payload)
    else:
        raise ValueError(f"Unknown platform: {platform}")


__all__ = ["send", "PushPayload", "PushSendError", "PushTokenInvalid"]
```

- [ ] **Step 9: Write a test that mocks both transports**

`backend/tests/test_push_dispatch.py`:

```python
from unittest.mock import AsyncMock, patch

import pytest

from app.models.notification import DevicePlatform
from app.services.push import PushPayload, send


@pytest.mark.asyncio
async def test_send_ios_calls_apns():
    payload = PushPayload(title="t", body="b", deep_link="/x", data={})
    with patch("app.services.push.apns.send", new=AsyncMock()) as m:
        await send("device-token", DevicePlatform.ios, payload)
    m.assert_awaited_once_with("device-token", payload)


@pytest.mark.asyncio
async def test_send_android_calls_fcm():
    payload = PushPayload(title="t", body="b", deep_link="/x", data={})
    with patch("app.services.push.fcm.send", new=AsyncMock()) as m:
        await send("device-token", DevicePlatform.android, payload)
    m.assert_awaited_once_with("device-token", payload)
```

- [ ] **Step 10: Run the test**

```bash
cd backend && source .venv/bin/activate
pytest tests/test_push_dispatch.py -v
```

Expected: 2/2 PASS.

- [ ] **Step 11: Commit**

```bash
git add backend/app/config.py backend/app/services/push/ backend/.env.example backend/pyproject.toml backend/tests/test_push_dispatch.py
git commit -m "feat(backend): APNs + FCM push transport clients"
```

---

## Task B5: `notifier` service (the dispatch core)

**Files:**
- Create: `backend/app/services/notifier.py`
- Create: `backend/tests/test_notifier.py`

- [ ] **Step 1: Write the failing tests** (TDD — define behavior first)

`backend/tests/test_notifier.py`:

```python
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.notification import (
    DevicePlatform,
    Notification,
    NotificationDevice,
    NotificationType,
)
from app.models.user import User
from app.services.notifier import dispatch
from app.services.push import PushTokenInvalid


@pytest_asyncio.fixture
async def user(db_session):
    u = User(id=uuid.uuid4(), email="x@ust.hk", name="X", role="student")
    db_session.add(u)
    await db_session.flush()
    return u


@pytest.mark.asyncio
async def test_dispatch_inserts_notification_row(db_session, user):
    with patch("app.services.notifier.push_send", new=AsyncMock()):
        await dispatch(
            db_session, user.id,
            type_=NotificationType.live_quiz_invite,
            title="Live now",
            body="Join CS101 quiz",
            deep_link="/dashboard/courses/x/live/y",
            data={"course_id": "x", "session_id": "y"},
        )
    rows = (await db_session.execute(select(Notification).where(Notification.user_id == user.id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].title == "Live now"
    assert rows[0].deep_link == "/dashboard/courses/x/live/y"


@pytest.mark.asyncio
async def test_dispatch_sends_to_each_device(db_session, user):
    db_session.add_all([
        NotificationDevice(user_id=user.id, platform=DevicePlatform.ios, push_token="ios-token-aaaa"),
        NotificationDevice(user_id=user.id, platform=DevicePlatform.android, push_token="and-token-bbbb"),
    ])
    await db_session.flush()

    with patch("app.services.notifier.push_send", new=AsyncMock()) as m:
        await dispatch(
            db_session, user.id,
            type_=NotificationType.content_ready,
            title="Quiz ready", body="Try it", deep_link="/x", data={},
        )
    assert m.await_count == 2


@pytest.mark.asyncio
async def test_dispatch_deletes_device_on_invalid_token(db_session, user):
    bad = NotificationDevice(user_id=user.id, platform=DevicePlatform.ios, push_token="bad-token-cccc")
    db_session.add(bad)
    await db_session.flush()

    with patch("app.services.notifier.push_send", new=AsyncMock(side_effect=PushTokenInvalid("gone"))):
        await dispatch(
            db_session, user.id,
            type_=NotificationType.announcement,
            title="x", body="y", deep_link="/z", data={},
        )

    devices = (await db_session.execute(select(NotificationDevice).where(NotificationDevice.user_id == user.id))).scalars().all()
    assert devices == []


@pytest.mark.asyncio
async def test_dispatch_sets_delivered_at_on_success(db_session, user):
    db_session.add(NotificationDevice(user_id=user.id, platform=DevicePlatform.ios, push_token="ok-token-dddd"))
    await db_session.flush()

    with patch("app.services.notifier.push_send", new=AsyncMock()):
        await dispatch(
            db_session, user.id,
            type_=NotificationType.course_update,
            title="x", body="y", deep_link="/z", data={},
        )
    n = (await db_session.execute(select(Notification).where(Notification.user_id == user.id))).scalar_one()
    assert n.delivered_at is not None
```

- [ ] **Step 2: Run tests; confirm they fail**

```bash
pytest tests/test_notifier.py -v
```

Expected: FAIL — `app.services.notifier` doesn't exist yet.

- [ ] **Step 3: Implement `backend/app/services/notifier.py`**

```python
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import (
    Notification,
    NotificationDevice,
    NotificationType,
)
from app.services.push import PushPayload, PushTokenInvalid
from app.services.push import send as push_send

log = logging.getLogger(__name__)


async def dispatch(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    type_: NotificationType,
    title: str,
    body: str,
    deep_link: str,
    data: dict[str, Any],
) -> Notification:
    """Persist a notification and fan it out to all of the user's devices.

    - Always inserts a row in `notifications` (the in-app feed source).
    - Best-effort sends to every registered device.
    - On 410/InvalidToken responses, deletes the offending device row.
    - Sets `delivered_at` if at least one push succeeded; leaves null otherwise.
    """
    notif = Notification(
        user_id=user_id,
        type=type_,
        title=title,
        body=body,
        deep_link=deep_link,
        data=data,
    )
    db.add(notif)
    await db.flush()

    devices = (
        await db.execute(
            select(NotificationDevice).where(NotificationDevice.user_id == user_id)
        )
    ).scalars().all()

    if not devices:
        return notif

    payload = PushPayload(
        title=title, body=body, deep_link=deep_link,
        data={k: str(v) for k, v in data.items()},
    )
    any_ok = False
    invalid_tokens: list[str] = []
    for d in devices:
        try:
            await push_send(d.push_token, d.platform, payload)
            any_ok = True
        except PushTokenInvalid:
            log.info("Push token invalidated; removing device %s", d.id)
            invalid_tokens.append(d.push_token)
        except Exception as e:  # noqa: BLE001 — best-effort
            log.warning("Push send failed for device %s: %s", d.id, e)

    if invalid_tokens:
        await db.execute(
            delete(NotificationDevice).where(
                NotificationDevice.push_token.in_(invalid_tokens)
            )
        )

    if any_ok:
        notif.delivered_at = datetime.now(tz=timezone.utc)
    return notif
```

- [ ] **Step 4: Re-run tests; confirm pass**

```bash
pytest tests/test_notifier.py -v
```

Expected: 4/4 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/notifier.py backend/tests/test_notifier.py
git commit -m "feat(backend): notifier service — fan-out push + persist feed entry"
```

---

## Task B6: Device registration + feed endpoints

**Files:**
- Create: `backend/app/api/notifications.py`
- Modify: `backend/app/api/__init__.py`
- Create: `backend/tests/test_api_notifications.py`

- [ ] **Step 1: Write failing tests**

`backend/tests/test_api_notifications.py`:

```python
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.notification import (
    DevicePlatform,
    Notification,
    NotificationDevice,
    NotificationType,
)


@pytest.mark.asyncio
async def test_register_device_creates_row(authed_client, db_session, current_user):
    r = await authed_client.post(
        "/api/notifications/devices",
        json={"push_token": "tok-aaaa", "platform": "ios", "app_version": "0.1.0"},
    )
    assert r.status_code == 200, r.text
    rows = (await db_session.execute(
        select(NotificationDevice).where(NotificationDevice.user_id == current_user.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].push_token == "tok-aaaa"
    assert rows[0].platform == DevicePlatform.ios


@pytest.mark.asyncio
async def test_register_device_upserts_on_existing_token(authed_client, db_session, current_user):
    db_session.add(NotificationDevice(
        user_id=current_user.id, platform=DevicePlatform.ios, push_token="tok-aaaa",
    ))
    await db_session.flush()
    r = await authed_client.post(
        "/api/notifications/devices",
        json={"push_token": "tok-aaaa", "platform": "ios", "app_version": "0.2.0"},
    )
    assert r.status_code == 200
    rows = (await db_session.execute(select(NotificationDevice))).scalars().all()
    assert len(rows) == 1
    assert rows[0].app_version == "0.2.0"


@pytest.mark.asyncio
async def test_delete_device_removes_row(authed_client, db_session, current_user):
    db_session.add(NotificationDevice(
        user_id=current_user.id, platform=DevicePlatform.ios, push_token="tok-bbbb",
    ))
    await db_session.flush()
    r = await authed_client.delete("/api/notifications/devices/tok-bbbb")
    assert r.status_code == 200
    remaining = (await db_session.execute(select(NotificationDevice))).scalars().all()
    assert remaining == []


@pytest.mark.asyncio
async def test_feed_returns_paginated_notifications(authed_client, db_session, current_user):
    for i in range(5):
        db_session.add(Notification(
            user_id=current_user.id,
            type=NotificationType.announcement,
            title=f"#{i}", body="b", deep_link="/x", data={},
        ))
    await db_session.flush()
    r = await authed_client.get("/api/notifications?limit=3")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert len(body["data"]["items"]) == 3


@pytest.mark.asyncio
async def test_unread_count(authed_client, db_session, current_user):
    db_session.add(Notification(
        user_id=current_user.id, type=NotificationType.announcement,
        title="a", body="b", deep_link="/x", data={}, read_at=None,
    ))
    db_session.add(Notification(
        user_id=current_user.id, type=NotificationType.announcement,
        title="a", body="b", deep_link="/x", data={},
        read_at=datetime.now(timezone.utc),
    ))
    await db_session.flush()
    r = await authed_client.get("/api/notifications/unread-count")
    assert r.json()["data"]["unread"] == 1


@pytest.mark.asyncio
async def test_mark_single_read(authed_client, db_session, current_user):
    n = Notification(
        user_id=current_user.id, type=NotificationType.announcement,
        title="a", body="b", deep_link="/x", data={},
    )
    db_session.add(n)
    await db_session.flush()
    r = await authed_client.post(f"/api/notifications/{n.id}/read")
    assert r.status_code == 200
    await db_session.refresh(n)
    assert n.read_at is not None


@pytest.mark.asyncio
async def test_mark_all_read(authed_client, db_session, current_user):
    for _ in range(3):
        db_session.add(Notification(
            user_id=current_user.id, type=NotificationType.announcement,
            title="a", body="b", deep_link="/x", data={},
        ))
    await db_session.flush()
    r = await authed_client.post("/api/notifications/read-all")
    assert r.status_code == 200
    rows = (await db_session.execute(
        select(Notification).where(Notification.user_id == current_user.id)
    )).scalars().all()
    assert all(n.read_at is not None for n in rows)


@pytest.mark.asyncio
async def test_user_cannot_mark_other_users_notification_read(
    authed_client, db_session
):
    other = uuid.uuid4()
    n = Notification(
        user_id=other, type=NotificationType.announcement,
        title="a", body="b", deep_link="/x", data={},
    )
    db_session.add(n)
    await db_session.flush()
    r = await authed_client.post(f"/api/notifications/{n.id}/read")
    assert r.status_code == 404
```

These tests assume the existing test fixtures provide `authed_client` and `current_user`. If they don't, check `backend/tests/conftest.py` for the equivalent fixture names and adjust.

- [ ] **Step 2: Confirm tests fail**

```bash
pytest tests/test_api_notifications.py -v
```

Expected: most tests fail with `404 Not Found` (router not registered).

- [ ] **Step 3: Implement `backend/app/api/notifications.py`**

```python
from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.notification import Notification, NotificationDevice
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.notification import (
    DeviceRegister,
    DeviceResponse,
    NotificationResponse,
    UnreadCountResponse,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post(
    "/devices",
    response_model=APIResponse[DeviceResponse],
)
async def register_device(
    body: DeviceRegister,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[DeviceResponse]:
    stmt = pg_insert(NotificationDevice).values(
        user_id=user.id,
        platform=body.platform,
        push_token=body.push_token,
        app_version=body.app_version,
        last_seen_at=datetime.now(timezone.utc),
    ).on_conflict_do_update(
        index_elements=[NotificationDevice.push_token],
        set_={
            "user_id": user.id,
            "platform": body.platform,
            "app_version": body.app_version,
            "last_seen_at": datetime.now(timezone.utc),
        },
    ).returning(NotificationDevice)
    row = (await db.execute(stmt)).scalar_one()
    await db.commit()
    return APIResponse(success=True, data=DeviceResponse.model_validate(row))


@router.delete(
    "/devices/{push_token}",
    response_model=APIResponse[None],
)
async def unregister_device(
    push_token: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> APIResponse[None]:
    res = await db.execute(
        select(NotificationDevice).where(
            and_(
                NotificationDevice.push_token == push_token,
                NotificationDevice.user_id == user.id,
            )
        )
    )
    device = res.scalar_one_or_none()
    if device is not None:
        await db.delete(device)
        await db.commit()
    return APIResponse(success=True, data=None)


def _encode_cursor(n: Notification) -> str:
    raw = {"created_at": n.created_at.isoformat(), "id": str(n.id)}
    return base64.urlsafe_b64encode(json.dumps(raw).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    raw = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    return datetime.fromisoformat(raw["created_at"]), uuid.UUID(raw["id"])


class _FeedItems:
    items: list[NotificationResponse]
    next_cursor: str | None


@router.get(
    "",
    response_model=APIResponse[dict],
)
async def list_notifications(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit + 1)
    )
    if cursor:
        ts, last_id = _decode_cursor(cursor)
        stmt = stmt.where(
            (Notification.created_at < ts)
            | ((Notification.created_at == ts) & (Notification.id < last_id))
        )

    rows = (await db.execute(stmt)).scalars().all()
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = _encode_cursor(page[-1]) if has_more and page else None

    return APIResponse(
        success=True,
        data={
            "items": [NotificationResponse.model_validate(r) for r in page],
            "next_cursor": next_cursor,
        },
    )


@router.get(
    "/unread-count",
    response_model=APIResponse[UnreadCountResponse],
)
async def unread_count(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    n = (await db.execute(
        select(func.count(Notification.id)).where(
            and_(Notification.user_id == user.id, Notification.read_at.is_(None))
        )
    )).scalar_one()
    return APIResponse(success=True, data=UnreadCountResponse(unread=n))


@router.post(
    "/{notification_id}/read",
    response_model=APIResponse[None],
)
async def mark_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    n = (await db.execute(
        select(Notification).where(
            and_(Notification.id == notification_id, Notification.user_id == user.id)
        )
    )).scalar_one_or_none()
    if n is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    n.read_at = datetime.now(timezone.utc)
    await db.commit()
    return APIResponse(success=True, data=None)


@router.post(
    "/read-all",
    response_model=APIResponse[None],
)
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await db.execute(
        update(Notification)
        .where(and_(Notification.user_id == user.id, Notification.read_at.is_(None)))
        .values(read_at=datetime.now(timezone.utc))
    )
    await db.commit()
    return APIResponse(success=True, data=None)
```

- [ ] **Step 4: Register the router**

In `backend/app/api/__init__.py`:

```python
from app.api.notifications import router as notifications_router
# ...
api_router.include_router(notifications_router)
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_api_notifications.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/notifications.py backend/app/api/__init__.py backend/tests/test_api_notifications.py
git commit -m "feat(backend): /api/notifications device + feed endpoints"
```

---

## Task B7: Announcements router (instructor compose)

**Files:**
- Create: `backend/app/api/announcements.py`
- Modify: `backend/app/api/__init__.py`
- Create: `backend/tests/test_api_announcements.py`

- [ ] **Step 1: Write failing tests**

`backend/tests/test_api_announcements.py`:

```python
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.course import Course, Enrollment
from app.models.notification import Announcement, AnnouncementSendMode
from app.models.user import User


@pytest.mark.asyncio
async def test_instructor_can_create_announcement_send_now(
    authed_instructor_client, db_session, instructor_user
):
    course = Course(
        id=uuid.uuid4(), name="CS101", code="CS101",
        language="english", instructor_id=instructor_user.id,
        enroll_code="ABCD1234",
    )
    db_session.add(course)
    student = User(id=uuid.uuid4(), email="s@connect.ust.hk", name="S", role="student")
    db_session.add(student)
    db_session.add(Enrollment(course_id=course.id, user_id=student.id))
    await db_session.flush()

    with patch("app.services.notifier.dispatch", new=AsyncMock()) as m_disp:
        r = await authed_instructor_client.post(
            f"/api/courses/{course.id}/announcements",
            json={"title": "Reminder", "body": "Read ch.3", "send_mode": "now"},
        )
    assert r.status_code == 201, r.text
    rows = (await db_session.execute(select(Announcement))).scalars().all()
    assert len(rows) == 1
    assert rows[0].sent_at is not None
    # one fanout per enrolled student
    assert m_disp.await_count == 1


@pytest.mark.asyncio
async def test_digest_announcement_does_not_dispatch_immediately(
    authed_instructor_client, db_session, instructor_user
):
    course = Course(
        id=uuid.uuid4(), name="CS102", code="CS102",
        language="english", instructor_id=instructor_user.id,
        enroll_code="QQQQ9999",
    )
    db_session.add(course)
    await db_session.flush()

    with patch("app.services.notifier.dispatch", new=AsyncMock()) as m_disp:
        r = await authed_instructor_client.post(
            f"/api/courses/{course.id}/announcements",
            json={"title": "Later", "body": "x", "send_mode": "digest"},
        )
    assert r.status_code == 201
    a = (await db_session.execute(select(Announcement))).scalar_one()
    assert a.sent_at is None
    assert a.send_mode == AnnouncementSendMode.digest
    m_disp.assert_not_awaited()


@pytest.mark.asyncio
async def test_student_cannot_create_announcement(
    authed_client, db_session, instructor_user
):
    course = Course(
        id=uuid.uuid4(), name="CS103", code="CS103",
        language="english", instructor_id=instructor_user.id,
        enroll_code="WWWW1111",
    )
    db_session.add(course)
    await db_session.flush()

    r = await authed_client.post(
        f"/api/courses/{course.id}/announcements",
        json={"title": "x", "body": "y"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_enrolled_student_can_read_announcement(
    authed_client, db_session, current_user
):
    instructor = User(id=uuid.uuid4(), email="i@ust.hk", name="I", role="instructor")
    course = Course(
        id=uuid.uuid4(), name="CS105", code="CS105",
        language="english", instructor_id=instructor.id,
        enroll_code="READREAD",
    )
    db_session.add_all([instructor, course])
    db_session.add(Enrollment(course_id=course.id, user_id=current_user.id))
    a = Announcement(
        course_id=course.id, author_id=instructor.id,
        title="Hi", body="Body", send_mode=AnnouncementSendMode.now,
    )
    db_session.add(a)
    await db_session.flush()
    r = await authed_client.get(f"/api/courses/{course.id}/announcements/{a.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["title"] == "Hi"


@pytest.mark.asyncio
async def test_non_enrolled_student_cannot_read_announcement(
    authed_client, db_session
):
    instructor = User(id=uuid.uuid4(), email="i@ust.hk", name="I", role="instructor")
    course = Course(
        id=uuid.uuid4(), name="CS106", code="CS106",
        language="english", instructor_id=instructor.id,
        enroll_code="NOREAD00",
    )
    db_session.add_all([instructor, course])
    a = Announcement(
        course_id=course.id, author_id=instructor.id,
        title="x", body="y", send_mode=AnnouncementSendMode.now,
    )
    db_session.add(a)
    await db_session.flush()
    r = await authed_client.get(f"/api/courses/{course.id}/announcements/{a.id}")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_retract_sets_retracted_at(
    authed_instructor_client, db_session, instructor_user
):
    course = Course(
        id=uuid.uuid4(), name="CS104", code="CS104",
        language="english", instructor_id=instructor_user.id,
        enroll_code="EEEE3333",
    )
    db_session.add(course)
    a = Announcement(
        course_id=course.id, author_id=instructor_user.id,
        title="x", body="y", send_mode=AnnouncementSendMode.now,
    )
    db_session.add(a)
    await db_session.flush()
    r = await authed_instructor_client.delete(
        f"/api/courses/{course.id}/announcements/{a.id}"
    )
    assert r.status_code == 200
    await db_session.refresh(a)
    assert a.retracted_at is not None
```

If `authed_instructor_client` and `instructor_user` fixtures don't exist, add them to `conftest.py` modeled on the existing `authed_client` / `current_user`. The fix is small: a fixture that overrides `require_instructor` to return a User with `role='instructor'`.

- [ ] **Step 2: Confirm tests fail**

```bash
pytest tests/test_api_announcements.py -v
```

Expected: 4 failures (404 / 403 mismatches).

- [ ] **Step 3: Implement `backend/app/api/announcements.py`**

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._helpers import verify_course_ownership_or_admin
from app.api.deps import get_current_user, get_db, require_instructor
from app.models.course import Course, Enrollment
from app.models.notification import (
    Announcement,
    AnnouncementSendMode,
    NotificationType,
)
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.notification import AnnouncementCreate, AnnouncementResponse
from app.services import notifier

router = APIRouter(prefix="/courses", tags=["announcements"])


async def _enrolled_student_ids(db: AsyncSession, course_id: uuid.UUID) -> list[uuid.UUID]:
    return (
        await db.execute(
            select(Enrollment.user_id).where(Enrollment.course_id == course_id)
        )
    ).scalars().all()


async def _verify_instructor_owns_course(
    db: AsyncSession, course_id: uuid.UUID, instructor: User
) -> Course:
    c = (
        await db.execute(select(Course).where(Course.id == course_id))
    ).scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    if c.instructor_id != instructor.id and instructor.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return c


@router.post(
    "/{course_id}/announcements",
    response_model=APIResponse[AnnouncementResponse],
    status_code=201,
)
async def create_announcement(
    course_id: uuid.UUID,
    body: AnnouncementCreate,
    db: AsyncSession = Depends(get_db),
    instructor: User = Depends(require_instructor),
):
    course = await _verify_instructor_owns_course(db, course_id, instructor)
    a = Announcement(
        course_id=course.id,
        author_id=instructor.id,
        title=body.title,
        body=body.body,
        send_mode=body.send_mode,
    )
    db.add(a)
    await db.flush()

    if body.send_mode == AnnouncementSendMode.now:
        student_ids = await _enrolled_student_ids(db, course.id)
        for sid in student_ids:
            await notifier.dispatch(
                db, sid,
                type_=NotificationType.announcement,
                title=body.title,
                body=body.body[:200],
                deep_link=f"/dashboard/courses/{course.id}/announcements/{a.id}",
                data={"course_id": str(course.id), "announcement_id": str(a.id)},
            )
        a.sent_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(a)
    return APIResponse(success=True, data=AnnouncementResponse.model_validate(a))


@router.get(
    "/{course_id}/announcements",
    response_model=APIResponse[list[AnnouncementResponse]],
)
async def list_announcements(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    instructor: User = Depends(require_instructor),
):
    await _verify_instructor_owns_course(db, course_id, instructor)
    rows = (
        await db.execute(
            select(Announcement)
            .where(Announcement.course_id == course_id)
            .order_by(Announcement.created_at.desc())
        )
    ).scalars().all()
    return APIResponse(success=True, data=[AnnouncementResponse.model_validate(r) for r in rows])


@router.get(
    "/{course_id}/announcements/{announcement_id}",
    response_model=APIResponse[AnnouncementResponse],
)
async def get_announcement(
    course_id: uuid.UUID,
    announcement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Read a single announcement.

    Accessible to instructors who own the course AND to students enrolled in
    the course. This is the read-side that students hit when they tap a
    notification deep link.
    """
    a = (
        await db.execute(
            select(Announcement).where(
                and_(Announcement.id == announcement_id, Announcement.course_id == course_id)
            )
        )
    ).scalar_one_or_none()
    if a is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # Course owner / admin always allowed.
    course = (
        await db.execute(select(Course).where(Course.id == course_id))
    ).scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if course.instructor_id == user.id or user.role == "admin":
        return APIResponse(success=True, data=AnnouncementResponse.model_validate(a))

    # Students must be enrolled.
    enrolled = (
        await db.execute(
            select(Enrollment).where(
                and_(Enrollment.course_id == course_id, Enrollment.user_id == user.id)
            )
        )
    ).scalar_one_or_none()
    if enrolled is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return APIResponse(success=True, data=AnnouncementResponse.model_validate(a))


@router.delete(
    "/{course_id}/announcements/{announcement_id}",
    response_model=APIResponse[None],
)
async def retract_announcement(
    course_id: uuid.UUID,
    announcement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    instructor: User = Depends(require_instructor),
):
    await _verify_instructor_owns_course(db, course_id, instructor)
    a = (
        await db.execute(
            select(Announcement).where(
                and_(Announcement.id == announcement_id, Announcement.course_id == course_id)
            )
        )
    ).scalar_one_or_none()
    if a is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    a.retracted_at = datetime.now(timezone.utc)
    await db.commit()
    return APIResponse(success=True, data=None)
```

If `verify_course_ownership_or_admin` doesn't already exist in `_helpers.py`, the helper is implemented inline above (`_verify_instructor_owns_course`); the import line can be removed.

- [ ] **Step 4: Register the router**

In `backend/app/api/__init__.py`:

```python
from app.api.announcements import router as announcements_router
# ...
api_router.include_router(announcements_router)
```

- [ ] **Step 5: Add `authed_instructor_client` + `instructor_user` fixtures** (if missing)

Open `backend/tests/conftest.py` and look for the existing `authed_client` / `current_user` fixtures. Right after them, add:

```python
@pytest_asyncio.fixture
async def instructor_user(db_session) -> User:
    u = User(
        id=uuid.uuid4(),
        email="prof@ust.hk",
        name="Prof",
        role="instructor",
    )
    db_session.add(u)
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def authed_instructor_client(db_session, instructor_user):
    from app.api.deps import require_instructor, get_current_user, get_db
    from app.main import app
    app.dependency_overrides[get_current_user] = lambda: instructor_user
    app.dependency_overrides[require_instructor] = lambda: instructor_user
    app.dependency_overrides[get_db] = lambda: db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
```

(Adapt to the existing conftest's exact structure if it differs.)

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_api_announcements.py -v
```

Expected: 4/4 PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/announcements.py backend/app/api/__init__.py backend/tests/test_api_announcements.py backend/tests/conftest.py
git commit -m "feat(backend): instructor announcements API + send_mode=now dispatch"
```

---

## Task B8: Course-update batching service

**Files:**
- Create: `backend/app/services/notification_throttle.py`
- Create: `backend/tests/test_notification_throttle.py`

The spec says: course updates batch within a 30-min window, max 1/day per (course, user). The simplest correct implementation is to **aggregate at dispatch time**: when an event arrives, check if a `course_update` notification for the same `(user, course)` exists with `created_at >= now-30min`. If yes, **update it in place** (append to data, increment counter, update title); otherwise create new.

- [ ] **Step 1: Write failing tests**

`backend/tests/test_notification_throttle.py`:

```python
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.notification import Notification, NotificationType
from app.models.user import User
from app.services.notification_throttle import dispatch_course_update


@pytest.fixture
async def student(db_session):
    u = User(id=uuid.uuid4(), email="s@connect.ust.hk", name="S", role="student")
    db_session.add(u)
    await db_session.flush()
    return u


@pytest.mark.asyncio
async def test_first_event_creates_notification(db_session, student):
    course_id = uuid.uuid4()
    await dispatch_course_update(
        db_session, student.id, course_id, content_type="document", title="ch1.pdf"
    )
    rows = (await db_session.execute(
        select(Notification).where(Notification.user_id == student.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].type == NotificationType.course_update
    assert "1 new" in rows[0].body or "ch1.pdf" in rows[0].body


@pytest.mark.asyncio
async def test_second_event_within_window_aggregates(db_session, student):
    course_id = uuid.uuid4()
    await dispatch_course_update(
        db_session, student.id, course_id, content_type="document", title="a.pdf"
    )
    await dispatch_course_update(
        db_session, student.id, course_id, content_type="quiz", title="Q1"
    )
    rows = (await db_session.execute(
        select(Notification).where(Notification.user_id == student.id)
    )).scalars().all()
    assert len(rows) == 1, "Second event should aggregate, not create"
    assert "2 new" in rows[0].body


@pytest.mark.asyncio
async def test_event_outside_window_creates_new_notification(db_session, student):
    course_id = uuid.uuid4()
    old = Notification(
        user_id=student.id, type=NotificationType.course_update,
        title="x", body="1 new", deep_link="/x", data={"count": 1, "course_id": str(course_id)},
        created_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    db_session.add(old)
    await db_session.flush()
    await dispatch_course_update(
        db_session, student.id, course_id, content_type="document", title="b.pdf"
    )
    rows = (await db_session.execute(
        select(Notification).where(Notification.user_id == student.id)
    )).scalars().all()
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_max_one_per_day(db_session, student):
    """If we already aggregated 5 today, the 6th event should still mutate the
    SAME row (not create new), preserving the daily cap intent."""
    course_id = uuid.uuid4()
    for _ in range(6):
        await dispatch_course_update(
            db_session, student.id, course_id, content_type="document", title="x.pdf"
        )
    rows = (await db_session.execute(
        select(Notification).where(Notification.user_id == student.id)
    )).scalars().all()
    assert len(rows) == 1
    assert "6 new" in rows[0].body
```

- [ ] **Step 2: Implement `backend/app/services/notification_throttle.py`**

```python
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationType

WINDOW = timedelta(minutes=30)


async def dispatch_course_update(
    db: AsyncSession,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    *,
    content_type: str,
    title: str,
) -> Notification:
    """Aggregate course-update notifications within a 30-min window per (user, course).

    The most-recent course_update notification for (user, course) created within
    WINDOW is mutated in place: counter incremented, body rewritten. Outside the
    window, a fresh row is created. This also implements the 'max 1/day' rule
    implicitly: while aggregation keeps happening, only one row exists.
    """
    cutoff = datetime.now(timezone.utc) - WINDOW
    existing = (
        await db.execute(
            select(Notification)
            .where(
                and_(
                    Notification.user_id == user_id,
                    Notification.type == NotificationType.course_update,
                    Notification.data["course_id"].astext == str(course_id),
                    Notification.created_at >= cutoff,
                )
            )
            .order_by(Notification.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if existing is not None:
        count = int(existing.data.get("count", 1)) + 1
        existing.data = {**existing.data, "count": count}
        existing.title = "Course updates"
        existing.body = f"{count} new items in this course"
        await db.flush()
        return existing

    notif = Notification(
        user_id=user_id,
        type=NotificationType.course_update,
        title="Course update",
        body=f"1 new {content_type}: {title}",
        deep_link=f"/dashboard/courses/{course_id}",
        data={"course_id": str(course_id), "count": 1},
    )
    db.add(notif)
    await db.flush()
    return notif
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_notification_throttle.py -v
```

Expected: 4/4 PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/notification_throttle.py backend/tests/test_notification_throttle.py
git commit -m "feat(backend): course-update notification batching (30-min window)"
```

---

## Task B9: Wire trigger sites — live quiz, document ready, content ready

**Files:**
- Modify: `backend/app/api/live.py`
- Modify: `backend/app/api/documents.py`
- Modify: `backend/app/services/worker.py` (if async generation lives there) — confirm path
- Modify: `backend/tests/test_api_live.py` (likely adjustments)

- [ ] **Step 1: Locate live-session-start handler**

```bash
grep -n "session.*start\|start.*session\|@router\.post" backend/app/api/live.py | head -10
```

Find the endpoint that creates a live session.

- [ ] **Step 2: Add notifier.dispatch on live session start**

In the live-session-start handler, after the session row is created, add:

```python
from app.models.course import Enrollment
from app.models.notification import NotificationType
from app.services import notifier

# After creating `session`:
enrolled_ids = (
    await db.execute(
        select(Enrollment.user_id).where(Enrollment.course_id == session.course_id)
    )
).scalars().all()
for sid in enrolled_ids:
    await notifier.dispatch(
        db, sid,
        type_=NotificationType.live_quiz_invite,
        title=f"Live quiz starting",
        body=f"{course.name} is now live — tap to join",
        deep_link=f"/dashboard/courses/{session.course_id}/live/{session.id}",
        data={"course_id": str(session.course_id), "session_id": str(session.id)},
    )
```

- [ ] **Step 3: Add notifier on async generation completion**

Find the worker handler for quiz/summary/flashcard generation:

```bash
grep -n "task.*type\|TaskType\|generate" backend/app/services/worker.py | head -20
```

Where the worker sets a task to `completed`, add:

```python
from app.models.notification import NotificationType
from app.services import notifier

# After successfully completing a quiz/summary/flashcard generation:
deep_link = _deep_link_for_task(task)  # e.g., /dashboard/courses/.../quizzes/{id}
title = "Quiz ready" if task.type == "quiz" else "Summary ready" if task.type == "summary" else "Flashcards ready"
await notifier.dispatch(
    db, task.user_id,
    type_=NotificationType.content_ready,
    title=title,
    body=f"Your {task.type} for {course.name} is ready",
    deep_link=deep_link,
    data={"task_id": str(task.id), "course_id": str(task.course_id)},
)
```

(Implement `_deep_link_for_task` near the worker — it's a small mapping function.)

- [ ] **Step 4: Add notifier for new documents (course-update path)**

In `backend/app/api/documents.py`, find the upload endpoint. After the document is created and pipelined, dispatch a course update to enrolled students:

```python
from app.services.notification_throttle import dispatch_course_update

enrolled_ids = (await db.execute(
    select(Enrollment.user_id).where(Enrollment.course_id == document.course_id)
)).scalars().all()
for sid in enrolled_ids:
    if sid == user.id:
        continue  # don't notify the uploader (instructor)
    await dispatch_course_update(
        db, sid, document.course_id,
        content_type="document", title=document.original_filename,
    )
```

- [ ] **Step 5: Run the existing live + document test suites**

```bash
pytest tests/test_api_live.py tests/test_api_documents.py 2>&1 | tail -30
```

Expected: tests still pass. If tests break because they don't expect the dispatch side-effect, mock it:

```python
with patch("app.services.notifier.dispatch", new=AsyncMock()):
    # existing test body
```

- [ ] **Step 6: Add an integration test confirming dispatch happened**

`backend/tests/test_notification_integration.py`:

```python
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.models.course import Course, Enrollment
from app.models.user import User


@pytest.mark.asyncio
async def test_starting_live_session_dispatches_to_enrolled_students(
    authed_instructor_client, db_session, instructor_user
):
    course = Course(
        id=uuid.uuid4(), name="X", code="X",
        language="english", instructor_id=instructor_user.id,
        enroll_code="LIVE0001",
    )
    db_session.add(course)
    s1 = User(id=uuid.uuid4(), email="a@connect.ust.hk", name="A", role="student")
    s2 = User(id=uuid.uuid4(), email="b@connect.ust.hk", name="B", role="student")
    db_session.add_all([s1, s2])
    db_session.add_all([
        Enrollment(course_id=course.id, user_id=s1.id),
        Enrollment(course_id=course.id, user_id=s2.id),
    ])
    await db_session.flush()

    with patch("app.services.notifier.dispatch", new=AsyncMock()) as m:
        # Adapt the path/payload to match the existing live-session-start endpoint:
        r = await authed_instructor_client.post(
            f"/api/courses/{course.id}/live/start",
            json={"quiz_id": str(uuid.uuid4())},
        )
    assert m.await_count == 2
```

(The exact path / payload may differ — match whatever the existing live router uses.)

- [ ] **Step 7: Run the integration test**

```bash
pytest tests/test_notification_integration.py -v
```

Expected: PASS (or adjust path/payload until it matches the real endpoint).

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/live.py backend/app/api/documents.py backend/app/services/worker.py backend/tests/test_notification_integration.py
git commit -m "feat(backend): trigger notifications on live start, doc ready, content ready"
```

---

## Task B10: Daily 8am announcement-digest scheduler

**Files:**
- Modify: `backend/app/services/worker.py` (or whichever lifespan-managed task file the project uses)
- Create: `backend/app/services/announcement_digest.py`
- Create: `backend/tests/test_announcement_digest.py`

- [ ] **Step 1: Look at the existing scheduler pattern (canvas_sync)**

```bash
sed -n '1,40p' backend/app/services/canvas_sync.py
```

Note the `run_scheduler(shutdown_event)` shape. We'll mirror it.

- [ ] **Step 2: Implement `backend/app/services/announcement_digest.py`**

```python
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.course import Enrollment
from app.models.notification import (
    Announcement,
    AnnouncementSendMode,
    NotificationType,
)
from app.services import notifier

log = logging.getLogger(__name__)

DIGEST_HOUR_UTC = 0  # 8am HKT == 00:00 UTC


async def run_scheduler(shutdown_event: asyncio.Event) -> None:
    """Once a day at DIGEST_HOUR_UTC, dispatch all pending digest announcements."""
    log.info("announcement digest scheduler starting (DIGEST_HOUR_UTC=%s)", DIGEST_HOUR_UTC)
    while not shutdown_event.is_set():
        seconds = _seconds_until_next_run()
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=seconds)
            return  # shutdown
        except asyncio.TimeoutError:
            pass
        try:
            async with async_session_factory() as db:
                await flush_digest(db)
        except Exception:  # noqa: BLE001
            log.exception("digest flush failed")


def _seconds_until_next_run(now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    target = now.replace(hour=DIGEST_HOUR_UTC, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def flush_digest(db: AsyncSession) -> int:
    """Find all `digest` announcements not yet sent and dispatch them.

    Returns the number of announcements processed.
    """
    pending = (
        await db.execute(
            select(Announcement).where(
                and_(
                    Announcement.send_mode == AnnouncementSendMode.digest,
                    Announcement.sent_at.is_(None),
                    Announcement.retracted_at.is_(None),
                )
            )
        )
    ).scalars().all()

    if not pending:
        return 0

    for a in pending:
        student_ids = (
            await db.execute(
                select(Enrollment.user_id).where(Enrollment.course_id == a.course_id)
            )
        ).scalars().all()
        for sid in student_ids:
            await notifier.dispatch(
                db, sid,
                type_=NotificationType.announcement,
                title=a.title,
                body=a.body[:200],
                deep_link=f"/dashboard/courses/{a.course_id}/announcements/{a.id}",
                data={"course_id": str(a.course_id), "announcement_id": str(a.id)},
            )
        a.sent_at = datetime.now(timezone.utc)

    await db.commit()
    log.info("flushed %s digest announcements", len(pending))
    return len(pending)
```

(Confirm `async_session_factory` is the right import — it may be in `app.database` or you may need to adapt.)

- [ ] **Step 3: Plug the scheduler into the FastAPI lifespan**

In `backend/app/main.py`, find the `lifespan` async-context-manager and add the scheduler alongside the existing canvas/worker tasks:

```python
from app.services.announcement_digest import run_scheduler as run_digest_scheduler

# inside lifespan(), where other background_tasks are appended:
background_tasks.append(asyncio.create_task(run_digest_scheduler(shutdown_event)))
```

- [ ] **Step 4: Write a unit test for `flush_digest`**

`backend/tests/test_announcement_digest.py`:

```python
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.models.course import Course, Enrollment
from app.models.notification import (
    Announcement,
    AnnouncementSendMode,
    NotificationType,
)
from app.models.user import User
from app.services.announcement_digest import flush_digest


@pytest.mark.asyncio
async def test_flush_digest_dispatches_to_enrolled_students(db_session):
    instr = User(id=uuid.uuid4(), email="i@ust.hk", name="I", role="instructor")
    s1 = User(id=uuid.uuid4(), email="a@connect.ust.hk", name="A", role="student")
    s2 = User(id=uuid.uuid4(), email="b@connect.ust.hk", name="B", role="student")
    course = Course(
        id=uuid.uuid4(), name="N", code="N",
        language="english", instructor_id=instr.id, enroll_code="DIGEST01",
    )
    db_session.add_all([instr, s1, s2, course])
    db_session.add_all([
        Enrollment(course_id=course.id, user_id=s1.id),
        Enrollment(course_id=course.id, user_id=s2.id),
    ])
    a = Announcement(
        course_id=course.id, author_id=instr.id,
        title="t", body="b", send_mode=AnnouncementSendMode.digest,
    )
    db_session.add(a)
    await db_session.flush()

    with patch("app.services.notifier.dispatch", new=AsyncMock()) as m:
        n = await flush_digest(db_session)

    assert n == 1
    assert m.await_count == 2
    await db_session.refresh(a)
    assert a.sent_at is not None
```

- [ ] **Step 5: Run the test**

```bash
pytest tests/test_announcement_digest.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/announcement_digest.py backend/app/main.py backend/tests/test_announcement_digest.py
git commit -m "feat(backend): daily 8am announcement-digest scheduler"
```

---

## Task B11: Suppression rules (foreground/active route + send_enabled)

**Files:**
- Modify: `backend/app/services/notifier.py` (add foreground hint param)
- This is mostly client-side per the spec; backend just exposes the toggle.

- [ ] **Step 1: Add `suppress_push` parameter to `notifier.dispatch`**

For now, the only suppression backend implements is `push_send_enabled=False` from config (already wired in `push.send`). Foreground suppression is client-side and is implemented in Plan C.

Document the deferred behavior with a docstring update on `notifier.dispatch`:

```python
async def dispatch(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    type_: NotificationType,
    title: str,
    body: str,
    deep_link: str,
    data: dict[str, Any],
) -> Notification:
    """Persist a notification and fan it out to all of the user's devices.

    Backend-side suppression: governed by `settings.push_send_enabled`. When
    false, rows are still inserted in `notifications` (so the in-app feed works
    normally) but no APNs/FCM call is made.

    Client-side suppression (foreground / active-route) is implemented in the
    Capacitor `pushNotificationReceived` listener — see Plan C.
    """
    ...
```

(The body is unchanged — this step is purely the docstring update.)

- [ ] **Step 2: Verify that with PUSH_SEND_ENABLED=false, dispatch still inserts the row**

`backend/tests/test_notifier.py` already has `test_dispatch_inserts_notification_row` which mocks the push send. Add one more:

```python
@pytest.mark.asyncio
async def test_dispatch_with_push_disabled_still_inserts_feed_row(db_session, user):
    db_session.add(NotificationDevice(
        user_id=user.id, platform=DevicePlatform.ios, push_token="x-token-eeee",
    ))
    await db_session.flush()
    with patch("app.services.notifier.push_send", new=AsyncMock()):
        with patch("app.config.settings.push_send_enabled", False):
            await dispatch(
                db_session, user.id,
                type_=NotificationType.announcement,
                title="t", body="b", deep_link="/x", data={},
            )
    rows = (await db_session.execute(select(Notification))).scalars().all()
    assert len(rows) == 1
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_notifier.py -v
```

Expected: 5/5 PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/notifier.py backend/tests/test_notifier.py
git commit -m "docs(backend): clarify notifier suppression rules"
```

---

## Task B12: Production secrets and deploy

**Files:**
- (none — operational)

- [ ] **Step 1: Generate APNs auth key**

In Apple Developer portal:
1. Certificates, Identifiers & Profiles → Keys → "+"
2. Name: "Meli APNs"
3. Enable "Apple Push Notifications service (APNs)"
4. Continue → Register → Download the `.p8` file (one-time)
5. Note the Key ID (10 chars) and your Team ID

- [ ] **Step 2: Generate FCM service account JSON**

Firebase Console → Project Settings → Service accounts → Generate new private key → download JSON.

- [ ] **Step 3: Set Railway environment variables**

```bash
# From repo root
railway link  # if not already
railway variables set APNS_KEY_ID="$KEY_ID"
railway variables set APNS_TEAM_ID="$TEAM_ID"
railway variables set APNS_TOPIC="hk.ust.meli"
railway variables set APNS_USE_SANDBOX="true"  # initially TestFlight; flip to false before public listing
railway variables set FCM_SERVICE_ACCOUNT_JSON="$(cat firebase-service-account.json)"
railway variables set PUSH_SEND_ENABLED="true"
```

For the `.p8` file: upload it as a file artifact via Railway's CLI:

```bash
railway run --service backend -- bash -c "cat > /app/secrets/apns_key.p8" < AuthKey_KEYID.p8
railway variables set APNS_AUTH_KEY_PATH="/app/secrets/apns_key.p8"
```

(Adapt to whatever file-secret mechanism Railway supports for your setup; Volume mounts or env-as-file via the dashboard both work.)

- [ ] **Step 4: Deploy**

```bash
git push origin main
railway logs --tail 100
```

Expected:
- Deploy succeeds
- App boots; lifespan tasks include digest scheduler
- A test `POST /api/notifications/devices` from any client returns 200

- [ ] **Step 5: Smoke test in production**

```bash
TOKEN=$(curl -X POST $API/api/auth/dev-login | jq -r '.data.token')  # or your usual auth path
curl -X POST $API/api/notifications/devices \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"push_token":"smoke-test-token","platform":"ios","app_version":"0.1.0"}'

curl $API/api/notifications -H "Authorization: Bearer $TOKEN"
```

Expected: device row is created; feed lists 0 items (none dispatched yet).

- [ ] **Step 6: Document the runbook**

Create `backend/docs/notifications-runbook.md`:

```markdown
# Notifications Runbook

## Toggling push send (incident response)

If APNs or FCM goes pear-shaped, suppress all push without taking the app down:

```bash
railway variables set PUSH_SEND_ENABLED=false
railway redeploy
```

In-app notification feed continues to work — only push delivery is silent.

## Rotating APNs key

Generate a new key in Apple Developer portal, then:

```bash
railway run --service backend -- bash -c "cat > /app/secrets/apns_key.p8" < AuthKey_NEWKEY.p8
railway variables set APNS_KEY_ID="$NEW_KEY_ID"
railway redeploy
```

The old key remains valid until you revoke it in Apple Developer portal.

## Rotating FCM service account

Same pattern: generate new JSON in Firebase Console, set
`FCM_SERVICE_ACCOUNT_JSON`, redeploy.

## Sandbox vs production APNs

- Sandbox = TestFlight + dev builds (`APNS_USE_SANDBOX=true`)
- Production = App Store + production builds (`APNS_USE_SANDBOX=false`)

Both can coexist if you maintain two backend environments. For our pilot,
keep sandbox until the public App Store listing goes live, then flip
both `APNS_USE_SANDBOX=false` and re-deploy in lock-step.
```

- [ ] **Step 7: Commit**

```bash
git add backend/docs/notifications-runbook.md
git commit -m "docs(backend): notifications runbook for deploy + rotation + suppression"
```

---

## Acceptance criteria for Plan B

- [ ] `alembic upgrade head` from clean DB succeeds; three new tables present
- [ ] `pytest backend/tests/` passes including the 5+ new test files
- [ ] `POST /api/notifications/devices` registers and updates devices
- [ ] `DELETE /api/notifications/devices/:token` removes them
- [ ] `GET /api/notifications` returns paginated feed
- [ ] `GET /api/notifications/unread-count` accurate
- [ ] `POST /api/notifications/:id/read` and `/read-all` work
- [ ] `POST /api/courses/:id/announcements` works for instructors only; 403 for students
- [ ] `send_mode=now` triggers fan-out; `send_mode=digest` does not
- [ ] Course-update events within 30 min aggregate into one notification row
- [ ] Live-quiz session start dispatches to all enrolled students
- [ ] Async generation completion dispatches `content_ready` to the requesting user
- [ ] Daily digest scheduler is started in app lifespan, can be unit-tested via `flush_digest`
- [ ] `PUSH_SEND_ENABLED=false` keeps in-app feed working but skips APNs/FCM
- [ ] Production env vars set; smoke `curl` works
