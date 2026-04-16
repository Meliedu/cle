"""Per-user Canvas REST client with refresh-on-401 and Link pagination."""

from __future__ import annotations

import contextlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import CanvasUserCredential
from app.services import canvas_oauth
from app.services.crypto import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def _acquire_refresh_lock(db: AsyncSession, user_id: uuid.UUID):
    """Postgres advisory lock scoped to ``user_id``.

    Serialises Canvas refresh-token rotations across every worker sharing
    this database — Canvas refresh tokens are single-use, so two concurrent
    401 retries racing to refresh would corrupt the stored refresh_token and
    force the user to re-auth. A prior in-process ``asyncio.Lock`` only
    covered one uvicorn worker; this advisory lock covers the whole fleet.

    ``hashtext()`` maps the UUID string to a 32-bit int; collisions are
    harmless — they only cause unrelated users to briefly queue behind each
    other during a refresh window.
    """
    key_row = await db.execute(
        sa.text("SELECT hashtext(:k)::bigint AS k").bindparams(k=str(user_id))
    )
    lock_key = key_row.scalar_one()
    await db.execute(sa.text("SELECT pg_advisory_lock(:k)").bindparams(k=lock_key))
    try:
        yield
    finally:
        await db.execute(
            sa.text("SELECT pg_advisory_unlock(:k)").bindparams(k=lock_key)
        )


# Allowlist of Canvas-operated hosts that may serve file payloads in
# addition to the institution's own Canvas host. Canvas's public file
# delivery CDN is ``files.instructure.com``; signed S3 URLs surface via
# ``canvas-*.s3.*.amazonaws.com``. Anything broader (e.g. bare
# ``instructure.com``) is too permissive for SSRF defense.
_CANVAS_DOWNLOAD_ALLOWLIST: tuple[str, ...] = (
    "files.instructure.com",
)


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
    Canvas host or from ``files.instructure.com`` (the Canvas file delivery
    CDN). If the operator has configured ``canvas_allowed_hosts`` we also
    treat each entry as an acceptable suffix match (e.g. to permit signed
    S3 URLs from ``canvas-*.s3.*.amazonaws.com`` in deployments that use
    them).
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

    candidates = {base_host, *_CANVAS_DOWNLOAD_ALLOWLIST}
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
        # Snapshot the access token we observed as "failing"; while waiting
        # for the advisory lock another worker may have completed a refresh
        # and rotated the credential, in which case we should just adopt the
        # new one instead of burning another single-use refresh_token.
        stale_access_ciphertext = self._cred.access_token_encrypted

        async with _acquire_refresh_lock(self._db, self._cred.user_id):
            # Re-read the credential row under the lock to pick up a refresh
            # that another worker may have just performed. Use a fresh SELECT
            # rather than ``Session.refresh()`` so we see committed writes
            # from other backend connections (other workers).
            current = (
                await self._db.execute(
                    select(CanvasUserCredential).where(
                        CanvasUserCredential.user_id == self._cred.user_id
                    )
                )
            ).scalar_one()
            if (
                current.access_token_encrypted != stale_access_ciphertext
                and current.status == "active"
            ):
                # A concurrent refresh already rotated the token — adopt it.
                self._cred = current
                return

            self._cred = current
            refresh = decrypt_secret(self._cred.refresh_token_encrypted)
            try:
                payload = await canvas_oauth.refresh_access_token(refresh)
            except httpx.HTTPError as exc:
                self._cred.status = "invalid"
                await self._db.commit()
                # httpx HTTPError stringifies with the target URL (query
                # params included), which can leak internal infrastructure
                # details. Surface a generic message; preserve the chain
                # via ``from exc`` for logging/tooling.
                raise CanvasReauthRequired("token refresh failed") from exc

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

    async def revoke_token(self) -> None:
        """Best-effort call to Canvas ``DELETE /login/oauth2/token``.

        Canvas refresh tokens are long-lived and reusable; revoking at
        disconnect prevents later reuse even if the encrypted credential
        row is later exfiltrated. Never raises — a failure here must not
        block the local credential delete.

        ``/login/oauth2/token`` lives outside the ``/api/v1`` namespace that
        ``_http()`` is scoped to, so we issue the call against the institution
        root URL directly.
        """
        try:
            access = decrypt_secret(self._cred.access_token_encrypted)
            revoke_url = (
                f"{self._cred.canvas_base_url.rstrip('/')}/login/oauth2/token"
            )
            async with httpx.AsyncClient(
                headers={"Authorization": f"Bearer {access}"},
                timeout=30.0,
                transport=self._transport,
            ) as http:
                await http.delete(revoke_url)
        except Exception:
            logger.exception(
                "Canvas token revoke failed — proceeding with local delete"
            )

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
