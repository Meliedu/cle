import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_instructor
from app.config import settings
from app.models.course import Enrollment
from app.models.document import Document
from app.models.task import Task
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.document import DocumentResponse
from app.services.storage import build_r2_key, upload_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/courses/{course_id}/documents", tags=["documents"])

ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "video/mp4": "mp4",
    "audio/mpeg": "mp3",
}


@router.post("/upload", response_model=APIResponse[DocumentResponse], status_code=201)
async def upload_document(
    course_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == course_id,
            Enrollment.user_id == user.id,
            Enrollment.role == "instructor",
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not course instructor")

    content_type = file.content_type or ""
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type {content_type} not allowed. Allowed: {', '.join(ALLOWED_TYPES.values())}",
        )

    file_data = await file.read()
    file_size = len(file_data)

    max_size = settings.max_upload_size_mb * 1024 * 1024
    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds {settings.max_upload_size_mb}MB limit",
        )

    document_id = uuid.uuid4()
    r2_key = build_r2_key(course_id, document_id, file.filename or "unnamed")

    # Persist the DB row first. If the R2 upload later fails, we have a
    # traceable pending/failed row to reconcile rather than an orphaned R2
    # object with no database record.
    document = Document(
        id=document_id,
        course_id=course_id,
        uploaded_by=user.id,
        filename=file.filename or "unnamed",
        file_type=ALLOWED_TYPES[content_type],
        file_size=file_size,
        r2_key=r2_key,
        status="pending",
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    # Upload to R2 off the event loop (boto3 is synchronous).
    try:
        await asyncio.to_thread(upload_file, r2_key, file_data, content_type)
    except Exception:
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
    enrollment = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == course_id, Enrollment.user_id == user.id
        )
    )
    if not enrollment.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enrolled")

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
    await db.commit()
    return APIResponse(success=True, data=None)
