"""Score router: score-category CRUD (P1) + score record + audited export (P5 B11).

P1 subset: ``GET/POST/PATCH/DELETE /courses/{id}/score-categories``. Categories
are seeded from the pilot profile on course creation (Task 4); this router lets
the teacher view/edit/add/remove/reorder them.

P5 B11 extends this module with the score *record* + audited grade export:

* ``GET /courses/{id}/scores`` (owner-guarded) — every ACTIVE student's
  per-category / per-artifact rollup from graded quiz attempts + score-bearing
  activity responses.
* ``GET /users/me/courses/{id}/scores`` (enrollment-scoped, active-only) — ONLY
  the caller's own record (S059).
* ``GET /courses/{id}/grade-export.csv`` (owner-guarded) — streams a CSV AND
  appends exactly ONE ``grade_exports`` audit row per request (Decision 7); the
  audit row commits BEFORE the response streams.

Owner-guarded routes 403 a student (``require_instructor``) and 404 a non-owner
(``get_owned_course``) so course existence never leaks.
"""
import csv
import io
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._helpers import verify_enrollment
from app.api.deps import (
    get_db,
    get_owned_course,
    require_instructor,
    require_student,
)
from app.models.course import Course
from app.models.score import GradeExport, ScoreCategory
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.score import (
    ScoreCategoryCreate,
    ScoreCategoryResponse,
    ScoreCategoryUpdate,
    StudentScoreRecord,
)
from app.services.scores import build_score_records

router = APIRouter(
    prefix="/courses/{course_id}/score-categories", tags=["setup"]
)

# P5 B11 routers: the score record + audited grade export live on their own
# course-scoped router (``/courses/{id}/scores`` + ``/grade-export.csv``) and a
# student self-scoped router (``/users/me/courses/{id}/scores``).
record_router = APIRouter(prefix="/courses/{course_id}", tags=["scores"])
me_router = APIRouter(prefix="/users/me/courses/{course_id}", tags=["scores"])


async def _get_category(
    db: AsyncSession, course: Course, category_id: uuid.UUID
) -> ScoreCategory:
    result = await db.execute(
        select(ScoreCategory).where(
            ScoreCategory.id == category_id,
            ScoreCategory.course_id == course.id,
            ScoreCategory.deleted_at.is_(None),
        )
    )
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Score category not found"
        )
    return cat


@router.get("", response_model=APIResponse[list[ScoreCategoryResponse]])
async def list_score_categories(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[list[ScoreCategoryResponse]]:
    result = await db.execute(
        select(ScoreCategory)
        .where(
            ScoreCategory.course_id == course.id,
            ScoreCategory.deleted_at.is_(None),
        )
        .order_by(ScoreCategory.sort, ScoreCategory.created_at)
    )
    cats = result.scalars().all()
    return APIResponse(
        success=True,
        data=[ScoreCategoryResponse.model_validate(c) for c in cats],
    )


@router.post("", response_model=APIResponse[ScoreCategoryResponse], status_code=201)
async def create_score_category(
    body: ScoreCategoryCreate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[ScoreCategoryResponse]:
    if body.sort is not None:
        next_sort = body.sort
    else:
        # Append after the current highest sort among live categories.
        max_sort = (
            await db.execute(
                select(func.max(ScoreCategory.sort)).where(
                    ScoreCategory.course_id == course.id,
                    ScoreCategory.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        next_sort = 0 if max_sort is None else max_sort + 1

    cat = ScoreCategory(
        course_id=course.id,
        name=body.name,
        weight=body.weight,
        points_pool=body.points_pool,
        sort=next_sort,
    )
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return APIResponse(success=True, data=ScoreCategoryResponse.model_validate(cat))


@router.patch(
    "/{category_id}", response_model=APIResponse[ScoreCategoryResponse]
)
async def update_score_category(
    category_id: uuid.UUID,
    body: ScoreCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[ScoreCategoryResponse]:
    cat = await _get_category(db, course, category_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(cat, field, value)
    await db.commit()
    await db.refresh(cat)
    return APIResponse(success=True, data=ScoreCategoryResponse.model_validate(cat))


@router.delete("/{category_id}", response_model=APIResponse[None])
async def delete_score_category(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[None]:
    cat = await _get_category(db, course, category_id)
    cat.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return APIResponse(success=True, data=None)


# ----- P5 B11: score record + audited grade export -----


@record_router.get("/scores", response_model=APIResponse[list[StudentScoreRecord]])
async def get_course_scores(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
) -> APIResponse[list[StudentScoreRecord]]:
    """Every active student's per-category / per-artifact rollup (owner-guarded).

    A student → 403 (``require_instructor``); a non-owner instructor → 404
    (``get_owned_course``).
    """
    records = await build_score_records(db, course_id=course.id)
    return APIResponse(
        success=True,
        data=[StudentScoreRecord.model_validate(r) for r in records],
    )


@me_router.get("/scores", response_model=APIResponse[StudentScoreRecord])
async def get_my_scores(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_student),
) -> APIResponse[StudentScoreRecord | None]:
    """The CALLER'S OWN score record only (S059), enrollment-scoped active-only.

    A non-enrolled / pending / rejected student → 403 (``verify_enrollment``).
    Returns only the caller's record — never another student's — because the
    aggregation is narrowed to ``user_ids=[user.id]``.
    """
    await verify_enrollment(db, course_id, user.id)
    records = await build_score_records(
        db, course_id=course_id, user_ids=[user.id]
    )
    record = records[0] if records else None
    data = StudentScoreRecord.model_validate(record) if record else None
    return APIResponse(success=True, data=data)


def _fmt(value: Decimal | None) -> str:
    """Render a Decimal cell as a plain string (empty for ``None``)."""
    return "" if value is None else str(value)


def _build_csv(records: list[dict]) -> str:
    """Flatten score records into a gradebook CSV string.

    Columns: ``student_name``, ``email``, one ``earned_points`` column per
    score-bearing artifact (identical set across all students), then
    ``total_earned`` / ``total_possible``. Built fully in memory so the audit
    row can commit BEFORE streaming and no DB access happens mid-stream.
    """
    # Derive a stable artifact column order from the first record (every student
    # carries the same artifact set — the ``submitted`` flag is what differs).
    artifact_cols: list[tuple[uuid.UUID, str]] = []
    if records:
        for cat in records[0]["categories"]:
            for art in cat["artifacts"]:
                artifact_cols.append(
                    (art["artifact_id"], f"{art['title']} ({art['kind']})")
                )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["student_name", "email"]
        + [header for _, header in artifact_cols]
        + ["total_earned", "total_possible"]
    )
    for rec in records:
        earned_by_artifact: dict[uuid.UUID, Decimal | None] = {}
        total_earned = Decimal("0")
        total_possible = Decimal("0")
        for cat in rec["categories"]:
            for art in cat["artifacts"]:
                earned_by_artifact[art["artifact_id"]] = art["earned_points"]
                total_earned += art["earned_points"] or Decimal("0")
                total_possible += art["points"] or Decimal("0")
        writer.writerow(
            [rec["full_name"] or "", rec["email"]]
            + [_fmt(earned_by_artifact.get(aid)) for aid, _ in artifact_cols]
            + [str(total_earned), str(total_possible)]
        )
    return buffer.getvalue()


@record_router.get("/grade-export.csv")
async def export_grades_csv(
    db: AsyncSession = Depends(get_db),
    course: Course = Depends(get_owned_course),
    user: User = Depends(require_instructor),
) -> StreamingResponse:
    """Stream an audited gradebook CSV (owner-guarded, Decision 7).

    Appends exactly ONE ``grade_exports`` audit row (``exported_by``, ``format``,
    ``filters``, ``row_count``) and COMMITS it BEFORE the CSV streams, inside the
    same request — the append-only audit is durable even if the client aborts
    the download. The CSV body is materialized in memory first, so the streaming
    generator never touches the DB session.
    """
    records = await build_score_records(db, course_id=course.id)
    csv_text = _build_csv(records)

    audit = GradeExport(
        course_id=course.id,
        exported_by=user.id,
        format="csv",
        filters={},
        row_count=len(records),
    )
    db.add(audit)
    await db.commit()

    filename = f"grades-{course.id}.csv"
    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
