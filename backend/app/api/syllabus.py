import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_instructor
from app.models import Course, Document, SyllabusImport, Task, User
from app.schemas.common import APIResponse
from app.schemas.curriculum import (
    SyllabusImportApplyRequest,
    SyllabusImportResponse,
    SyllabusImportTriggerRequest,
)
from app.services.syllabus import apply_syllabus_payload

router = APIRouter(prefix="/courses/{course_id}/syllabus", tags=["curriculum"])


async def _own_course(course_id: uuid.UUID, user: User, db: AsyncSession) -> Course:
    res = await db.execute(
        select(Course).where(
            Course.id == course_id,
            Course.instructor_id == user.id,
            Course.deleted_at.is_(None),
        )
    )
    c = res.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Course not found")
    return c


@router.post(
    "/imports",
    response_model=APIResponse[SyllabusImportResponse],
    status_code=202,
)
async def trigger_import(
    course_id: uuid.UUID,
    body: SyllabusImportTriggerRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _own_course(course_id, user, db)
    doc = (
        await db.execute(
            select(Document).where(
                Document.id == body.document_id,
                Document.course_id == course_id,
                Document.kind == "syllabus",
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="syllabus document not found")

    imp = SyllabusImport(
        course_id=course_id,
        document_id=doc.id,
        raw_text="",
        parsed_payload={},
        status="pending",
        created_by=user.id,
    )
    db.add(imp)
    await db.flush()
    db.add(
        Task(
            task_type="parse_syllabus",
            payload={"syllabus_import_id": str(imp.id), "document_id": str(doc.id)},
            status="pending",
            attempts=0,
            max_attempts=3,
        )
    )
    await db.commit()
    await db.refresh(imp)
    return APIResponse(success=True, data=SyllabusImportResponse.model_validate(imp))


@router.get("/imports", response_model=APIResponse[list[SyllabusImportResponse]])
async def list_imports(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _own_course(course_id, user, db)
    rows = (
        await db.execute(
            select(SyllabusImport)
            .where(SyllabusImport.course_id == course_id)
            .order_by(SyllabusImport.created_at.desc())
        )
    ).scalars().all()
    return APIResponse(
        success=True,
        data=[SyllabusImportResponse.model_validate(r) for r in rows],
    )


@router.post(
    "/imports/{import_id}/apply",
    response_model=APIResponse[SyllabusImportResponse],
)
async def apply_import(
    course_id: uuid.UUID,
    import_id: uuid.UUID,
    body: SyllabusImportApplyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _own_course(course_id, user, db)
    imp = (
        await db.execute(
            select(SyllabusImport).where(
                SyllabusImport.id == import_id,
                SyllabusImport.course_id == course_id,
            )
        )
    ).scalar_one_or_none()
    if not imp:
        raise HTTPException(status_code=404, detail="import not found")
    if imp.status != "parsed":
        raise HTTPException(
            status_code=409,
            detail=f"only 'parsed' imports can be applied (current: {imp.status})",
        )
    await apply_syllabus_payload(
        db,
        course_id=course_id,
        payload=body.parsed_payload,
        applied_by=user.id,
    )
    imp.parsed_payload = body.parsed_payload
    imp.status = "applied"
    imp.applied_at = datetime.now(timezone.utc)
    imp.applied_by = user.id

    # supersede earlier applied imports for the same course
    earlier = (
        await db.execute(
            select(SyllabusImport).where(
                SyllabusImport.course_id == course_id,
                SyllabusImport.id != imp.id,
                SyllabusImport.status == "applied",
            )
        )
    ).scalars().all()
    for e in earlier:
        e.status = "superseded"

    await db.commit()
    await db.refresh(imp)
    return APIResponse(success=True, data=SyllabusImportResponse.model_validate(imp))
