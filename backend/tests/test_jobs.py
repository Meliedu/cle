"""Tests for async generation job handlers in app.services.jobs."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.chunk import Chunk
from app.models.course import Course
from app.models.document import Document
from app.models.flashcard import FlashcardCard, FlashcardSet
from app.models.quiz import Question, Quiz
from app.models.summary import CourseSummary
from app.models.task import Task
from app.models.user import User
from app.services.generator import (
    GeneratedFlashcard,
    GeneratedQuestion,
)
from app.services.jobs import (
    run_generate_flashcards,
    run_generate_quiz,
    run_generate_summary,
)
from app.services.retriever import RetrievedChunk
from app.services.worker import complete_task, process_task


@pytest_asyncio.fixture
async def instructor_and_course(db_session):
    instructor = User(
        better_auth_id=f"dev_{uuid.uuid4().hex[:10]}",
        email="jobs-test@ust.hk",
        full_name="Jobs Tester",
        role="instructor",
    )
    db_session.add(instructor)
    await db_session.flush()

    course = Course(
        name="Test course",
        description="…",
        language="spanish",
        instructor_id=instructor.id,
        enroll_code=f"E{uuid.uuid4().hex[:8]}",
    )
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(instructor)
    await db_session.refresh(course)
    return instructor, course


@pytest.mark.asyncio
async def test_run_generate_quiz_creates_quiz_and_questions(
    db_session, instructor_and_course
):
    instructor, course = instructor_and_course

    fake_questions = [
        GeneratedQuestion(
            question_text=f"Q{i}",
            options={"A": "a", "B": "b", "C": "c", "D": "d"},
            correct_answer="A",
            explanation="E",
        )
        for i in range(3)
    ]

    with patch(
        "app.services.jobs.embed_query", new_callable=AsyncMock
    ) as mock_embed, patch(
        "app.services.jobs.retrieve_chunks", new_callable=AsyncMock
    ) as mock_retrieve, patch(
        "app.services.jobs.generate_quiz", new_callable=AsyncMock
    ) as mock_gen:
        mock_embed.return_value = [0.0] * 3072
        mock_retrieve.return_value = []
        mock_gen.return_value = fake_questions

        result = await run_generate_quiz(
            db_session,
            {
                "course_id": str(course.id),
                "user_id": str(instructor.id),
                "title": "Chapter 3 Review",
                "num_questions": 3,
                "document_ids": None,
            },
        )

    assert result["question_count"] == 3
    quiz_id = uuid.UUID(result["quiz_id"])

    quizzes = (await db_session.execute(select(Quiz))).scalars().all()
    assert len(quizzes) == 1
    assert quizzes[0].id == quiz_id
    assert quizzes[0].title == "Chapter 3 Review"

    qs = (await db_session.execute(select(Question))).scalars().all()
    assert len(qs) == 3


@pytest.mark.asyncio
async def test_run_generate_flashcards_creates_set_and_cards(
    db_session, instructor_and_course
):
    instructor, course = instructor_and_course

    with patch(
        "app.services.jobs.embed_query", new_callable=AsyncMock
    ) as mock_embed, patch(
        "app.services.jobs.retrieve_chunks", new_callable=AsyncMock
    ) as mock_retrieve, patch(
        "app.services.jobs.generate_flashcards", new_callable=AsyncMock
    ) as mock_gen:
        mock_embed.return_value = [0.0] * 3072
        mock_retrieve.return_value = []
        mock_gen.return_value = [
            GeneratedFlashcard(front=f"F{i}", back=f"B{i}") for i in range(2)
        ]

        result = await run_generate_flashcards(
            db_session,
            {
                "course_id": str(course.id),
                "user_id": str(instructor.id),
                "title": "Basics",
                "num_cards": 2,
                "document_ids": None,
            },
        )

    assert result["card_count"] == 2
    assert "flashcard_set_id" in result

    sets = (await db_session.execute(select(FlashcardSet))).scalars().all()
    cards = (await db_session.execute(select(FlashcardCard))).scalars().all()
    assert len(sets) == 1 and len(cards) == 2


@pytest.mark.asyncio
async def test_run_generate_summary_upserts(
    db_session, instructor_and_course
):
    instructor, course = instructor_and_course

    with patch(
        "app.services.jobs.embed_query", new_callable=AsyncMock
    ) as mock_embed, patch(
        "app.services.jobs.retrieve_chunks", new_callable=AsyncMock
    ) as mock_retrieve, patch(
        "app.services.jobs.generate_summary", new_callable=AsyncMock
    ) as mock_gen:
        mock_embed.return_value = [0.0] * 3072
        mock_retrieve.return_value = []
        mock_gen.return_value = "# Summary\n\nKey concepts…"

        result = await run_generate_summary(
            db_session,
            {
                "course_id": str(course.id),
                "user_id": str(instructor.id),
                "document_ids": None,
            },
        )

        # Second call should upsert (not duplicate)
        mock_gen.return_value = "# Summary v2"
        await run_generate_summary(
            db_session,
            {
                "course_id": str(course.id),
                "user_id": str(instructor.id),
                "document_ids": None,
            },
        )

    assert "summary_id" in result
    rows = (await db_session.execute(select(CourseSummary))).scalars().all()
    assert len(rows) == 1
    assert rows[0].summary_text == "# Summary v2"


@pytest.mark.asyncio
async def test_process_task_then_complete_task_writes_result(
    db_session, instructor_and_course
):
    """End-to-end: Task row through worker.process_task + complete_task."""
    instructor, course = instructor_and_course

    task = Task(
        task_type="generate_quiz",
        payload={
            "course_id": str(course.id),
            "user_id": str(instructor.id),
            "title": "Worker Roundtrip",
            "num_questions": 2,
            "document_ids": None,
        },
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    with patch(
        "app.services.jobs.embed_query", new_callable=AsyncMock
    ) as mock_embed, patch(
        "app.services.jobs.retrieve_chunks", new_callable=AsyncMock
    ) as mock_retrieve, patch(
        "app.services.jobs.generate_quiz", new_callable=AsyncMock
    ) as mock_gen:
        mock_embed.return_value = [0.0] * 3072
        mock_retrieve.return_value = []
        mock_gen.return_value = [
            GeneratedQuestion(
                question_text="Q",
                options={"A": "a", "B": "b", "C": "c", "D": "d"},
                correct_answer="A",
                explanation="E",
            )
            for _ in range(2)
        ]

        result = await process_task(db_session, task)
        await complete_task(db_session, task.id, result)

    await db_session.refresh(task)
    assert task.status == "completed"
    assert task.payload["result"]["question_count"] == 2
    assert "quiz_id" in task.payload["result"]


# ---------------------------------------------------------------------------
# Tag-inheritance enqueue (C-1: Phase 2 mastery wiring)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def course_with_chunk(db_session, instructor_and_course):
    """Build the minimum graph needed to exercise the enqueue path:
    instructor + course + a Document + a single Chunk we can use as the
    primary source for retrieval."""
    instructor, course = instructor_and_course
    doc = Document(
        course_id=course.id,
        uploaded_by=instructor.id,
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
        course_id=course.id,
        chunk_index=0,
        content="Big-O notation describes asymptotic complexity.",
        token_count=8,
        embedding=[0.0] * 1536,
    )
    db_session.add(chunk)
    await db_session.commit()
    await db_session.refresh(chunk)
    return instructor, course, chunk


def _retrieved_chunk(chunk: Chunk) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk.id,
        content=chunk.content,
        document_id=chunk.document_id,
        page_number=None,
        similarity_score=0.99,
    )


@pytest.mark.asyncio
async def test_run_generate_quiz_enqueues_tag_inheritance_per_question(
    db_session, course_with_chunk
):
    """C-1: each new Question must trigger a tag_artifact_concepts task with
    its source_chunk_id so chunk concept tags inherit (× 0.7) onto the question.

    Without this wiring the mastery update path finds zero tags and
    Phase 2 silently no-ops in production.
    """
    instructor, course, chunk = course_with_chunk

    fake_questions = [
        GeneratedQuestion(
            question_text=f"Q{i}",
            options={"A": "a", "B": "b", "C": "c", "D": "d"},
            correct_answer="A",
            explanation="E",
        )
        for i in range(2)
    ]

    with patch(
        "app.services.jobs.embed_query", new_callable=AsyncMock
    ) as mock_embed, patch(
        "app.services.jobs.retrieve_chunks", new_callable=AsyncMock
    ) as mock_retrieve, patch(
        "app.services.jobs.generate_quiz", new_callable=AsyncMock
    ) as mock_gen:
        mock_embed.return_value = [0.0] * 3072
        mock_retrieve.return_value = [_retrieved_chunk(chunk)]
        mock_gen.return_value = fake_questions

        result = await run_generate_quiz(
            db_session,
            {
                "course_id": str(course.id),
                "user_id": str(instructor.id),
                "title": "Algorithms Quiz",
                "num_questions": 2,
                "document_ids": None,
            },
        )

    assert result["question_count"] == 2

    questions = (await db_session.execute(select(Question))).scalars().all()
    assert len(questions) == 2
    # Every question carries the primary chunk as its source so the
    # downstream inherit job has something to copy from.
    assert all(q.source_chunk_id == chunk.id for q in questions)

    tag_tasks = (
        await db_session.execute(
            select(Task).where(Task.task_type == "tag_artifact_concepts")
        )
    ).scalars().all()
    assert len(tag_tasks) == 2
    target_ids = {t.payload["target_id"] for t in tag_tasks}
    assert target_ids == {str(q.id) for q in questions}
    for t in tag_tasks:
        assert t.payload["target_kind"] == "question"
        assert t.payload["course_id"] == str(course.id)
        assert t.payload["source_chunk_id"] == str(chunk.id)
        assert t.status == "pending"


@pytest.mark.asyncio
async def test_run_generate_flashcards_enqueues_tag_inheritance_per_card(
    db_session, course_with_chunk
):
    instructor, course, chunk = course_with_chunk

    with patch(
        "app.services.jobs.embed_query", new_callable=AsyncMock
    ) as mock_embed, patch(
        "app.services.jobs.retrieve_chunks", new_callable=AsyncMock
    ) as mock_retrieve, patch(
        "app.services.jobs.generate_flashcards", new_callable=AsyncMock
    ) as mock_gen:
        mock_embed.return_value = [0.0] * 3072
        mock_retrieve.return_value = [_retrieved_chunk(chunk)]
        mock_gen.return_value = [
            GeneratedFlashcard(front=f"F{i}", back=f"B{i}") for i in range(3)
        ]

        await run_generate_flashcards(
            db_session,
            {
                "course_id": str(course.id),
                "user_id": str(instructor.id),
                "title": "Basics",
                "num_cards": 3,
                "document_ids": None,
            },
        )

    cards = (await db_session.execute(select(FlashcardCard))).scalars().all()
    assert len(cards) == 3
    assert all(c.source_chunk_id == chunk.id for c in cards)

    tag_tasks = (
        await db_session.execute(
            select(Task).where(Task.task_type == "tag_artifact_concepts")
        )
    ).scalars().all()
    assert len(tag_tasks) == 3
    assert all(
        t.payload["target_kind"] == "flashcard_card" for t in tag_tasks
    )
    assert {t.payload["target_id"] for t in tag_tasks} == {str(c.id) for c in cards}


@pytest.mark.asyncio
async def test_run_generate_quiz_skips_enqueue_when_no_chunks_retrieved(
    db_session, instructor_and_course
):
    """When retrieval returns nothing the artifact has no source chunk to
    inherit from — skip the enqueue rather than write a doomed orphan task."""
    instructor, course = instructor_and_course

    with patch(
        "app.services.jobs.embed_query", new_callable=AsyncMock
    ) as mock_embed, patch(
        "app.services.jobs.retrieve_chunks", new_callable=AsyncMock
    ) as mock_retrieve, patch(
        "app.services.jobs.generate_quiz", new_callable=AsyncMock
    ) as mock_gen:
        mock_embed.return_value = [0.0] * 3072
        mock_retrieve.return_value = []
        mock_gen.return_value = [
            GeneratedQuestion(
                question_text="Q",
                options={"A": "a", "B": "b", "C": "c", "D": "d"},
                correct_answer="A",
                explanation="E",
            )
        ]

        await run_generate_quiz(
            db_session,
            {
                "course_id": str(course.id),
                "user_id": str(instructor.id),
                "title": "Empty",
                "num_questions": 1,
                "document_ids": None,
            },
        )

    questions = (await db_session.execute(select(Question))).scalars().all()
    assert len(questions) == 1
    assert questions[0].source_chunk_id is None

    tag_tasks = (
        await db_session.execute(
            select(Task).where(Task.task_type == "tag_artifact_concepts")
        )
    ).scalars().all()
    assert tag_tasks == []
