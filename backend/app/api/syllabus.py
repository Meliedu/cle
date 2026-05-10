import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.api.deps import get_db, get_owned_course
from app.models import Document, SyllabusImport, Task
from app.models.course import Course
from app.schemas.common import APIResponse
from app.schemas.curriculum import (
    SyllabusImportApplyRequest,
    SyllabusImportResponse,
    SyllabusImportTriggerRequest,
)
from app.services.syllabus import apply_syllabus_payload

router = APIRouter(prefix="/courses/{course_id}/syllabus", tags=["curriculum"])


@router.post(
    "/imports",
    response_model=APIResponse[SyllabusImportResponse],
    status_code=202,
)
async def trigger_import(
    body: SyllabusImportTriggerRequest,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
):
    doc = (
        await db.execute(
            select(Document).where(
                Document.id == body.document_id,
                Document.course_id == course.id,
                Document.kind == "syllabus",
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="syllabus document not found")

    imp = SyllabusImport(
        course_id=course.id,
        document_id=doc.id,
        raw_text="",
        parsed_payload={},
        status="pending",
        created_by=course.instructor_id,
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
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
):
    rows = (
        await db.execute(
            select(SyllabusImport)
            .where(SyllabusImport.course_id == course.id)
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
    import_id: uuid.UUID,
    body: SyllabusImportApplyRequest,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
):
    # Atomic state transition: parsed → applying. The conditional UPDATE
    # is the actual lock — only one concurrent request flips the row.
    # Without it, two requests both pass a SELECT status='parsed' check
    # and both run apply_syllabus_payload, duplicating curriculum because
    # the applier dedupes by select-then-insert with no DB-level uniqueness.
    transitioned = (
        await db.execute(
            update(SyllabusImport)
            .where(
                SyllabusImport.id == import_id,
                SyllabusImport.course_id == course.id,
                SyllabusImport.status == "parsed",
            )
            .values(status="applying")
            .returning(SyllabusImport.id)
        )
    ).scalar_one_or_none()
    if transitioned is None:
        # Either the row doesn't exist, doesn't belong to this course, or
        # isn't in 'parsed' state. Probe to give the right error code.
        existing = (
            await db.execute(
                select(SyllabusImport.status).where(
                    SyllabusImport.id == import_id,
                    SyllabusImport.course_id == course.id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            raise HTTPException(status_code=404, detail="import not found")
        raise HTTPException(
            status_code=409,
            detail=f"only 'parsed' imports can be applied (current: {existing})",
        )
    # Commit the transition immediately so concurrent requests see
    # 'applying' and bail at the conditional UPDATE.
    await db.commit()

    try:
        await apply_syllabus_payload(
            db,
            course_id=course.id,
            payload=body.parsed_payload,
            applied_by=course.instructor_id,
        )
    except Exception:
        # Roll back to 'failed' so the import doesn't get stuck in
        # 'applying' forever and so the UI can surface the failure.
        logger.exception("apply_syllabus_payload failed for %s", import_id)
        await db.rollback()
        await db.execute(
            update(SyllabusImport)
            .where(SyllabusImport.id == import_id)
            .values(status="failed")
        )
        await db.commit()
        raise HTTPException(
            status_code=500, detail="syllabus apply failed"
        )

    now = datetime.now(timezone.utc)
    await db.execute(
        update(SyllabusImport)
        .where(SyllabusImport.id == import_id)
        .values(
            parsed_payload=body.parsed_payload,
            status="applied",
            applied_at=now,
            applied_by=course.instructor_id,
        )
    )
    # supersede earlier applied imports for the same course
    await db.execute(
        update(SyllabusImport)
        .where(
            SyllabusImport.course_id == course.id,
            SyllabusImport.id != import_id,
            SyllabusImport.status == "applied",
        )
        .values(status="superseded")
    )
    await db.commit()

    imp = (
        await db.execute(
            select(SyllabusImport).where(SyllabusImport.id == import_id)
        )
    ).scalar_one()
    return APIResponse(success=True, data=SyllabusImportResponse.model_validate(imp))
