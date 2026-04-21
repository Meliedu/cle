import asyncio
import logging
import os
import re
import uuid

import boto3
from botocore.config import Config

from app.config import settings

logger = logging.getLogger(__name__)

_s3_client = None

_FILENAME_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_FILENAME_LEN = 200


def sanitize_filename(filename: str) -> str:
    """Normalize an uploaded filename for safe storage and display.

    Strips any path components, collapses disallowed characters to
    underscores, trims leading/trailing punctuation, and caps the length.
    The result is safe to persist to the database and to render in admin
    UIs without XSS risk.
    """
    base = os.path.basename(filename.replace("\\", "/")).strip()
    if not base or base in {".", ".."}:
        return "unnamed"
    cleaned = _FILENAME_SANITIZE_RE.sub("_", base)
    cleaned = re.sub(r"_+", "_", cleaned).strip("._") or "unnamed"
    return cleaned[:_MAX_FILENAME_LEN]


# Backwards-compatible alias. Prefer ``sanitize_filename`` for new call sites.
_sanitize_filename = sanitize_filename


def get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint_url,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )
    return _s3_client


def build_r2_key(course_id: uuid.UUID, document_id: uuid.UUID, filename: str) -> str:
    safe_name = _sanitize_filename(filename)
    return f"courses/{course_id}/documents/{document_id}/{safe_name}"


def upload_file(r2_key: str, file_data: bytes, content_type: str) -> None:
    client = get_s3_client()
    client.put_object(
        Bucket=settings.r2_bucket_name,
        Key=r2_key,
        Body=file_data,
        ContentType=content_type,
    )


def download_file(r2_key: str) -> bytes:
    client = get_s3_client()
    response = client.get_object(Bucket=settings.r2_bucket_name, Key=r2_key)
    return response["Body"].read()


def delete_file(r2_key: str) -> None:
    client = get_s3_client()
    client.delete_object(Bucket=settings.r2_bucket_name, Key=r2_key)


async def delete_file_safe(r2_key: str | None) -> None:
    """Best-effort R2 delete used by terminal document cleanup paths.

    Runs boto3 off the event loop and swallows any error — a missing key or
    a transient R2 blip must not fail the HTTP request / worker transaction
    that's tombstoning the document. Logs failures at WARNING so orphans
    are still discoverable.
    """
    if not r2_key:
        return
    try:
        await asyncio.to_thread(delete_file, r2_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("R2 delete failed for %s: %s", r2_key, exc)


def generate_presigned_url(r2_key: str, expiration: int = 3600) -> str:
    client = get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.r2_bucket_name, "Key": r2_key},
        ExpiresIn=expiration,
    )
