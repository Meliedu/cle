"""Tests for the ``generate_checkpoints`` job (T022): grounded, DRAFT-only
checkpoint drafting with a fixed ``final_comments`` card and concept-tagged
review-point cards.

The LLM/generator and retrieval boundaries are mocked so the job runs fully
offline and deterministically (Decision 3: checkpoints are written in ``draft``
state only; the publish/approve state machine is P3).
"""

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.chunk import Chunk
from app.models.checkpoint import Checkpoint, CheckpointCard
from app.models.course import Course
from app.models.curriculum import CourseMeeting
from app.models.document import Document
from app.models.task import Task
from app.services import checkpoint_generation
from app.services.checkpoint_generation import run_generate_checkpoints
from app.services.worker import complete_task, process_task


@pytest_asyncio.fixture
async def seed_course(db_session, test_instructor):
    course = Course(
        name="LANG1511",
        language="zh",
        instructor_id=test_instructor.id,
        enroll_code="CKPT" + uuid.uuid4().hex[:4].upper(),
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


@pytest_asyncio.fixture
async def seed_meeting(db_session, seed_course):
    meeting = CourseMeeting(
        course_id=seed_course.id,
        meeting_index=1,
        title="Greetings",
        scheduled_at=datetime.now(timezone.utc),
        topic_summary="Greetings and numbers",
    )
    db_session.add(meeting)
    await db_session.commit()
    await db_session.refresh(meeting)
    return meeting


@pytest_asyncio.fixture
async def seed_chunk(db_session, seed_course, test_instructor):
    doc = Document(
        course_id=seed_course.id,
        uploaded_by=test_instructor.id,
        filename="ch1.pdf",
        file_type="pdf",
        r2_key=f"docs/{uuid.uuid4()}",
        file_size=1024,
        status="completed",
    )
    db_session.add(doc)
    await db_session.flush()
    chunk = Chunk(
        document_id=doc.id,
        course_id=seed_course.id,
        content="Tone sandhi changes the third tone before another third tone.",
        chunk_index=0,
    )
    db_session.add(chunk)
    await db_session.commit()
    await db_session.refresh(chunk)
    return chunk


@pytest_asyncio.fixture(autouse=True)
def _stub_retrieval(monkeypatch):
    """Keep grounding retrieval offline for every test (no embed/network)."""

    async def _no_retrieval(db, course_id, query, document_ids=None):
        return []

    monkeypatch.setattr(
        checkpoint_generation, "retrieve_grounding_chunks", _no_retrieval
    )


@pytest.mark.asyncio
async def test_generate_creates_draft_checkpoint_with_final_card(
    db_session, seed_course, seed_meeting, monkeypatch
):
    async def fake_ground(db, course_id):
        return "Syllabus: greetings, numbers."

    monkeypatch.setattr(
        checkpoint_generation, "load_syllabus_grounding", fake_ground
    )

    async def fake_cards(*args, **kwargs):
        return [
            {"prompt": "How confident are you ordering food?", "chunk_id": None},
            {"prompt": "Rate your grasp of tone sandhi.", "chunk_id": None},
        ]

    monkeypatch.setattr(checkpoint_generation, "draft_review_cards", fake_cards)

    result = await run_generate_checkpoints(
        db_session,
        {"course_id": str(seed_course.id), "meeting_id": str(seed_meeting.id)},
    )

    cps = (
        await db_session.execute(
            select(Checkpoint).where(Checkpoint.course_id == seed_course.id)
        )
    ).scalars().all()
    assert len(cps) == 1
    assert cps[0].status == "draft"  # Decision 3: never past draft
    assert cps[0].kind == "session"
    assert cps[0].meeting_id == seed_meeting.id

    cards = (
        await db_session.execute(
            select(CheckpointCard).where(
                CheckpointCard.checkpoint_id == cps[0].id
            )
        )
    ).scalars().all()
    kinds = sorted(c.kind for c in cards)
    assert kinds.count("final_comments") == 1  # exactly one fixed final card
    assert kinds.count("review_point") == 2
    assert result["created"] == 1


@pytest.mark.asyncio
async def test_generate_enqueues_tag_tasks_for_anchored_cards(
    db_session, seed_course, seed_meeting, seed_chunk, monkeypatch
):
    async def fake_ground(db, course_id):
        return None

    monkeypatch.setattr(
        checkpoint_generation, "load_syllabus_grounding", fake_ground
    )

    async def fake_cards(*a, **k):
        return [{"prompt": "grounded card", "chunk_id": str(seed_chunk.id)}]

    monkeypatch.setattr(checkpoint_generation, "draft_review_cards", fake_cards)

    await run_generate_checkpoints(
        db_session,
        {"course_id": str(seed_course.id), "meeting_id": str(seed_meeting.id)},
    )

    # The anchored review-point card carries its source anchors.
    card = (
        await db_session.execute(
            select(CheckpointCard).where(
                CheckpointCard.kind == "review_point"
            )
        )
    ).scalar_one()
    assert card.chunk_id == seed_chunk.id
    assert card.document_id == seed_chunk.document_id

    tasks = (
        await db_session.execute(
            select(Task).where(Task.task_type == "tag_artifact_concepts")
        )
    ).scalars().all()
    checkpoint_card_tasks = [
        t for t in tasks if t.payload.get("target_kind") == "checkpoint_card"
    ]
    assert len(checkpoint_card_tasks) == 1
    tag_task = checkpoint_card_tasks[0]
    # Trap 2: target_id MUST be the CARD id, never the checkpoint id.
    assert tag_task.payload["target_id"] == str(card.id)
    assert tag_task.payload["source_chunk_id"] == str(seed_chunk.id)
    assert tag_task.payload["course_id"] == str(seed_course.id)


@pytest.mark.asyncio
async def test_worker_dispatch_runs_generate_checkpoints(
    db_session, seed_course, seed_meeting, monkeypatch
):
    async def fake_ground(db, course_id):
        return None

    monkeypatch.setattr(
        checkpoint_generation, "load_syllabus_grounding", fake_ground
    )

    async def fake_cards(*a, **k):
        return [{"prompt": "confidence check", "chunk_id": None}]

    monkeypatch.setattr(checkpoint_generation, "draft_review_cards", fake_cards)

    task = Task(
        task_type="generate_checkpoints",
        payload={
            "course_id": str(seed_course.id),
            "meeting_id": str(seed_meeting.id),
        },
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    result = await process_task(db_session, task)
    await complete_task(db_session, task.id, result)

    await db_session.refresh(task)
    assert task.status == "completed"
    assert task.payload["result"]["created"] == 1
    cps = (
        await db_session.execute(
            select(Checkpoint).where(Checkpoint.course_id == seed_course.id)
        )
    ).scalars().all()
    assert len(cps) == 1
    assert cps[0].status == "draft"
