import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._helpers import verify_enrollment
from app.api.deps import get_current_user, get_db, require_instructor
from app.config import settings
from app.models.course import Enrollment
from app.models.document import Document
from app.models.task import Task
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.document import DocumentResponse
from app.services.storage import (
    build_r2_key,
    delete_file_safe,
    sanitize_filename,
    upload_file,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/courses/{course_id}/documents", tags=["documents"])

ALLOWED_DOCUMENT_KINDS = {"lecture", "syllabus", "reading", "reference", "other"}

ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "video/mp4": "mp4",
    "audio/mpeg": "mp3",
}

# Magic-byte signatures keyed by declared MIME. Each entry is a list of
# acceptable prefixes — some formats have multiple legitimate variants.
# mp4 is checked via the ftyp atom at offset 4.
MAGIC_BYTES: dict[str, list[bytes]] = {
    "application/pdf": [b"%PDF-"],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"],
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": [b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"],
    "audio/mpeg": [b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"],
}


def _matches_magic(content_type: str, file_data: bytes) -> bool:
    if content_type == "video/mp4":
        # mp4: "....ftyp" — ftyp atom at byte offset 4
        return len(file_data) >= 12 and file_data[4:8] == b"ftyp"
    signatures = MAGIC_BYTES.get(content_type, [])
    return any(file_data.startswith(sig) for sig in signatures)


async def _require_course_instructor(
    db: AsyncSession, course_id: uuid.UUID, user: User
) -> None:
    result = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == course_id,
            Enrollment.user_id == user.id,
            Enrollment.role == "instructor",
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not course instructor")


@router.post("/upload", response_model=APIResponse[DocumentResponse], status_code=201)
async def upload_document(
    course_id: uuid.UUID,
    file: UploadFile,
    kind: str = Form("lecture"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    if kind not in ALLOWED_DOCUMENT_KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid document kind '{kind}'. Allowed: {', '.join(sorted(ALLOWED_DOCUMENT_KINDS))}",
        )

    await _require_course_instructor(db, course_id, user)

    content_type = file.content_type or ""
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type {content_type} not allowed. Allowed: {', '.join(ALLOWED_TYPES.values())}",
        )

    # Stream the upload in 1 MiB chunks, tracking total size as we go.
    # This caps memory to ~max_upload_size_mb + 1 MiB instead of buffering
    # whatever the client chose to send (which could be orders of magnitude
    # larger than our limit) before we reject it.
    max_size = settings.max_upload_size_mb * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds {settings.max_upload_size_mb}MB limit",
            )
        chunks.append(chunk)
    file_data = b"".join(chunks)
    file_size = total

    if not _matches_magic(content_type, file_data):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content does not match declared type",
        )

    document_id = uuid.uuid4()
    # Sanitize once and reuse everywhere so the DB row, R2 key, and any
    # admin UI rendering all see the same safe value. Prevents stored XSS
    # from attacker-controlled filenames.
    safe_name = sanitize_filename(file.filename or "unnamed")
    r2_key = build_r2_key(course_id, document_id, safe_name)

    # Persist DB row first so a failed R2 write leaves only a pending orphan
    # that can be reconciled, rather than an unreferenced R2 object.
    document = Document(
        id=document_id,
        course_id=course_id,
        uploaded_by=user.id,
        filename=safe_name,
        file_type=ALLOWED_TYPES[content_type],
        file_size=file_size,
        r2_key=r2_key,
        status="pending",
        kind=kind,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    # Upload to R2 off the event loop (boto3 is sync)
    try:
        await asyncio.to_thread(upload_file, r2_key, file_data, content_type)
    except Exception:
        # R2 failed — tombstone the DB row so it doesn't sit forever
        document.status = "failed"
        await db.commit()
        logger.exception("R2 upload failed for document %s", document_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="File storage upload failed",
        )

    task = Task(
        task_type="process_document",
        payload={"document_id": str(document_id)},
    )
    db.add(task)
    await db.commit()

    return APIResponse(success=True, data=DocumentResponse.model_validate(document))


@router.get("", response_model=APIResponse[list[DocumentResponse]])
async def list_documents(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await verify_enrollment(db, course_id, user.id)

    result = await db.execute(
        select(Document).where(
            Document.course_id == course_id, Document.deleted_at.is_(None)
        )
    )
    docs = result.scalars().all()
    return APIResponse(
        success=True,
        data=[DocumentResponse.model_validate(d) for d in docs],
    )


@router.delete("/{document_id}", response_model=APIResponse[None])
async def delete_document(
    course_id: uuid.UUID,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _require_course_instructor(db, course_id, user)

    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.course_id == course_id,
            Document.deleted_at.is_(None),
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    doc.deleted_at = datetime.now(timezone.utc)
    r2_key = doc.r2_key  # capture before commit in case the row is evicted
    await db.commit()
    # Reclaim the R2 object so soft-deleted docs don't accumulate storage.
    # Best-effort: a missing/already-gone key must not fail this request.
    await delete_file_safe(r2_key)
    return APIResponse(success=True, data=None)
