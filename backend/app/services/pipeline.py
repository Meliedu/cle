from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.document import Document
from app.models.task import Task
from app.services.chunker import chunk_text
from app.services.embedder import embed_texts
from app.services.parser import parse_document
from app.services.storage import download_file

logger = logging.getLogger(__name__)


async def _set_document_status(
    session: AsyncSession, document: Document, status: str, error_code: str | None = None
) -> None:
    """Persist a document status transition; isolate failures so the caller's
    original error is not masked by a commit/rollback failure here.

    error_code is the typed, user-safe failure classification recorded when
    transitioning to failed. It is cleared on any other transition so a
    retried document does not keep showing recovery copy for a failure that no
    longer applies.
    """
    try:
        document.status = status
        document.error_code = error_code
        await session.commit()
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to persist document status=%s for %s", status, document.id
        )
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            logger.exception("Rollback also failed")


async def process_document_pipeline(
    session: AsyncSession, document_id: str
) -> bool:
    doc_uuid = uuid.UUID(document_id)

    result = await session.execute(
        select(Document).where(Document.id == doc_uuid)
    )
    document = result.scalar_one_or_none()
    if not document:
        raise ValueError(f"Document not found: {document_id}")

    await _set_document_status(session, document, "processing")

    try:
        # 1. Download from R2 — boto3 is sync, off-load to thread pool so the
        #    event loop isn't blocked for multi-second downloads on large docs.
        logger.info(f"Downloading {document.r2_key}")
        file_data = await asyncio.to_thread(download_file, document.r2_key)

        # 2. Parse
        logger.info(f"Parsing {document.filename} (type={document.file_type})")
        parse_result = await parse_document(
            file_data, document.file_type, document.filename
        )

        # 3. Chunk
        logger.info(f"Chunking {parse_result.word_count} words")
        chunks = chunk_text(parse_result.text, pages=parse_result.pages)
        logger.info(f"Created {len(chunks)} chunks")

        if not chunks:
            document.status = "ready"
            document.page_count = parse_result.page_count
            document.word_count = parse_result.word_count
            await session.commit()
            return True

        # 4. Embed
        logger.info(f"Embedding {len(chunks)} chunks")
        embeddings = await embed_texts([c.content for c in chunks])

        # 5. Store chunks + final metadata in a single transaction.
        #
        # Clear any chunks already stored for this document first. A previous
        # run can have committed a full chunk set at the commit below and then
        # failed in step 6, which flips the row to "failed" with its chunks
        # intact. Both the reprocess endpoint and the worker's stuck-task
        # requeue then re-enter here, and without this delete each attempt
        # appends a second full set: duplicate retrieval hits, and a second
        # embedding bill. Same transaction as the insert, so a crash between
        # the two cannot leave the document with no chunks at all.
        await session.execute(delete(Chunk).where(Chunk.document_id == document.id))

        created_chunks: list[Chunk] = []
        for chunk_data, embedding in zip(chunks, embeddings):
            chunk = Chunk(
                document_id=document.id,
                course_id=document.course_id,
                content=chunk_data.content,
                chunk_index=chunk_data.chunk_index,
                page_number=chunk_data.page_number,
                token_count=chunk_data.token_count,
                embedding=embedding,
                metadata_=dict(chunk_data.metadata) if chunk_data.metadata else {},
            )
            session.add(chunk)
            created_chunks.append(chunk)

        document.status = "ready"
        document.page_count = parse_result.page_count
        document.word_count = parse_result.word_count
        await session.commit()

        # 6. Enqueue concept-tagging tasks for each newly-stored chunk so the
        #    worker can populate ``concept_tags`` asynchronously. Only runs
        #    after the chunk commit above succeeded — failed chunk inserts
        #    raise and skip this block via the ``except`` branch.
        for created_chunk in created_chunks:
            session.add(
                Task(
                    task_type="tag_artifact_concepts",
                    payload={
                        "target_kind": "chunk",
                        "target_id": str(created_chunk.id),
                        "course_id": str(created_chunk.course_id),
                    },
                    status="pending",
                )
            )
        await session.commit()

        logger.info(f"Document {document_id} processed: {len(chunks)} chunks stored")
        return True

    except Exception as exc:
        # Classify before persisting so the instructor sees actionable copy
        # rather than an exception, and the raw detail goes to the structured
        # log where triage needs it (safe failure contract, rules 01 and 02).
        from app.services.failures import classify_and_log

        code = classify_and_log(
            exc,
            context="process_document_pipeline",
            document_id=document_id,
            course_id=document.course_id,
        )
        await _set_document_status(session, document, "failed", code.value)
        raise
