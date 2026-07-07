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
from app.models.curriculum import CourseMeeting
from app.models.document import Document
from app.models.task import Task
from app.models.user import User
from app.models.work_item import WorkItem
from app.schemas.common import APIResponse
from app.schemas.document import (
    DocumentAssignRequest,
    DocumentResponse,
    MaterialGroup,
    MaterialPreview,
    MaterialsLibrary,
)
from app.services.storage import (
    build_r2_key,
    delete_file_safe,
    generate_presigned_url,
    sanitize_filename,
    upload_file,
)
from app.services.work_items import remove_work_item, upsert_work_item

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/courses/{course_id}/documents", tags=["documents"])

# Second router for the grouped materials library, mounted OUTSIDE the
# ``/documents`` prefix (spec §4.6 / Decision 6: ``GET /courses/{id}/materials``).
materials_router = APIRouter(prefix="/courses/{course_id}", tags=["documents"])

# Short-lived signed preview URL — never stream raw bytes through the API.
PREVIEW_TTL_SECONDS = 300

# Sessions whose materials a student may see/preview (student visibility axis).
# ``locked``/``archived`` sessions are never student-visible.
_STUDENT_VISIBLE_RELEASE_STATES = frozenset({"released", "completed"})

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


# ---------------------------------------------------------------------------
# Materials library (P4 B8): assign-to-session, session folders, signed preview
# ---------------------------------------------------------------------------


async def _is_course_instructor(
    db: AsyncSession, course_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """True if the user holds an instructor-role enrollment in the course."""
    result = await db.execute(
        select(Enrollment.id).where(
            Enrollment.course_id == course_id,
            Enrollment.user_id == user_id,
            Enrollment.role == "instructor",
        )
    )
    return result.scalar_one_or_none() is not None


async def _sync_material_work_item(
    db: AsyncSession,
    *,
    document: Document,
    meeting: CourseMeeting | None,
    user: User,
) -> None:
    """Keep the ``material`` work_item in lock-step with the assignment (Decision 6).

    A document assigned to a ``released`` session surfaces on the student
    checklist/calendar as an idempotent ``material`` work_item; anything else
    (unassigned, or a locked/archived session) must NOT. The unique index on
    ``(course_id, source_kind, source_id)`` means a prior soft-deleted row still
    occupies the key, so re-assigning reactivates it rather than double-inserting.
    The caller owns the commit.
    """
    existing = (
        await db.execute(
            select(WorkItem).where(
                WorkItem.course_id == document.course_id,
                WorkItem.source_kind == "material",
                WorkItem.source_id == document.id,
            )
        )
    ).scalar_one_or_none()

    should_surface = meeting is not None and meeting.release_state == "released"

    if should_surface:
        if existing is None:
            await upsert_work_item(
                db,
                course_id=document.course_id,
                source_kind="material",
                source_id=document.id,
                title=document.filename,
                required=False,
                score_bearing=False,
                due_at=None,
                close_at=None,
                created_by=user.id,
            )
        elif existing.deleted_at is not None:
            existing.deleted_at = None
            db.add(existing)
    elif existing is not None and existing.deleted_at is None:
        await remove_work_item(db, existing)


@router.patch("/{document_id}", response_model=APIResponse[DocumentResponse])
async def assign_document(
    course_id: uuid.UUID,
    document_id: uuid.UUID,
    body: DocumentAssignRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    """Assign a document to a session or unassign it (owner-guarded, T056).

    Setting ``meeting_id`` to a session in THIS course assigns it; ``null``
    unassigns. A meeting belonging to another course is a 404 (cross-course
    assignment is the primary leak vector — a document can only ever be attached
    to a meeting in its own course). Assigning to a ``released`` session creates
    an idempotent ``material`` work_item; unassigning (or a locked/archived
    session) soft-removes it.
    """
    await _require_course_instructor(db, course_id, user)

    doc = (
        await db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.course_id == course_id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    meeting: CourseMeeting | None = None
    if body.meeting_id is not None:
        meeting = (
            await db.execute(
                select(CourseMeeting).where(
                    CourseMeeting.id == body.meeting_id,
                    CourseMeeting.course_id == course_id,
                    CourseMeeting.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if meeting is None:
            # Missing OR foreign (belongs to another course) — 404 either way so
            # cross-course meeting existence is never leaked.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "MEETING_NOT_FOUND", "message": "Meeting not found in this course"},
            )

    doc.meeting_id = body.meeting_id
    await _sync_material_work_item(db, document=doc, meeting=meeting, user=user)
    await db.commit()
    await db.refresh(doc)
    return APIResponse(success=True, data=DocumentResponse.model_validate(doc))


@router.get("/{document_id}/preview", response_model=APIResponse[MaterialPreview])
async def preview_document(
    course_id: uuid.UUID,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return a short-lived signed R2 URL for a document (never raw bytes).

    Access: the course owner (instructor enrollment) OR an actively-enrolled
    student whose target document sits on a student-visible (``released``/
    ``completed``) session. A student on a non-released/unassigned document, or a
    non-enrolled caller, is refused.
    """
    doc = (
        await db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.course_id == course_id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    if not await _is_course_instructor(db, course_id, user.id):
        # Student path: must be actively enrolled AND the document must live on a
        # student-visible session.
        await verify_enrollment(db, course_id, user.id)
        release_state = None
        if doc.meeting_id is not None:
            release_state = (
                await db.execute(
                    select(CourseMeeting.release_state).where(
                        CourseMeeting.id == doc.meeting_id,
                        CourseMeeting.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
        if release_state not in _STUDENT_VISIBLE_RELEASE_STATES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "MATERIAL_NOT_RELEASED",
                    "message": "This material is not available yet",
                },
            )

    url = generate_presigned_url(doc.r2_key, expiration=PREVIEW_TTL_SECONDS)
    return APIResponse(
        success=True,
        data=MaterialPreview(
            url=url,
            expires_in=PREVIEW_TTL_SECONDS,
            filename=doc.filename,
            file_type=doc.file_type,
        ),
    )


@materials_router.get("/materials", response_model=APIResponse[MaterialsLibrary])
async def list_materials(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Documents grouped into session folders + an unassigned bucket (Decision 6).

    Owner view (instructor enrollment): every non-deleted session folder plus the
    ``unassigned`` bucket. Student view (actively enrolled): only student-visible
    (``released``/``completed``) session folders — no unassigned bucket and no
    locked/archived sessions leak.
    """
    is_owner = await _is_course_instructor(db, course_id, user.id)
    if not is_owner:
        await verify_enrollment(db, course_id, user.id)

    meetings = (
        await db.execute(
            select(CourseMeeting)
            .where(
                CourseMeeting.course_id == course_id,
                CourseMeeting.deleted_at.is_(None),
            )
            .order_by(CourseMeeting.meeting_index)
        )
    ).scalars().all()
    if not is_owner:
        meetings = [
            m for m in meetings
            if m.release_state in _STUDENT_VISIBLE_RELEASE_STATES
        ]
    visible_meeting_ids = {m.id for m in meetings}

    docs = (
        await db.execute(
            select(Document)
            .where(
                Document.course_id == course_id,
                Document.deleted_at.is_(None),
            )
            .order_by(Document.created_at)
        )
    ).scalars().all()

    docs_by_meeting: dict[uuid.UUID, list[DocumentResponse]] = {
        mid: [] for mid in visible_meeting_ids
    }
    unassigned: list[DocumentResponse] = []
    for d in docs:
        payload = DocumentResponse.model_validate(d)
        if d.meeting_id is None:
            # Students never see the unassigned bucket.
            if is_owner:
                unassigned.append(payload)
        elif d.meeting_id in docs_by_meeting:
            docs_by_meeting[d.meeting_id].append(payload)
        # Docs on a non-visible session (student view) are silently dropped.

    sessions = [
        MaterialGroup(
            meeting_id=m.id,
            meeting_index=m.meeting_index,
            title=m.title,
            release_state=m.release_state,
            documents=docs_by_meeting.get(m.id, []),
        )
        for m in meetings
    ]
    return APIResponse(
        success=True,
        data=MaterialsLibrary(sessions=sessions, unassigned=unassigned),
    )
