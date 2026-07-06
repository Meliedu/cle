"""``analyze_course_setup`` job: course map + missing-source detection (T019/T028).

Read-only aggregation — never mutates course state. The setup router persists
the completion flag; this handler just returns the map so ``GET .../setup/analysis``
can render the review screen (T019) and the missing-source error state (T028).

The result dict is returned to the worker, which stores it under
``tasks.payload['result']`` (see ``worker.complete_task``); the setup router reads
it back by querying the latest completed ``analyze_course_setup`` Task via
``Task.payload.op("->>")("course_id")``.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ConceptTag, Document, LearningObjective
from app.models.curriculum import CourseMeeting, SyllabusImport


async def run_analyze_course_setup(
    db: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    course_id = uuid.UUID(payload["course_id"])

    doc_count = (
        await db.execute(
            select(func.count())
            .select_from(Document)
            .where(
                Document.course_id == course_id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one()

    meetings = (
        await db.execute(
            select(CourseMeeting).where(
                CourseMeeting.course_id == course_id,
                CourseMeeting.deleted_at.is_(None),
            )
        )
    ).scalars().all()

    objectives = (
        await db.execute(
            select(LearningObjective).where(
                LearningObjective.course_id == course_id,
                LearningObjective.deleted_at.is_(None),
            )
        )
    ).scalars().all()

    # ``syllabus_imports`` has no soft-delete column; an *applied* import is the
    # syllabus-grounding source the wizard's "syllabus" step marks complete.
    syllabus_applied = bool(
        (
            await db.execute(
                select(func.count())
                .select_from(SyllabusImport)
                .where(
                    SyllabusImport.course_id == course_id,
                    SyllabusImport.status == "applied",
                )
            )
        ).scalar_one()
    )

    missing_sources: list[dict[str, Any]] = []

    # Objective is a "missing source" when nothing tags it as covered — i.e.
    # no concept_tags row anchors an objective the checkpoint generator could
    # ground on, and there is no course material at all. (P1 heuristic; P3
    # tightens to chunk-level coverage.)
    for obj in objectives:
        tagged = (
            await db.execute(
                select(func.count())
                .select_from(ConceptTag)
                .where(
                    ConceptTag.target_kind == "objective",
                    ConceptTag.target_id == obj.id,
                )
            )
        ).scalar_one()
        if tagged == 0 and doc_count == 0:
            missing_sources.append(
                {
                    "kind": "objective_without_source",
                    "id": str(obj.id),
                    "label": obj.statement[:120],
                }
            )

    for m in meetings:
        # A scheduled session with no materials and no topic summary can't
        # anchor checkpoint generation → flag for the analyzer review (T019).
        if doc_count == 0 and not m.topic_summary:
            missing_sources.append(
                {
                    "kind": "session_without_material",
                    "id": str(m.id),
                    "label": m.title or f"Session {m.meeting_index}",
                }
            )

    return {
        "course_id": str(course_id),
        "counts": {
            "documents": int(doc_count),
            "meetings": len(meetings),
            "objectives": len(objectives),
        },
        "syllabus_applied": syllabus_applied,
        "missing_sources": missing_sources,
        "has_missing_sources": bool(missing_sources),
    }
