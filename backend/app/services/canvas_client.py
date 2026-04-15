"""Per-user Canvas REST client with refresh-on-401 and Link pagination."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import CanvasUserCredential
from app.services import canvas_oauth
from app.services.crypto import decrypt_secret, encrypt_secret

# Per-user lock registry for serializing refresh_access_token calls. Canvas
# refresh tokens are single-use; two concurrent 401s racing to refresh would
# corrupt the stored refresh_token and force re-auth.
_REFRESH_LOCKS: dict[uuid.UUID, asyncio.Lock] = {}
_REFRESH_LOCKS_GUARD = asyncio.Lock()


async def _get_refresh_lock(user_id: uuid.UUID) -> asyncio.Lock:
    async with _REFRESH_LOCKS_GUARD:
        lock = _REFRESH_LOCKS.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            _REFRESH_LOCKS[user_id] = lock
        return lock


async def _discard_refresh_lock(user_id: uuid.UUID) -> None:
    async with _REFRESH_LOCKS_GUARD:
        lock = _REFRESH_LOCKS.get(user_id)
        if lock is not None and not lock.locked():
            _REFRESH_LOCKS.pop(user_id, None)


class CanvasNotConnected(Exception):
    """User has no Canvas credential (or it was marked invalid)."""


class CanvasReauthRequired(Exception):
    """Refresh failed — user must re-run OAuth."""


class CanvasDownloadUrlRejected(Exception):
    """download_file was called with a URL that failed host validation."""


def _validate_download_url(download_url: str, canvas_base_url: str) -> None:
    """Reject download URLs that don't point at the user's Canvas host or a
    narrowly-allowlisted Canvas file-delivery CDN.

    Canvas typically serves file payloads either from the institution's own
    Canvas host or from ``*.instructure.com`` (the Canvas file delivery CDN).
    If the operator has configured ``canvas_allowed_hosts`` we also treat
    each entry as an acceptable suffix match.
    """
    parsed = urlparse(download_url)
    if parsed.scheme != "https":
        raise CanvasDownloadUrlRejected("download URL must be https")
    host = (parsed.hostname or "").lower()
    if not host:
        raise CanvasDownloadUrlRejected("download URL missing hostname")

    base_host = (urlparse(canvas_base_url).hostname or "").lower()
    configured = [
        h.strip().lower()
        for h in (settings.canvas_allowed_hosts or "").split(",")
        if h.strip()
    ]

    candidates = {base_host, "instructure.com"}
    candidates.update(configured)
    candidates.discard("")

    if any(host == c or host.endswith("." + c) for c in candidates):
        return
    raise CanvasDownloadUrlRejected(
        f"download URL host '{host}' is not an allowed Canvas host"
    )


class CanvasClient:
    def __init__(
        self,
        db: AsyncSession,
        credential: CanvasUserCredential,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._db = db
        self._cred = credential
        self._transport = transport

    def _http(self) -> httpx.AsyncClient:
        access = decrypt_secret(self._cred.access_token_encrypted)
        return httpx.AsyncClient(
            base_url=f"{self._cred.canvas_base_url.rstrip('/')}/api/v1",
            headers={"Authorization": f"Bearer {access}"},
            timeout=30.0,
            transport=self._transport,
        )

    async def _refresh(self) -> None:
        user_id = self._cred.user_id
        lock = await _get_refresh_lock(user_id)

        # Snapshot the access token we observed as "failing"; while waiting
        # for the lock another coroutine may have completed a refresh and
        # rotated the credential, in which case we should just use the new
        # one instead of burning another refresh_token.
        stale_access_ciphertext = self._cred.access_token_encrypted

        async with lock:
            try:
                # Re-read the credential row under the lock to pick up a
                # refresh that another request may have just performed.
                await self._db.refresh(self._cred)
                if (
                    self._cred.access_token_encrypted != stale_access_ciphertext
                    and self._cred.status == "active"
                ):
                    # A concurrent refresh already rotated the token. Skip.
                    return

                refresh = decrypt_secret(self._cred.refresh_token_encrypted)
                try:
                    payload = await canvas_oauth.refresh_access_token(refresh)
                except httpx.HTTPError as exc:
                    self._cred.status = "invalid"
                    await self._db.commit()
                    raise CanvasReauthRequired(str(exc)) from exc

                self._cred.access_token_encrypted = encrypt_secret(
                    payload["access_token"]
                )
                if "refresh_token" in payload:
                    self._cred.refresh_token_encrypted = encrypt_secret(
                        payload["refresh_token"]
                    )
                self._cred.access_token_expires_at = datetime.now(
                    timezone.utc
                ) + timedelta(seconds=int(payload.get("expires_in", 3600)))
                self._cred.status = "active"
                await self._db.commit()
            finally:
                # Drop the lock entry if no other waiter holds it, to avoid
                # unbounded growth of _REFRESH_LOCKS across many users.
                await _discard_refresh_lock(user_id)

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        async with self._http() as http:
            response = await http.request(method, path, **kwargs)
        if response.status_code == 401:
            await self._refresh()
            async with self._http() as http:
                response = await http.request(method, path, **kwargs)
        response.raise_for_status()
        return response

    async def _paginate(self, path: str, params: dict | None = None) -> list[dict]:
        """Follow Canvas's Link header pagination."""
        results: list[dict] = []
        url: str | None = path
        next_params = dict(params or {})
        next_params.setdefault("per_page", 50)
        first = True
        while url:
            response = await self._request(
                "GET", url, params=next_params if first else None
            )
            results.extend(response.json())
            link = response.headers.get("Link", "")
            url = _parse_next_link(link)
            first = False
        return results

    # -------------------- high-level methods --------------------

    async def get_user_self(self) -> dict:
        return (await self._request("GET", "/users/self")).json()

    async def list_my_courses(self, enrollment_type: str) -> list[dict]:
        return await self._paginate(
            "/users/self/courses",
            {"enrollment_type": enrollment_type, "state[]": "available"},
        )

    async def get_course(self, canvas_course_id: str) -> dict:
        return (await self._request("GET", f"/courses/{canvas_course_id}")).json()

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
        # Guard against SSRF: Canvas's list_course_files returns attacker-
        # influenceable URLs (file uploads can carry a redirect target in
        # some deployments). Require https + an allowed Canvas host, and
        # disable redirect following so a 3xx can't smuggle us elsewhere.
        _validate_download_url(download_url, self._cred.canvas_base_url)
        async with httpx.AsyncClient(
            timeout=120.0, transport=self._transport, follow_redirects=False
        ) as client:
            response = await client.get(download_url)
            response.raise_for_status()
            return response.content


def _parse_next_link(link_header: str) -> str | None:
    """Parse a Canvas Link header and return the rel="next" URL if present."""
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
    """Load the user's Canvas credential and wrap it in a CanvasClient."""
    cred = (
        await db.execute(
            select(CanvasUserCredential).where(
                CanvasUserCredential.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if cred is None or cred.status != "active":
        raise CanvasNotConnected()
    return CanvasClient(db, cred, transport=transport)
