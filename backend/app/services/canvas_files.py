"""Canvas → Meli file import pipeline."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, Task
from app.services import storage
from app.services.canvas_client import CanvasClient

logger = logging.getLogger(__name__)


# Mirrors `app.api.documents.ALLOWED_TYPES` — kept local so the import path is
# canvas-only (avoids pulling the upload router into background services).
_CONTENT_TYPE_TO_FILE_TYPE: dict[str, str] = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "video/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
}


def _derive_file_type(content_type: str, filename: str) -> str:
    if content_type in _CONTENT_TYPE_TO_FILE_TYPE:
        return _CONTENT_TYPE_TO_FILE_TYPE[content_type]
    # Fallback: extension. Strip leading dot, lowercase, capped at 20 chars
    # because the column is VARCHAR(20).
    ext = ""
    if "." in filename:
        ext = filename.rsplit(".", 1)[1].lower()
    if ext:
        return ext[:20]
    # Best-effort prefix from the content-type, e.g. "application/pdf" → "application".
    if "/" in content_type:
        return content_type.split("/", 1)[0][:20] or "bin"
    return "bin"


@dataclass
class ImportResult:
    imported: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)


async def import_canvas_files(
    db: AsyncSession,
    client: CanvasClient,
    course_id: uuid.UUID,
    file_ids: list[str],
    *,
    uploaded_by: uuid.UUID,
) -> ImportResult:
    """Download each Canvas file, persist a Document row, and enqueue processing.

    Already-imported files (matched by ``Document.canvas_file_id`` within the
    course) are reported under ``skipped``. Per-file errors are isolated so a
    single bad file does not abort the batch.
    """
    file_ids = [str(fid) for fid in file_ids]

    existing = (
        await db.execute(
            select(Document.canvas_file_id).where(
                Document.course_id == course_id,
                Document.canvas_file_id.in_(file_ids),
            )
        )
    ).scalars().all()
    existing_set = {str(e) for e in existing}

    result = ImportResult(skipped=list(existing_set))

    for file_id in file_ids:
        if file_id in existing_set:
            continue
        try:
            meta = await client.get_file(file_id)
            content_type = (
                meta.get("content-type") or meta.get("content_type") or ""
            ).lower()
            display_name = meta.get("display_name") or f"canvas-{file_id}"
            download_url = meta.get("url")
            if not download_url:
                raise ValueError("missing download url in Canvas metadata")

            body = await client.download_file(download_url)
            doc_id = uuid.uuid4()
            r2_key = storage.build_r2_key(course_id, doc_id, display_name)
            # boto3 is sync — keep the event loop free.
            await asyncio.to_thread(
                storage.upload_file, r2_key, body, content_type or "application/octet-stream"
            )

            doc = Document(
                id=doc_id,
                course_id=course_id,
                uploaded_by=uploaded_by,
                filename=display_name,
                file_type=_derive_file_type(content_type, display_name),
                file_size=meta.get("size") or len(body),
                r2_key=r2_key,
                status="pending",
                canvas_file_id=file_id,
                canvas_file_etag=str(meta.get("updated_at") or "") or None,
            )
            db.add(doc)
            await db.flush()

            db.add(
                Task(
                    task_type="process_document",
                    payload={"document_id": str(doc.id)},
                    status="pending",
                )
            )
            result.imported.append(file_id)
        except Exception as exc:  # noqa: BLE001 — per-file isolation
            logger.exception("Canvas import failed for file %s", file_id)
            await db.rollback()
            result.errors.append({"file_id": file_id, "error": str(exc)})
            continue

    await db.commit()
    return result
