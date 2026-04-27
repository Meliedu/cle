import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

from app.api._helpers import verify_enrollment as _verify_enrollment
from app.api.deps import get_current_user, get_db, require_instructor
from app.models.pronunciation import (
    PronunciationFolder,
    PronunciationItem,
    PronunciationSet,
)
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.pronunciation import (
    PronunciationFolderCreate,
    PronunciationFolderMove,
    PronunciationFolderRename,
    PronunciationFolderResponse,
    PronunciationItemCreate,
    PronunciationItemResponse,
    PronunciationItemUpdate,
    PronunciationSetDetailResponse,
    PronunciationSetMove,
    PronunciationSetResponse,
    PronunciationSetUpdate,
)

router = APIRouter(tags=["pronunciation"])


# ---------------------------------------------------------------------------
# Pronunciation sets
# ---------------------------------------------------------------------------


@router.get(
    "/courses/{course_id}/pronunciation-sets",
    response_model=APIResponse[list[PronunciationSetResponse]],
)
async def list_pronunciation_sets(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _verify_enrollment(db, course_id, user.id)

    stmt = (
        select(
            PronunciationSet,
            func.count(PronunciationItem.id).label("item_count"),
        )
        .outerjoin(
            PronunciationItem,
            PronunciationItem.pronunciation_set_id == PronunciationSet.id,
        )
        .where(
            PronunciationSet.course_id == course_id,
            PronunciationSet.deleted_at.is_(None),
        )
        .group_by(PronunciationSet.id)
    )

    if user.role != "instructor":
        stmt = stmt.where(PronunciationSet.is_published.is_(True))

    result = await db.execute(stmt)
    rows = result.all()

    data = [
        PronunciationSetResponse(
            id=ps.id,
            course_id=ps.course_id,
            title=ps.title,
            is_published=ps.is_published,
            difficulty=ps.difficulty,
            language=ps.language,
            folder_id=ps.folder_id,
            item_count=item_count,
            created_at=ps.created_at,
        )
        for ps, item_count in rows
    ]

    return APIResponse(success=True, data=data)


@router.get(
    "/pronunciation-sets/{set_id}",
    response_model=APIResponse[PronunciationSetDetailResponse],
)
async def get_pronunciation_set(
    set_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PronunciationSet)
        .options(selectinload(PronunciationSet.items))
        .where(
            PronunciationSet.id == set_id,
            PronunciationSet.deleted_at.is_(None),
        )
    )
    pron_set = result.scalar_one_or_none()
    if not pron_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pronunciation set not found",
        )

    await _verify_enrollment(db, pron_set.course_id, user.id)

    if user.role != "instructor" and not pron_set.is_published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pronunciation set not found",
        )

    item_responses = [
        PronunciationItemResponse(
            id=i.id,
            item_index=i.item_index,
            text=i.text,
            phonetic=i.phonetic,
            translation=i.translation,
            tips=i.tips,
            item_type=i.item_type,
            difficulty=i.difficulty,
            created_at=i.created_at,
        )
        for i in pron_set.items
    ]

    return APIResponse(
        success=True,
        data=PronunciationSetDetailResponse(
            id=pron_set.id,
            course_id=pron_set.course_id,
            title=pron_set.title,
            is_published=pron_set.is_published,
            difficulty=pron_set.difficulty,
            language=pron_set.language,
            folder_id=pron_set.folder_id,
            items=item_responses,
            created_at=pron_set.created_at,
        ),
    )


def _set_response(
    pron_set: PronunciationSet, item_count: int
) -> PronunciationSetResponse:
    return PronunciationSetResponse(
        id=pron_set.id,
        course_id=pron_set.course_id,
        title=pron_set.title,
        is_published=pron_set.is_published,
        difficulty=pron_set.difficulty,
        language=pron_set.language,
        folder_id=pron_set.folder_id,
        item_count=item_count,
        created_at=pron_set.created_at,
    )


async def _count_items(db: AsyncSession, set_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count(PronunciationItem.id)).where(
            PronunciationItem.pronunciation_set_id == set_id
        )
    )
    return result.scalar_one()


@router.patch(
    "/pronunciation-sets/{set_id}",
    response_model=APIResponse[PronunciationSetResponse],
)
async def update_pronunciation_set(
    set_id: uuid.UUID,
    body: PronunciationSetUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(PronunciationSet).where(
            PronunciationSet.id == set_id,
            PronunciationSet.created_by == user.id,
            PronunciationSet.deleted_at.is_(None),
        )
    )
    pron_set = result.scalar_one_or_none()
    if not pron_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pronunciation set not found",
        )

    if body.title is not None:
        title = body.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="Title cannot be empty")
        pron_set.title = title[:255]

    await db.commit()
    await db.refresh(pron_set)

    item_count = await _count_items(db, pron_set.id)
    return APIResponse(success=True, data=_set_response(pron_set, item_count))


@router.post(
    "/pronunciation-sets/{set_id}/publish",
    response_model=APIResponse[PronunciationSetResponse],
)
async def publish_pronunciation_set(
    set_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(PronunciationSet).where(
            PronunciationSet.id == set_id,
            PronunciationSet.created_by == user.id,
            PronunciationSet.deleted_at.is_(None),
        )
    )
    pron_set = result.scalar_one_or_none()
    if not pron_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pronunciation set not found",
        )

    pron_set.is_published = not pron_set.is_published
    await db.commit()
    await db.refresh(pron_set)

    item_count = await _count_items(db, pron_set.id)
    return APIResponse(success=True, data=_set_response(pron_set, item_count))


@router.delete(
    "/pronunciation-sets/{set_id}",
    response_model=APIResponse[None],
)
async def delete_pronunciation_set(
    set_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(PronunciationSet).where(
            PronunciationSet.id == set_id,
            PronunciationSet.created_by == user.id,
            PronunciationSet.deleted_at.is_(None),
        )
    )
    pron_set = result.scalar_one_or_none()
    if not pron_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pronunciation set not found",
        )

    pron_set.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return APIResponse(success=True, data=None)


# ---------------------------------------------------------------------------
# Per-item review actions (instructor-only)
# ---------------------------------------------------------------------------


@router.post(
    "/pronunciation-sets/{set_id}/items",
    response_model=APIResponse[PronunciationItemResponse],
    status_code=status.HTTP_201_CREATED,
)
async def add_pronunciation_item(
    set_id: uuid.UUID,
    body: PronunciationItemCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(PronunciationSet).where(
            PronunciationSet.id == set_id,
            PronunciationSet.created_by == user.id,
            PronunciationSet.deleted_at.is_(None),
        )
    )
    pron_set = result.scalar_one_or_none()
    if not pron_set:
        raise HTTPException(status_code=404, detail="Pronunciation set not found")

    count_result = await db.execute(
        select(func.count(PronunciationItem.id)).where(
            PronunciationItem.pronunciation_set_id == set_id
        )
    )
    next_index = count_result.scalar_one()

    item = PronunciationItem(
        pronunciation_set_id=set_id,
        item_index=next_index,
        text=body.text.strip(),
        item_type=body.item_type,
        phonetic=(body.phonetic or "").strip() or None,
        translation=(body.translation or "").strip() or None,
        tips=(body.tips or "").strip() or None,
        difficulty=body.difficulty,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return APIResponse(
        success=True, data=PronunciationItemResponse.model_validate(item)
    )


@router.delete(
    "/pronunciation-items/{item_id}",
    response_model=APIResponse[None],
)
async def delete_pronunciation_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(PronunciationItem)
        .join(
            PronunciationSet,
            PronunciationSet.id == PronunciationItem.pronunciation_set_id,
        )
        .where(
            PronunciationItem.id == item_id,
            PronunciationSet.created_by == user.id,
            PronunciationSet.deleted_at.is_(None),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    set_id = item.pronunciation_set_id
    await db.delete(item)

    remaining = await db.execute(
        select(PronunciationItem)
        .where(PronunciationItem.pronunciation_set_id == set_id)
        .order_by(PronunciationItem.item_index)
    )
    for idx, it in enumerate(remaining.scalars().all()):
        it.item_index = idx

    await db.commit()
    return APIResponse(success=True, data=None)


@router.patch(
    "/pronunciation-items/{item_id}",
    response_model=APIResponse[PronunciationItemResponse],
)
async def update_pronunciation_item(
    item_id: uuid.UUID,
    body: PronunciationItemUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(PronunciationItem)
        .join(
            PronunciationSet,
            PronunciationSet.id == PronunciationItem.pronunciation_set_id,
        )
        .where(
            PronunciationItem.id == item_id,
            PronunciationSet.created_by == user.id,
            PronunciationSet.deleted_at.is_(None),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if body.text is not None:
        text = body.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="Text cannot be empty")
        item.text = text
    if body.item_type is not None:
        item.item_type = body.item_type
    if body.phonetic is not None:
        item.phonetic = body.phonetic.strip() or None
    if body.translation is not None:
        item.translation = body.translation.strip() or None
    if body.tips is not None:
        item.tips = body.tips.strip() or None
    if body.difficulty is not None:
        item.difficulty = body.difficulty

    await db.commit()
    await db.refresh(item)
    return APIResponse(
        success=True, data=PronunciationItemResponse.model_validate(item)
    )


@router.post(
    "/pronunciation-items/{item_id}/regenerate",
    response_model=APIResponse[PronunciationItemResponse],
)
async def regenerate_pronunciation_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    from app.services.embedder import embed_query
    from app.services.generator import generate_pronunciation
    from app.services.retriever import retrieve_chunks

    result = await db.execute(
        select(PronunciationItem)
        .join(
            PronunciationSet,
            PronunciationSet.id == PronunciationItem.pronunciation_set_id,
        )
        .where(
            PronunciationItem.id == item_id,
            PronunciationSet.created_by == user.id,
            PronunciationSet.deleted_at.is_(None),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    set_result = await db.execute(
        select(PronunciationSet)
        .options(selectinload(PronunciationSet.source_documents))
        .where(PronunciationSet.id == item.pronunciation_set_id)
    )
    pron_set = set_result.scalar_one()
    doc_ids = [sd.document_id for sd in pron_set.source_documents] or None

    query_embedding = await embed_query(item.text)
    chunks = await retrieve_chunks(
        db,
        course_id=pron_set.course_id,
        query_embedding=query_embedding,
        top_k=10,
        document_ids=doc_ids,
    )

    # Preserve the original item_type so a regenerated word stays a word.
    generated = await generate_pronunciation(
        chunks,
        num_items=1,
        item_types=[item.item_type],
        difficulty=item.difficulty or "medium",
        language=pron_set.language,
    )
    if not generated:
        raise HTTPException(
            status_code=500, detail="Failed to regenerate item"
        )

    new_item = generated[0]
    item.text = new_item.text
    item.phonetic = new_item.phonetic
    item.translation = new_item.translation
    item.tips = new_item.tips
    item.item_type = new_item.item_type
    if item.difficulty == "mixed":
        item.difficulty = new_item.difficulty

    await db.commit()
    await db.refresh(item)
    return APIResponse(
        success=True, data=PronunciationItemResponse.model_validate(item)
    )


# ---------------------------------------------------------------------------
# Pronunciation folders
# ---------------------------------------------------------------------------

# Maximum nesting depth for folder trees. Mirrors the flashcard cap to keep UI
# breadcrumbs sane and prevent unbounded recursion via deeply nested structures.
MAX_FOLDER_DEPTH = 10


async def _pron_folder_ancestor_depth(
    db: AsyncSession, parent_id: uuid.UUID
) -> int:
    """Return the depth of ``parent_id`` (root = depth 1). Guards against cycles."""
    depth = 1
    current: uuid.UUID | None = parent_id
    visited: set[uuid.UUID] = set()
    while current is not None:
        if current in visited:
            return MAX_FOLDER_DEPTH + 1
        visited.add(current)
        parent = await db.get(PronunciationFolder, current)
        if parent is None or parent.deleted_at is not None:
            break
        if parent.parent_id is None:
            break
        depth += 1
        if depth > MAX_FOLDER_DEPTH:
            return depth
        current = parent.parent_id
    return depth


async def _pron_folder_first_live_ancestor(
    db: AsyncSession, folder: PronunciationFolder
) -> uuid.UUID | None:
    current = folder.parent_id
    visited: set[uuid.UUID] = set()
    while current is not None:
        if current in visited:
            logger.warning(
                "pronunciation folder cycle detected during ancestor walk",
                extra={"folder_id": str(folder.id), "cycle_at": str(current)},
            )
            return None
        visited.add(current)
        ancestor = await db.get(PronunciationFolder, current)
        if ancestor is None:
            return None
        if ancestor.deleted_at is None:
            return ancestor.id
        current = ancestor.parent_id
    return None


async def _pron_folder_descendant_ids(
    db: AsyncSession, root_id: uuid.UUID
) -> set[uuid.UUID]:
    base = (
        select(PronunciationFolder.id.label("id"))
        .where(
            PronunciationFolder.id == root_id,
            PronunciationFolder.deleted_at.is_(None),
        )
        .cte(name="pronunciation_folder_descendants", recursive=True)
    )
    recursive = select(PronunciationFolder.id).where(
        PronunciationFolder.parent_id == base.c.id,
        PronunciationFolder.deleted_at.is_(None),
    )
    cte = base.union_all(recursive)
    rows = (await db.execute(select(cte.c.id))).scalars().all()
    return set(rows)


async def _pron_folder_subtree_height(
    db: AsyncSession, folder_id: uuid.UUID
) -> int:
    height = 0
    frontier: set[uuid.UUID] = {folder_id}
    visited: set[uuid.UUID] = {folder_id}
    while frontier:
        rows = (
            await db.execute(
                select(PronunciationFolder.id).where(
                    PronunciationFolder.parent_id.in_(frontier),
                    PronunciationFolder.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        next_frontier: set[uuid.UUID] = set()
        for child_id in rows:
            if child_id in visited:
                continue
            visited.add(child_id)
            next_frontier.add(child_id)
        if not next_frontier:
            break
        height += 1
        frontier = next_frontier
        if height > MAX_FOLDER_DEPTH:
            return height
    return height


@router.get(
    "/courses/{course_id}/pronunciation-folders",
    response_model=APIResponse[list[PronunciationFolderResponse]],
)
async def list_pronunciation_folders(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _verify_enrollment(db, course_id, user.id)
    result = await db.execute(
        select(PronunciationFolder)
        .where(
            PronunciationFolder.course_id == course_id,
            PronunciationFolder.deleted_at.is_(None),
        )
        .order_by(PronunciationFolder.created_at)
    )
    return APIResponse(
        success=True,
        data=[
            PronunciationFolderResponse.model_validate(f)
            for f in result.scalars().all()
        ],
    )


@router.post(
    "/courses/{course_id}/pronunciation-folders",
    response_model=APIResponse[PronunciationFolderResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_pronunciation_folder(
    course_id: uuid.UUID,
    body: PronunciationFolderCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _verify_enrollment(db, course_id, user.id)
    if body.parent_id is not None:
        parent = await db.get(PronunciationFolder, body.parent_id)
        if (
            parent is None
            or parent.deleted_at is not None
            or parent.course_id != course_id
        ):
            raise HTTPException(
                status_code=400, detail="Parent folder not found in this course"
            )
        parent_depth = await _pron_folder_ancestor_depth(db, parent.id)
        if parent_depth >= MAX_FOLDER_DEPTH:
            raise HTTPException(
                status_code=400,
                detail=f"Folder nesting exceeds maximum depth of {MAX_FOLDER_DEPTH}",
            )
    folder = PronunciationFolder(
        course_id=course_id,
        name=body.name.strip() or "Untitled",
        parent_id=body.parent_id,
        created_by=user.id,
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return APIResponse(
        success=True, data=PronunciationFolderResponse.model_validate(folder)
    )


@router.patch(
    "/pronunciation-folders/{folder_id}",
    response_model=APIResponse[PronunciationFolderResponse],
)
async def rename_pronunciation_folder(
    folder_id: uuid.UUID,
    body: PronunciationFolderRename,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    folder = await db.get(PronunciationFolder, folder_id)
    if folder is None or folder.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Folder not found")
    await _verify_enrollment(db, folder.course_id, user.id)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    folder.name = name
    await db.commit()
    await db.refresh(folder)
    return APIResponse(
        success=True, data=PronunciationFolderResponse.model_validate(folder)
    )


@router.post(
    "/pronunciation-folders/{folder_id}/move",
    response_model=APIResponse[PronunciationFolderResponse],
)
async def move_pronunciation_folder(
    folder_id: uuid.UUID,
    body: PronunciationFolderMove,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    preview = await db.get(PronunciationFolder, folder_id)
    if preview is None or preview.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Folder not found")
    await _verify_enrollment(db, preview.course_id, user.id)
    await db.rollback()

    candidate_ids = {folder_id}
    if body.parent_id is not None and body.parent_id != folder_id:
        candidate_ids.add(body.parent_id)
    lock_ids: list[uuid.UUID] = sorted(candidate_ids, key=lambda x: x.bytes)

    folder: PronunciationFolder | None = None
    for attempt in range(3):
        try:
            await db.connection(
                execution_options={"isolation_level": "SERIALIZABLE"}
            )
            locked_rows = (
                await db.execute(
                    select(PronunciationFolder)
                    .where(PronunciationFolder.id.in_(lock_ids))
                    .order_by(PronunciationFolder.id)
                    .with_for_update()
                )
            ).scalars().all()
            locked_by_id = {row.id: row for row in locked_rows}

            folder = locked_by_id.get(folder_id)
            if folder is None or folder.deleted_at is not None:
                raise HTTPException(status_code=404, detail="Folder not found")
            if body.parent_id is not None:
                if body.parent_id == folder_id:
                    raise HTTPException(
                        status_code=400,
                        detail="Cannot nest folder inside itself",
                    )
                parent = locked_by_id.get(body.parent_id)
                if (
                    parent is None
                    or parent.deleted_at is not None
                    or parent.course_id != folder.course_id
                ):
                    raise HTTPException(
                        status_code=400,
                        detail="Parent folder not found in this course",
                    )
                descendants = await _pron_folder_descendant_ids(db, folder_id)
                if body.parent_id in descendants:
                    raise HTTPException(
                        status_code=400,
                        detail="Cannot move folder into its own descendant",
                    )
                parent_depth = await _pron_folder_ancestor_depth(db, parent.id)
                subtree_height = await _pron_folder_subtree_height(db, folder_id)
                if parent_depth + subtree_height > MAX_FOLDER_DEPTH:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Folder nesting exceeds maximum depth of {MAX_FOLDER_DEPTH}",
                    )
            folder.parent_id = body.parent_id
            await db.commit()
            break
        except DBAPIError as exc:
            pgcode = getattr(exc.orig, "pgcode", None) if exc.orig else None
            if pgcode in ("40001", "40P01") and attempt < 2:
                await db.rollback()
                await asyncio.sleep(0.05 * (2**attempt))
                continue
            if pgcode in ("40001", "40P01"):
                await db.rollback()
                raise HTTPException(
                    status_code=409,
                    detail="conflicting_move_please_retry",
                ) from exc
            raise

    assert folder is not None
    await db.refresh(folder)
    return APIResponse(
        success=True, data=PronunciationFolderResponse.model_validate(folder)
    )


@router.delete(
    "/pronunciation-folders/{folder_id}",
    response_model=APIResponse[None],
)
async def delete_pronunciation_folder(
    folder_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    folder = await db.get(PronunciationFolder, folder_id)
    if folder is None or folder.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Folder not found")
    await _verify_enrollment(db, folder.course_id, user.id)

    new_parent = await _pron_folder_first_live_ancestor(db, folder)

    async with db.begin_nested():
        await db.execute(
            PronunciationSet.__table__.update()
            .where(PronunciationSet.folder_id == folder_id)
            .values(folder_id=new_parent)
        )
        await db.execute(
            PronunciationFolder.__table__.update()
            .where(PronunciationFolder.parent_id == folder_id)
            .values(parent_id=new_parent)
        )
        folder.deleted_at = datetime.now(timezone.utc)

    await db.commit()
    return APIResponse(success=True, data=None)


@router.patch(
    "/pronunciation-sets/{set_id}/folder",
    response_model=APIResponse[PronunciationSetResponse],
)
async def move_pronunciation_set_to_folder(
    set_id: uuid.UUID,
    body: PronunciationSetMove,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    pron_set = await db.get(PronunciationSet, set_id)
    if pron_set is None or pron_set.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Pronunciation set not found")
    await _verify_enrollment(db, pron_set.course_id, user.id)
    if body.folder_id is not None:
        folder = await db.get(PronunciationFolder, body.folder_id)
        if (
            folder is None
            or folder.deleted_at is not None
            or folder.course_id != pron_set.course_id
        ):
            raise HTTPException(
                status_code=400, detail="Folder not found in this course"
            )
    pron_set.folder_id = body.folder_id
    await db.commit()
    await db.refresh(pron_set)

    item_count = await _count_items(db, pron_set.id)
    return APIResponse(success=True, data=_set_response(pron_set, item_count))
