# CLE Phase 1b — RAG Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the document processing pipeline (parse → chunk → embed → store) and RAG-powered content generation (quiz, summary, flashcards) with full CRUD APIs.

**Architecture:** Stateless service functions called by the existing task worker (document processing) and new API endpoints (RAG generation). OpenAI for embeddings, OpenRouter for LLM generation, Docling for document parsing, pgvector for similarity search.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, OpenAI SDK (`openai`), Docling, pgvector, pytest.

---

## File Structure

### New Services (`backend/app/services/`)

```
services/
├── parser.py           # Document parsing (Docling + Whisper)
├── chunker.py          # Text chunking with sentence boundaries
├── embedder.py         # OpenAI embedding API wrapper
├── retriever.py        # pgvector cosine similarity search
└── generator.py        # OpenRouter LLM quiz/summary/flashcard generation
```

### New Schemas (`backend/app/schemas/`)

```
schemas/
├── rag.py              # RAG request/response schemas
├── quiz.py             # Quiz CRUD schemas
└── flashcard.py        # Flashcard CRUD schemas
```

### New API Routes (`backend/app/api/`)

```
api/
├── rag.py              # POST /api/rag/* endpoints
├── quizzes.py          # Quiz CRUD endpoints
└── flashcards.py       # Flashcard CRUD endpoints
```

### New Tests (`backend/tests/`)

```
tests/
├── test_chunker.py     # Pure function tests
├── test_parser.py      # Mocked Docling/Whisper tests
├── test_embedder.py    # Mocked OpenAI tests
├── test_retriever.py   # DB integration tests
├── test_generator.py   # Mocked OpenRouter tests
├── test_pipeline.py    # Full pipeline integration test
├── test_api_rag.py     # RAG endpoint tests
├── test_api_quizzes.py # Quiz endpoint tests
└── test_api_flashcards.py # Flashcard endpoint tests
```

### Modified Files

```
services/worker.py      # Wire process_document handler
api/__init__.py          # Register new routers
schemas/__init__.py      # Re-export new schemas
requirements.txt         # Add tiktoken (optional)
```

---

## Task 1: Text Chunker

Pure function, no external dependencies — easiest to test first.

**Files:**
- Create: `backend/app/services/chunker.py`
- Create: `backend/tests/test_chunker.py`

- [ ] **Step 1: Write chunker tests**

```python
# backend/tests/test_chunker.py
import pytest

from app.services.chunker import ChunkData, PageContent, chunk_text


class TestChunkText:
    def test_short_text_single_chunk(self):
        result = chunk_text("Hello world. This is a test.")
        assert len(result) == 1
        assert result[0].content == "Hello world. This is a test."
        assert result[0].chunk_index == 0
        assert result[0].token_count == 7

    def test_long_text_multiple_chunks(self):
        # Create text with ~1000 words (2 chunks at 500-word target)
        sentences = [f"Sentence number {i} has some words in it." for i in range(125)]
        text = " ".join(sentences)
        result = chunk_text(text)
        assert len(result) >= 2
        for i, chunk in enumerate(result):
            assert chunk.chunk_index == i
            assert chunk.token_count > 0
            assert chunk.token_count <= 550  # allow some overflow for sentence alignment

    def test_overlap_between_chunks(self):
        sentences = [f"Sentence number {i} has some words in it." for i in range(125)]
        text = " ".join(sentences)
        result = chunk_text(text)
        if len(result) >= 2:
            # Last words of chunk 0 should appear at start of chunk 1
            words_end_0 = result[0].content.split()[-20:]
            words_start_1 = result[1].content.split()[:60]
            overlap = set(words_end_0) & set(words_start_1)
            assert len(overlap) > 0, "Chunks should overlap"

    def test_preserves_page_numbers(self):
        pages = [
            PageContent(page_number=1, text="Page one content with enough words. " * 60),
            PageContent(page_number=2, text="Page two content with different text. " * 60),
        ]
        full_text = "\n".join(p.text for p in pages)
        result = chunk_text(full_text, pages=pages)
        assert any(c.page_number == 1 for c in result)
        assert any(c.page_number == 2 for c in result)

    def test_empty_text_returns_empty(self):
        result = chunk_text("")
        assert result == []

    def test_whitespace_only_returns_empty(self):
        result = chunk_text("   \n\n  ")
        assert result == []

    def test_sentence_boundary_alignment(self):
        # Chunks should end at sentence boundaries, not mid-sentence
        sentences = ["First sentence here." for _ in range(70)]
        text = " ".join(sentences)
        result = chunk_text(text)
        for chunk in result:
            content = chunk.content.strip()
            assert content.endswith(".") or content.endswith("?") or content.endswith("!") or chunk == result[-1]
```

- [ ] **Step 2: Run tests — should fail**

```bash
cd backend && python -m pytest tests/test_chunker.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.chunker'`

- [ ] **Step 3: Implement chunker.py**

```python
# backend/app/services/chunker.py
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class PageContent:
    page_number: int
    text: str


@dataclass
class ChunkData:
    content: str
    chunk_index: int
    page_number: int | None
    token_count: int


TARGET_CHUNK_TOKENS = 500
OVERLAP_TOKENS = 50
SENTENCE_SPLITTER = re.compile(r"(?<=[.!?])\s+|\n{2,}")


def _count_tokens(text: str) -> int:
    return len(text.split())


def _split_sentences(text: str) -> list[str]:
    parts = SENTENCE_SPLITTER.split(text)
    return [p.strip() for p in parts if p.strip()]


def _find_page_number(
    chunk_start_char: int, pages: list[PageContent] | None
) -> int | None:
    if not pages:
        return None
    running = 0
    for page in pages:
        page_end = running + len(page.text) + 1  # +1 for joining newline
        if chunk_start_char < page_end:
            return page.page_number
        running = page_end
    return pages[-1].page_number if pages else None


def chunk_text(
    text: str, pages: list[PageContent] | None = None
) -> list[ChunkData]:
    text = text.strip()
    if not text:
        return []

    sentences = _split_sentences(text)
    if not sentences:
        return []

    chunks: list[ChunkData] = []
    current_sentences: list[str] = []
    current_tokens = 0
    chunk_index = 0
    char_offset = 0

    for sentence in sentences:
        sentence_tokens = _count_tokens(sentence)

        if current_tokens + sentence_tokens > TARGET_CHUNK_TOKENS and current_sentences:
            chunk_content = " ".join(current_sentences)
            page_num = _find_page_number(char_offset, pages)
            chunks.append(
                ChunkData(
                    content=chunk_content,
                    chunk_index=chunk_index,
                    page_number=page_num,
                    token_count=_count_tokens(chunk_content),
                )
            )
            chunk_index += 1
            char_offset += len(chunk_content) + 1

            # Keep overlap: take last N tokens worth of sentences
            overlap_sentences: list[str] = []
            overlap_count = 0
            for s in reversed(current_sentences):
                s_tokens = _count_tokens(s)
                if overlap_count + s_tokens > OVERLAP_TOKENS:
                    break
                overlap_sentences.insert(0, s)
                overlap_count += s_tokens

            current_sentences = overlap_sentences
            current_tokens = overlap_count

        current_sentences.append(sentence)
        current_tokens += sentence_tokens

    # Final chunk
    if current_sentences:
        chunk_content = " ".join(current_sentences)
        page_num = _find_page_number(char_offset, pages)
        chunks.append(
            ChunkData(
                content=chunk_content,
                chunk_index=chunk_index,
                page_number=page_num,
                token_count=_count_tokens(chunk_content),
            )
        )

    return chunks
```

- [ ] **Step 4: Run tests — should pass**

```bash
cd backend && python -m pytest tests/test_chunker.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/chunker.py backend/tests/test_chunker.py
git commit -m "feat: add text chunker with sentence boundary alignment and overlap"
```

---

## Task 2: Document Parser

**Files:**
- Create: `backend/app/services/parser.py`
- Create: `backend/tests/test_parser.py`

- [ ] **Step 1: Write parser tests**

```python
# backend/tests/test_parser.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.parser import ParseResult, PageContent, parse_document


class TestParseDocument:
    @pytest.mark.asyncio
    @patch("app.services.parser._parse_with_docling")
    async def test_parse_pdf(self, mock_docling):
        mock_docling.return_value = ParseResult(
            text="Hello from PDF.",
            pages=[PageContent(page_number=1, text="Hello from PDF.")],
            word_count=3,
            page_count=1,
        )
        result = await parse_document(b"fake-pdf-bytes", "pdf", "test.pdf")
        assert result.text == "Hello from PDF."
        assert result.page_count == 1
        assert result.word_count == 3
        mock_docling.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.services.parser._parse_with_docling")
    async def test_parse_docx(self, mock_docling):
        mock_docling.return_value = ParseResult(
            text="Hello from DOCX.",
            pages=[PageContent(page_number=1, text="Hello from DOCX.")],
            word_count=3,
            page_count=1,
        )
        result = await parse_document(b"fake-docx-bytes", "docx", "test.docx")
        assert result.text == "Hello from DOCX."
        mock_docling.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.services.parser._parse_with_docling")
    async def test_parse_pptx(self, mock_docling):
        mock_docling.return_value = ParseResult(
            text="Slide content.",
            pages=[PageContent(page_number=1, text="Slide content.")],
            word_count=2,
            page_count=1,
        )
        result = await parse_document(b"fake-pptx-bytes", "pptx", "test.pptx")
        assert result.text == "Slide content."
        mock_docling.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.services.parser._transcribe_with_whisper")
    async def test_parse_mp3(self, mock_whisper):
        mock_whisper.return_value = ParseResult(
            text="Transcribed audio.",
            pages=[],
            word_count=2,
            page_count=0,
        )
        result = await parse_document(b"fake-mp3-bytes", "mp3", "lecture.mp3")
        assert result.text == "Transcribed audio."
        assert result.page_count == 0
        mock_whisper.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.services.parser._transcribe_with_whisper")
    async def test_parse_mp4(self, mock_whisper):
        mock_whisper.return_value = ParseResult(
            text="Transcribed video.",
            pages=[],
            word_count=2,
            page_count=0,
        )
        result = await parse_document(b"fake-mp4-bytes", "mp4", "lecture.mp4")
        assert result.text == "Transcribed video."
        mock_whisper.assert_called_once()

    @pytest.mark.asyncio
    async def test_unsupported_type_raises(self):
        with pytest.raises(ValueError, match="Unsupported file type"):
            await parse_document(b"bytes", "exe", "bad.exe")
```

- [ ] **Step 2: Run tests — should fail**

```bash
cd backend && python -m pytest tests/test_parser.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.parser'`

- [ ] **Step 3: Implement parser.py**

```python
# backend/app/services/parser.py
from __future__ import annotations

import asyncio
import io
import logging
import tempfile
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class PageContent:
    page_number: int
    text: str


@dataclass
class ParseResult:
    text: str
    pages: list[PageContent]
    word_count: int
    page_count: int


DOCUMENT_TYPES = {"pdf", "docx", "pptx"}
AUDIO_TYPES = {"mp3", "mp4"}


async def parse_document(
    file_data: bytes, file_type: str, filename: str
) -> ParseResult:
    if file_type in DOCUMENT_TYPES:
        return await _parse_with_docling(file_data, file_type, filename)
    elif file_type in AUDIO_TYPES:
        return await _transcribe_with_whisper(file_data, file_type, filename)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")


async def _parse_with_docling(
    file_data: bytes, file_type: str, filename: str
) -> ParseResult:
    from docling.document_converter import DocumentConverter

    def _run_docling() -> ParseResult:
        with tempfile.NamedTemporaryFile(suffix=f".{file_type}", delete=True) as tmp:
            tmp.write(file_data)
            tmp.flush()

            converter = DocumentConverter()
            result = converter.convert(tmp.name)
            doc = result.document

            full_text = doc.export_to_markdown()
            pages: list[PageContent] = []

            # Docling provides page-level access via items
            page_texts: dict[int, list[str]] = {}
            for item, _level in doc.iterate_items():
                prov = getattr(item, "prov", None)
                if prov:
                    for p in prov:
                        page_no = p.page_no
                        text = getattr(item, "text", "") or ""
                        if text.strip():
                            page_texts.setdefault(page_no, []).append(text)

            for page_no in sorted(page_texts.keys()):
                page_text = "\n".join(page_texts[page_no])
                pages.append(PageContent(page_number=page_no, text=page_text))

            word_count = len(full_text.split())
            page_count = len(pages) if pages else 1

            return ParseResult(
                text=full_text,
                pages=pages,
                word_count=word_count,
                page_count=page_count,
            )

    return await asyncio.to_thread(_run_docling)


async def _transcribe_with_whisper(
    file_data: bytes, file_type: str, filename: str
) -> ParseResult:
    import openai

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    audio_file = io.BytesIO(file_data)
    audio_file.name = filename

    transcript = await client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        response_format="text",
    )

    text = str(transcript).strip()
    word_count = len(text.split())

    return ParseResult(
        text=text,
        pages=[],
        word_count=word_count,
        page_count=0,
    )
```

- [ ] **Step 4: Run tests — should pass**

```bash
cd backend && python -m pytest tests/test_parser.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/parser.py backend/tests/test_parser.py
git commit -m "feat: add document parser with Docling and Whisper support"
```

---

## Task 3: Embedder Service

**Files:**
- Create: `backend/app/services/embedder.py`
- Create: `backend/tests/test_embedder.py`

- [ ] **Step 1: Write embedder tests**

```python
# backend/tests/test_embedder.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.embedder import embed_texts, embed_query


class TestEmbedTexts:
    @pytest.mark.asyncio
    @patch("app.services.embedder._get_client")
    async def test_embed_single_text(self, mock_get_client):
        mock_client = AsyncMock()
        mock_embedding = MagicMock()
        mock_embedding.embedding = [0.1] * 1536
        mock_client.embeddings.create.return_value = MagicMock(data=[mock_embedding])
        mock_get_client.return_value = mock_client

        result = await embed_texts(["Hello world"])
        assert len(result) == 1
        assert len(result[0]) == 1536
        mock_client.embeddings.create.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.services.embedder._get_client")
    async def test_embed_multiple_texts(self, mock_get_client):
        mock_client = AsyncMock()
        embeddings = [MagicMock(embedding=[0.1 * i] * 1536) for i in range(3)]
        mock_client.embeddings.create.return_value = MagicMock(data=embeddings)
        mock_get_client.return_value = mock_client

        result = await embed_texts(["Text 1", "Text 2", "Text 3"])
        assert len(result) == 3

    @pytest.mark.asyncio
    @patch("app.services.embedder._get_client")
    async def test_embed_batches_large_input(self, mock_get_client):
        mock_client = AsyncMock()
        # 150 texts should require 2 batches (100 + 50)
        batch_1 = [MagicMock(embedding=[0.1] * 1536) for _ in range(100)]
        batch_2 = [MagicMock(embedding=[0.2] * 1536) for _ in range(50)]
        mock_client.embeddings.create.side_effect = [
            MagicMock(data=batch_1),
            MagicMock(data=batch_2),
        ]
        mock_get_client.return_value = mock_client

        texts = [f"Text {i}" for i in range(150)]
        result = await embed_texts(texts)
        assert len(result) == 150
        assert mock_client.embeddings.create.call_count == 2

    @pytest.mark.asyncio
    @patch("app.services.embedder._get_client")
    async def test_embed_empty_list(self, mock_get_client):
        result = await embed_texts([])
        assert result == []


class TestEmbedQuery:
    @pytest.mark.asyncio
    @patch("app.services.embedder.embed_texts")
    async def test_embed_query_returns_single_vector(self, mock_embed_texts):
        mock_embed_texts.return_value = [[0.5] * 1536]
        result = await embed_query("What is machine learning?")
        assert len(result) == 1536
        mock_embed_texts.assert_called_once_with(["What is machine learning?"])
```

- [ ] **Step 2: Run tests — should fail**

```bash
cd backend && python -m pytest tests/test_embedder.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement embedder.py**

```python
# backend/app/services/embedder.py
from __future__ import annotations

import openai

from app.config import settings

EMBEDDING_MODEL = "text-embedding-3-large"
BATCH_SIZE = 100

_client: openai.AsyncOpenAI | None = None


def _get_client() -> openai.AsyncOpenAI:
    global _client
    if _client is None:
        _client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    client = _get_client()
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        response = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch,
        )
        all_embeddings.extend([item.embedding for item in response.data])

    return all_embeddings


async def embed_query(query: str) -> list[float]:
    results = await embed_texts([query])
    return results[0]
```

- [ ] **Step 4: Run tests — should pass**

```bash
cd backend && python -m pytest tests/test_embedder.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/embedder.py backend/tests/test_embedder.py
git commit -m "feat: add OpenAI embedding service with batching"
```

---

## Task 4: Retriever Service

**Files:**
- Create: `backend/app/services/retriever.py`
- Create: `backend/tests/test_retriever.py`

- [ ] **Step 1: Write retriever tests**

```python
# backend/tests/test_retriever.py
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.course import Course
from app.models.user import User
from app.services.retriever import RetrievedChunk, retrieve_chunks


@pytest_asyncio.fixture
async def course_with_chunks(db_session: AsyncSession, test_instructor: User):
    course = Course(
        name="Test Course",
        code="TEST101",
        language="english",
        instructor_id=test_instructor.id,
    )
    db_session.add(course)
    await db_session.flush()

    doc_id = uuid.uuid4()

    # Create 3 chunks with known embeddings
    for i in range(3):
        embedding = [0.0] * 1536
        embedding[i] = 1.0  # Each chunk has a distinct embedding
        chunk = Chunk(
            document_id=doc_id,
            course_id=course.id,
            content=f"Chunk {i} content about topic {i}",
            chunk_index=i,
            page_number=1,
            token_count=7,
            embedding=embedding,
        )
        db_session.add(chunk)

    await db_session.commit()
    return course


class TestRetrieveChunks:
    @pytest.mark.asyncio
    async def test_retrieve_returns_results(self, db_session, course_with_chunks):
        query_embedding = [0.0] * 1536
        query_embedding[0] = 1.0  # Should match chunk 0 best

        results = await retrieve_chunks(
            db=db_session,
            course_id=course_with_chunks.id,
            query_embedding=query_embedding,
            top_k=3,
        )
        assert len(results) == 3
        assert isinstance(results[0], RetrievedChunk)
        assert "Chunk 0" in results[0].content  # Best match first

    @pytest.mark.asyncio
    async def test_retrieve_respects_top_k(self, db_session, course_with_chunks):
        query_embedding = [0.0] * 1536
        query_embedding[0] = 1.0

        results = await retrieve_chunks(
            db=db_session,
            course_id=course_with_chunks.id,
            query_embedding=query_embedding,
            top_k=1,
        )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_retrieve_filters_by_course(self, db_session, course_with_chunks):
        other_course_id = uuid.uuid4()
        query_embedding = [0.0] * 1536
        query_embedding[0] = 1.0

        results = await retrieve_chunks(
            db=db_session,
            course_id=other_course_id,
            query_embedding=query_embedding,
            top_k=10,
        )
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_retrieve_returns_similarity_scores(self, db_session, course_with_chunks):
        query_embedding = [0.0] * 1536
        query_embedding[0] = 1.0

        results = await retrieve_chunks(
            db=db_session,
            course_id=course_with_chunks.id,
            query_embedding=query_embedding,
            top_k=3,
        )
        for r in results:
            assert 0.0 <= r.similarity_score <= 1.0
        # Results should be sorted by similarity descending
        scores = [r.similarity_score for r in results]
        assert scores == sorted(scores, reverse=True)
```

- [ ] **Step 2: Run tests — should fail**

```bash
cd backend && python -m pytest tests/test_retriever.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement retriever.py**

```python
# backend/app/services/retriever.py
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    content: str
    document_id: uuid.UUID
    page_number: int | None
    similarity_score: float


async def retrieve_chunks(
    db: AsyncSession,
    course_id: uuid.UUID,
    query_embedding: list[float],
    top_k: int = 10,
    document_ids: list[uuid.UUID] | None = None,
) -> list[RetrievedChunk]:
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    # 1 - cosine distance = cosine similarity
    similarity_expr = text(
        f"1 - (chunks.embedding <=> '{embedding_str}'::vector) AS similarity"
    )

    stmt = (
        select(Chunk, similarity_expr)
        .where(Chunk.course_id == course_id)
        .where(Chunk.embedding.isnot(None))
    )

    if document_ids:
        stmt = stmt.where(Chunk.document_id.in_(document_ids))

    stmt = stmt.order_by(text("similarity DESC")).limit(top_k)

    result = await db.execute(stmt)
    rows = result.all()

    return [
        RetrievedChunk(
            chunk_id=chunk.id,
            content=chunk.content,
            document_id=chunk.document_id,
            page_number=chunk.page_number,
            similarity_score=float(similarity),
        )
        for chunk, similarity in rows
    ]
```

- [ ] **Step 4: Run tests — should pass**

```bash
cd backend && python -m pytest tests/test_retriever.py -v
```

Expected: All tests PASS. (Requires test database with pgvector extension.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/retriever.py backend/tests/test_retriever.py
git commit -m "feat: add pgvector cosine similarity retriever"
```

---

## Task 5: LLM Generator Service

**Files:**
- Create: `backend/app/services/generator.py`
- Create: `backend/tests/test_generator.py`

- [ ] **Step 1: Write generator tests**

```python
# backend/tests/test_generator.py
import json
import uuid

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.generator import (
    GeneratedFlashcard,
    GeneratedQuestion,
    generate_flashcards,
    generate_quiz,
    generate_summary,
)
from app.services.retriever import RetrievedChunk

SAMPLE_CHUNKS = [
    RetrievedChunk(
        chunk_id=uuid.uuid4(),
        content="Photosynthesis is the process by which plants convert sunlight into energy.",
        document_id=uuid.uuid4(),
        page_number=1,
        similarity_score=0.92,
    ),
    RetrievedChunk(
        chunk_id=uuid.uuid4(),
        content="Chlorophyll is the green pigment that absorbs light energy.",
        document_id=uuid.uuid4(),
        page_number=2,
        similarity_score=0.87,
    ),
]


class TestGenerateQuiz:
    @pytest.mark.asyncio
    @patch("app.services.generator._call_llm")
    async def test_generates_questions(self, mock_llm):
        mock_llm.return_value = json.dumps([
            {
                "question_text": "What is photosynthesis?",
                "options": {"A": "Plant eating", "B": "Light to energy", "C": "Water absorption", "D": "Root growth"},
                "correct_answer": "B",
                "explanation": "Photosynthesis converts sunlight into energy.",
            }
        ])
        result = await generate_quiz(SAMPLE_CHUNKS, num_questions=1)
        assert len(result) == 1
        assert isinstance(result[0], GeneratedQuestion)
        assert result[0].question_text == "What is photosynthesis?"
        assert result[0].correct_answer == "B"

    @pytest.mark.asyncio
    @patch("app.services.generator._call_llm")
    async def test_handles_invalid_json_with_fallback(self, mock_llm):
        mock_llm.side_effect = [
            "not valid json",  # primary model fails
            json.dumps([{
                "question_text": "Fallback question?",
                "options": {"A": "Yes", "B": "No", "C": "Maybe", "D": "None"},
                "correct_answer": "A",
                "explanation": "Explanation.",
            }]),
        ]
        result = await generate_quiz(SAMPLE_CHUNKS, num_questions=1)
        assert len(result) == 1
        assert mock_llm.call_count == 2


class TestGenerateSummary:
    @pytest.mark.asyncio
    @patch("app.services.generator._call_llm")
    async def test_generates_summary_text(self, mock_llm):
        mock_llm.return_value = "Photosynthesis is a process where plants use sunlight."
        result = await generate_summary(SAMPLE_CHUNKS)
        assert isinstance(result, str)
        assert len(result) > 0


class TestGenerateFlashcards:
    @pytest.mark.asyncio
    @patch("app.services.generator._call_llm")
    async def test_generates_flashcards(self, mock_llm):
        mock_llm.return_value = json.dumps([
            {"front": "What is photosynthesis?", "back": "The process of converting sunlight to energy."},
            {"front": "What is chlorophyll?", "back": "A green pigment that absorbs light."},
        ])
        result = await generate_flashcards(SAMPLE_CHUNKS, num_cards=2)
        assert len(result) == 2
        assert isinstance(result[0], GeneratedFlashcard)
        assert result[0].front == "What is photosynthesis?"
```

- [ ] **Step 2: Run tests — should fail**

```bash
cd backend && python -m pytest tests/test_generator.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement generator.py**

```python
# backend/app/services/generator.py
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import openai

from app.config import settings
from app.services.retriever import RetrievedChunk

logger = logging.getLogger(__name__)


@dataclass
class GeneratedQuestion:
    question_text: str
    options: dict[str, str]
    correct_answer: str
    explanation: str


@dataclass
class GeneratedFlashcard:
    front: str
    back: str


def _build_context(chunks: list[RetrievedChunk]) -> str:
    parts = []
    for i, chunk in enumerate(chunks):
        source = f"[Source {i + 1}, page {chunk.page_number}]" if chunk.page_number else f"[Source {i + 1}]"
        parts.append(f"{source}\n{chunk.content}")
    return "\n\n".join(parts)


async def _call_llm(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
    client = openai.AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )
    used_model = model or settings.openrouter_primary_model
    response = await client.chat.completions.create(
        model=used_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
    )
    return response.choices[0].message.content or ""


def _parse_json_response(text: str) -> list[dict]:
    text = text.strip()
    # Try to extract JSON array from markdown code blocks
    if "```" in text:
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            text = text[start:end]
    return json.loads(text)


async def generate_quiz(
    chunks: list[RetrievedChunk],
    num_questions: int = 5,
    quiz_type: str = "multiple_choice",
    language: str = "english",
) -> list[GeneratedQuestion]:
    context = _build_context(chunks)
    system_prompt = f"""You are an expert quiz generator for university courses.
Generate exactly {num_questions} {quiz_type} questions based on the provided course material.
Language: {language}.

Return ONLY a JSON array with this exact structure (no markdown, no explanation):
[
  {{
    "question_text": "...",
    "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
    "correct_answer": "A",
    "explanation": "Brief explanation of why this is correct."
  }}
]"""

    user_prompt = f"Generate {num_questions} questions from this material:\n\n{context}"

    # Try primary model, fallback on parse error
    for model in [None, settings.openrouter_fallback_model]:
        try:
            raw = await _call_llm(system_prompt, user_prompt, model=model)
            parsed = _parse_json_response(raw)
            return [
                GeneratedQuestion(
                    question_text=q["question_text"],
                    options=q["options"],
                    correct_answer=q["correct_answer"],
                    explanation=q.get("explanation", ""),
                )
                for q in parsed[:num_questions]
            ]
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"LLM response parse failed (model={model}): {e}")
            continue

    raise ValueError("Both primary and fallback models failed to generate valid quiz JSON")


async def generate_summary(
    chunks: list[RetrievedChunk],
    language: str = "english",
) -> str:
    context = _build_context(chunks)
    system_prompt = f"""You are an expert academic summarizer. Summarize the provided course material
into a clear, well-structured summary. Language: {language}. Use markdown formatting."""

    user_prompt = f"Summarize this material:\n\n{context}"
    return await _call_llm(system_prompt, user_prompt)


async def generate_flashcards(
    chunks: list[RetrievedChunk],
    num_cards: int = 10,
    language: str = "english",
) -> list[GeneratedFlashcard]:
    context = _build_context(chunks)
    system_prompt = f"""You are an expert flashcard creator for university courses.
Generate exactly {num_cards} flashcards based on the provided course material.
Language: {language}.

Return ONLY a JSON array with this exact structure (no markdown, no explanation):
[
  {{
    "front": "Question or concept",
    "back": "Answer or definition"
  }}
]"""

    user_prompt = f"Generate {num_cards} flashcards from this material:\n\n{context}"

    for model in [None, settings.openrouter_fallback_model]:
        try:
            raw = await _call_llm(system_prompt, user_prompt, model=model)
            parsed = _parse_json_response(raw)
            return [
                GeneratedFlashcard(front=c["front"], back=c["back"])
                for c in parsed[:num_cards]
            ]
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"LLM response parse failed (model={model}): {e}")
            continue

    raise ValueError("Both primary and fallback models failed to generate valid flashcard JSON")
```

- [ ] **Step 4: Run tests — should pass**

```bash
cd backend && python -m pytest tests/test_generator.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/generator.py backend/tests/test_generator.py
git commit -m "feat: add LLM generator for quizzes, summaries, and flashcards"
```

---

## Task 6: Wire Worker Pipeline

Connect the existing worker to the new services to process uploaded documents end-to-end.

**Files:**
- Create: `backend/app/services/pipeline.py`
- Create: `backend/tests/test_pipeline.py`
- Modify: `backend/app/services/worker.py`

- [ ] **Step 1: Write pipeline tests**

```python
# backend/tests/test_pipeline.py
import uuid

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.pipeline import process_document_pipeline


class TestProcessDocumentPipeline:
    @pytest.mark.asyncio
    @patch("app.services.pipeline.embed_texts")
    @patch("app.services.pipeline.chunk_text")
    @patch("app.services.pipeline.parse_document")
    @patch("app.services.pipeline.download_file")
    async def test_full_pipeline(
        self, mock_download, mock_parse, mock_chunk, mock_embed
    ):
        from app.services.parser import PageContent, ParseResult
        from app.services.chunker import ChunkData

        doc_id = uuid.uuid4()
        course_id = uuid.uuid4()

        mock_download.return_value = b"fake file content"
        mock_parse.return_value = ParseResult(
            text="Parsed text content here.",
            pages=[PageContent(page_number=1, text="Parsed text content here.")],
            word_count=4,
            page_count=1,
        )
        mock_chunk.return_value = [
            ChunkData(content="Parsed text content here.", chunk_index=0, page_number=1, token_count=4),
        ]
        mock_embed.return_value = [[0.1] * 1536]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=MagicMock(
                id=doc_id,
                course_id=course_id,
                r2_key="courses/xxx/documents/yyy/test.pdf",
                file_type="pdf",
                filename="test.pdf",
            ))
        ))

        result = await process_document_pipeline(mock_session, str(doc_id))

        mock_download.assert_called_once()
        mock_parse.assert_called_once()
        mock_chunk.assert_called_once()
        mock_embed.assert_called_once()
        assert result is True

    @pytest.mark.asyncio
    @patch("app.services.pipeline.download_file")
    async def test_pipeline_fails_on_missing_document(self, mock_download):
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=None)
        ))

        with pytest.raises(ValueError, match="Document not found"):
            await process_document_pipeline(mock_session, str(uuid.uuid4()))
```

- [ ] **Step 2: Run tests — should fail**

```bash
cd backend && python -m pytest tests/test_pipeline.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement pipeline.py**

```python
# backend/app/services/pipeline.py
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.document import Document
from app.services.chunker import chunk_text
from app.services.embedder import embed_texts
from app.services.parser import parse_document
from app.services.storage import download_file

logger = logging.getLogger(__name__)


async def process_document_pipeline(
    session: AsyncSession, document_id: str
) -> bool:
    doc_uuid = uuid.UUID(document_id)

    # Fetch document
    result = await session.execute(
        select(Document).where(Document.id == doc_uuid)
    )
    document = result.scalar_one_or_none()
    if not document:
        raise ValueError(f"Document not found: {document_id}")

    # Update status to processing
    document.status = "processing"
    await session.commit()

    try:
        # 1. Download from R2
        logger.info(f"Downloading {document.r2_key}")
        file_data = download_file(document.r2_key)

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

        # 5. Store chunks
        for chunk_data, embedding in zip(chunks, embeddings):
            chunk = Chunk(
                document_id=document.id,
                course_id=document.course_id,
                content=chunk_data.content,
                chunk_index=chunk_data.chunk_index,
                page_number=chunk_data.page_number,
                token_count=chunk_data.token_count,
                embedding=embedding,
            )
            session.add(chunk)

        # 6. Update document metadata
        document.status = "ready"
        document.page_count = parse_result.page_count
        document.word_count = parse_result.word_count
        await session.commit()

        logger.info(f"Document {document_id} processed: {len(chunks)} chunks stored")
        return True

    except Exception as e:
        document.status = "failed"
        await session.commit()
        raise
```

- [ ] **Step 4: Update worker.py to call pipeline**

Replace the placeholder `process_task` function in `backend/app/services/worker.py`:

Find:
```python
async def process_task(task: Task) -> None:
    if task.task_type == "process_document":
        logger.info(f"Document processing task {task.id} — handler not yet implemented")
    else:
        raise ValueError(f"Unknown task type: {task.task_type}")
```

Replace with:
```python
async def process_task(session: AsyncSession, task: Task) -> None:
    if task.task_type == "process_document":
        from app.services.pipeline import process_document_pipeline
        document_id = task.payload.get("document_id")
        if not document_id:
            raise ValueError("Missing document_id in task payload")
        await process_document_pipeline(session, document_id)
    else:
        raise ValueError(f"Unknown task type: {task.task_type}")
```

Also update the `worker_loop` to pass `session` to `process_task`. Find:
```python
                        await process_task(task)
```

Replace with:
```python
                        await process_task(session, task)
```

- [ ] **Step 5: Run tests — should pass**

```bash
cd backend && python -m pytest tests/test_pipeline.py -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/pipeline.py backend/app/services/worker.py backend/tests/test_pipeline.py
git commit -m "feat: wire document processing pipeline into task worker"
```

---

## Task 7: Pydantic Schemas for RAG, Quiz, and Flashcards

**Files:**
- Create: `backend/app/schemas/rag.py`
- Create: `backend/app/schemas/quiz.py`
- Create: `backend/app/schemas/flashcard.py`
- Modify: `backend/app/schemas/__init__.py`

- [ ] **Step 1: Create schemas/rag.py**

```python
# backend/app/schemas/rag.py
import uuid

from pydantic import BaseModel, Field


class RAGQueryRequest(BaseModel):
    course_id: uuid.UUID
    query: str
    top_k: int = Field(default=10, ge=1, le=50)


class ChunkResult(BaseModel):
    chunk_id: uuid.UUID
    content: str
    document_id: uuid.UUID
    page_number: int | None
    similarity_score: float

    model_config = {"from_attributes": True}


class RAGQueryResponse(BaseModel):
    chunks: list[ChunkResult]


class GenerateQuizRequest(BaseModel):
    course_id: uuid.UUID
    title: str
    document_ids: list[uuid.UUID] | None = None
    num_questions: int = Field(default=5, ge=1, le=30)


class GenerateSummaryRequest(BaseModel):
    course_id: uuid.UUID
    document_ids: list[uuid.UUID] | None = None


class GenerateFlashcardsRequest(BaseModel):
    course_id: uuid.UUID
    title: str
    document_ids: list[uuid.UUID] | None = None
    num_cards: int = Field(default=10, ge=1, le=50)
```

- [ ] **Step 2: Create schemas/quiz.py**

```python
# backend/app/schemas/quiz.py
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class QuestionResponse(BaseModel):
    id: uuid.UUID
    question_index: int
    type: str
    question_text: str
    options: dict | None
    explanation: str | None
    # Note: correct_answer intentionally omitted for students

    model_config = {"from_attributes": True}


class QuestionWithAnswerResponse(QuestionResponse):
    correct_answer: str

    model_config = {"from_attributes": True}


class QuizResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    description: str | None
    quiz_type: str
    is_published: bool
    question_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class QuizDetailResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    description: str | None
    quiz_type: str
    is_published: bool
    questions: list[QuestionResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


class QuizUpdate(BaseModel):
    title: str | None = None
    description: str | None = None


class QuizAttemptCreate(BaseModel):
    answers: dict[str, str]  # question_id -> selected_answer
    time_taken_seconds: int | None = None


class QuizAttemptResult(BaseModel):
    question_id: uuid.UUID
    question_text: str
    selected_answer: str
    correct_answer: str
    is_correct: bool
    explanation: str | None


class QuizAttemptResponse(BaseModel):
    id: uuid.UUID
    quiz_id: uuid.UUID
    score: Decimal
    total_questions: int
    correct_count: int
    time_taken_seconds: int | None
    results: list[QuizAttemptResult]
    completed_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 3: Create schemas/flashcard.py**

```python
# backend/app/schemas/flashcard.py
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class FlashcardCardResponse(BaseModel):
    id: uuid.UUID
    card_index: int
    front: str
    back: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FlashcardSetResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    card_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class FlashcardSetDetailResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    cards: list[FlashcardCardResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


class FlashcardProgressUpdate(BaseModel):
    card_id: uuid.UUID
    quality: int = Field(ge=0, le=5)  # SM-2 quality rating


class FlashcardProgressResponse(BaseModel):
    card_id: uuid.UUID
    ease_factor: Decimal
    interval_days: int
    repetitions: int
    next_review: datetime | None
    last_reviewed: datetime | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Update schemas/__init__.py**

Replace the contents of `backend/app/schemas/__init__.py`:

```python
from app.schemas.common import APIResponse, ErrorDetail, PaginatedResponse, PaginationMeta
from app.schemas.course import CourseCreate, CourseResponse, CourseUpdate, EnrollmentCreate, EnrollmentResponse
from app.schemas.document import DocumentResponse
from app.schemas.flashcard import (
    FlashcardCardResponse,
    FlashcardProgressResponse,
    FlashcardProgressUpdate,
    FlashcardSetDetailResponse,
    FlashcardSetResponse,
)
from app.schemas.quiz import (
    QuestionResponse,
    QuestionWithAnswerResponse,
    QuizAttemptCreate,
    QuizAttemptResponse,
    QuizDetailResponse,
    QuizResponse,
    QuizUpdate,
)
from app.schemas.rag import (
    ChunkResult,
    GenerateFlashcardsRequest,
    GenerateQuizRequest,
    GenerateSummaryRequest,
    RAGQueryRequest,
    RAGQueryResponse,
)
from app.schemas.user import UserResponse
```

- [ ] **Step 5: Verify imports**

```bash
cd backend && python -c "from app.schemas import *; print('All schemas import OK')"
```

Expected: `All schemas import OK`

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/
git commit -m "feat: add Pydantic schemas for RAG, quiz, and flashcard APIs"
```

---

## Task 8: RAG API Endpoints

**Files:**
- Create: `backend/app/api/rag.py`
- Create: `backend/tests/test_api_rag.py`
- Modify: `backend/app/api/__init__.py`

- [ ] **Step 1: Create api/rag.py**

```python
# backend/app/api/rag.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_instructor
from app.models.course import Enrollment
from app.models.flashcard import FlashcardCard, FlashcardSet, FlashcardSetDocument
from app.models.quiz import Question, Quiz, QuizDocument
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.flashcard import FlashcardSetDetailResponse
from app.schemas.quiz import QuizDetailResponse
from app.schemas.rag import (
    ChunkResult,
    GenerateFlashcardsRequest,
    GenerateQuizRequest,
    GenerateSummaryRequest,
    RAGQueryRequest,
    RAGQueryResponse,
)
from app.services.embedder import embed_query
from app.services.generator import generate_flashcards, generate_quiz, generate_summary
from app.services.retriever import retrieve_chunks

router = APIRouter(prefix="/rag", tags=["rag"])


async def _verify_enrollment(
    db: AsyncSession, course_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    result = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == course_id,
            Enrollment.user_id == user_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enrolled in this course",
        )


@router.post("/query", response_model=APIResponse[RAGQueryResponse])
async def rag_query(
    body: RAGQueryRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _verify_enrollment(db, body.course_id, user.id)

    query_embedding = await embed_query(body.query)
    chunks = await retrieve_chunks(
        db=db,
        course_id=body.course_id,
        query_embedding=query_embedding,
        top_k=body.top_k,
    )

    return APIResponse(
        success=True,
        data=RAGQueryResponse(
            chunks=[
                ChunkResult(
                    chunk_id=c.chunk_id,
                    content=c.content,
                    document_id=c.document_id,
                    page_number=c.page_number,
                    similarity_score=c.similarity_score,
                )
                for c in chunks
            ]
        ),
    )


@router.post("/generate-quiz", response_model=APIResponse[QuizDetailResponse], status_code=201)
async def rag_generate_quiz(
    body: GenerateQuizRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    await _verify_enrollment(db, body.course_id, user.id)

    # Build a query from the title to retrieve relevant chunks
    query_embedding = await embed_query(body.title)
    chunks = await retrieve_chunks(
        db=db,
        course_id=body.course_id,
        query_embedding=query_embedding,
        top_k=15,
        document_ids=body.document_ids,
    )

    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No processed documents found for this course",
        )

    # Generate questions via LLM
    generated = await generate_quiz(chunks, num_questions=body.num_questions)

    # Store quiz + questions in DB
    quiz = Quiz(
        course_id=body.course_id,
        created_by=user.id,
        title=body.title,
        quiz_type="practice",
    )
    db.add(quiz)
    await db.flush()

    # Link source documents
    doc_ids_used = set()
    for chunk in chunks:
        doc_ids_used.add(chunk.document_id)
    for doc_id in doc_ids_used:
        db.add(QuizDocument(quiz_id=quiz.id, document_id=doc_id))

    # Create question rows
    for i, q in enumerate(generated):
        question = Question(
            quiz_id=quiz.id,
            question_index=i,
            type="multiple_choice",
            question_text=q.question_text,
            options=q.options,
            correct_answer=q.correct_answer,
            explanation=q.explanation,
        )
        db.add(question)

    await db.commit()
    await db.refresh(quiz)

    # Load questions for response
    result = await db.execute(
        select(Question).where(Question.quiz_id == quiz.id).order_by(Question.question_index)
    )
    questions = result.scalars().all()

    return APIResponse(
        success=True,
        data=QuizDetailResponse(
            id=quiz.id,
            course_id=quiz.course_id,
            title=quiz.title,
            description=quiz.description,
            quiz_type=quiz.quiz_type,
            is_published=quiz.is_published,
            questions=questions,
            created_at=quiz.created_at,
        ),
    )


@router.post("/generate-summary", response_model=APIResponse[str])
async def rag_generate_summary(
    body: GenerateSummaryRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _verify_enrollment(db, body.course_id, user.id)

    query_embedding = await embed_query("comprehensive summary of course material")
    chunks = await retrieve_chunks(
        db=db,
        course_id=body.course_id,
        query_embedding=query_embedding,
        top_k=20,
        document_ids=body.document_ids,
    )

    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No processed documents found for this course",
        )

    summary = await generate_summary(chunks)
    return APIResponse(success=True, data=summary)


@router.post("/generate-flashcards", response_model=APIResponse[FlashcardSetDetailResponse], status_code=201)
async def rag_generate_flashcards(
    body: GenerateFlashcardsRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _verify_enrollment(db, body.course_id, user.id)

    query_embedding = await embed_query(body.title)
    chunks = await retrieve_chunks(
        db=db,
        course_id=body.course_id,
        query_embedding=query_embedding,
        top_k=15,
        document_ids=body.document_ids,
    )

    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No processed documents found for this course",
        )

    generated = await generate_flashcards(chunks, num_cards=body.num_cards)

    flashcard_set = FlashcardSet(
        course_id=body.course_id,
        created_by=user.id,
        title=body.title,
    )
    db.add(flashcard_set)
    await db.flush()

    # Link source documents
    doc_ids_used = set()
    for chunk in chunks:
        doc_ids_used.add(chunk.document_id)
    for doc_id in doc_ids_used:
        db.add(FlashcardSetDocument(flashcard_set_id=flashcard_set.id, document_id=doc_id))

    for i, card in enumerate(generated):
        db.add(FlashcardCard(
            flashcard_set_id=flashcard_set.id,
            card_index=i,
            front=card.front,
            back=card.back,
        ))

    await db.commit()
    await db.refresh(flashcard_set)

    # Load cards for response
    result = await db.execute(
        select(FlashcardCard)
        .where(FlashcardCard.flashcard_set_id == flashcard_set.id)
        .order_by(FlashcardCard.card_index)
    )
    cards = result.scalars().all()

    return APIResponse(
        success=True,
        data=FlashcardSetDetailResponse(
            id=flashcard_set.id,
            course_id=flashcard_set.course_id,
            title=flashcard_set.title,
            cards=cards,
            created_at=flashcard_set.created_at,
        ),
    )
```

- [ ] **Step 2: Update api/__init__.py**

Replace the contents of `backend/app/api/__init__.py`:

```python
from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.canvas import router as canvas_router
from app.api.courses import router as courses_router
from app.api.documents import router as documents_router
from app.api.rag import router as rag_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(courses_router)
api_router.include_router(documents_router)
api_router.include_router(canvas_router)
api_router.include_router(rag_router)
```

- [ ] **Step 3: Verify imports**

```bash
cd backend && python -c "from app.api import api_router; print('Router OK')"
```

Expected: `Router OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/rag.py backend/app/api/__init__.py
git commit -m "feat: add RAG API endpoints for query, quiz, summary, and flashcard generation"
```

---

## Task 9: Quiz CRUD API

**Files:**
- Create: `backend/app/api/quizzes.py`
- Modify: `backend/app/api/__init__.py`

- [ ] **Step 1: Create api/quizzes.py**

```python
# backend/app/api/quizzes.py
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_instructor
from app.models.course import Enrollment
from app.models.quiz import Question, Quiz, QuizAttempt
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.quiz import (
    QuizAttemptCreate,
    QuizAttemptResponse,
    QuizAttemptResult,
    QuizDetailResponse,
    QuizResponse,
    QuizUpdate,
)

router = APIRouter(tags=["quizzes"])


@router.get("/courses/{course_id}/quizzes", response_model=APIResponse[list[QuizResponse]])
async def list_quizzes(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Verify enrollment
    enrollment = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == course_id, Enrollment.user_id == user.id
        )
    )
    if not enrollment.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enrolled")

    stmt = select(Quiz).where(Quiz.course_id == course_id, Quiz.deleted_at.is_(None))

    # Students only see published quizzes
    if user.role == "student":
        stmt = stmt.where(Quiz.is_published.is_(True))

    result = await db.execute(stmt.order_by(Quiz.created_at.desc()))
    quizzes = result.scalars().all()

    quiz_responses = []
    for q in quizzes:
        count_result = await db.execute(
            select(func.count()).where(Question.quiz_id == q.id)
        )
        question_count = count_result.scalar() or 0
        quiz_responses.append(
            QuizResponse(
                id=q.id,
                course_id=q.course_id,
                title=q.title,
                description=q.description,
                quiz_type=q.quiz_type,
                is_published=q.is_published,
                question_count=question_count,
                created_at=q.created_at,
            )
        )

    return APIResponse(success=True, data=quiz_responses)


@router.get("/quizzes/{quiz_id}", response_model=APIResponse[QuizDetailResponse])
async def get_quiz(
    quiz_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Quiz).where(Quiz.id == quiz_id, Quiz.deleted_at.is_(None))
    )
    quiz = result.scalar_one_or_none()
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")

    # Verify enrollment
    enrollment = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == quiz.course_id, Enrollment.user_id == user.id
        )
    )
    if not enrollment.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enrolled")

    # Students can only see published quizzes
    if user.role == "student" and not quiz.is_published:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")

    questions_result = await db.execute(
        select(Question).where(Question.quiz_id == quiz.id).order_by(Question.question_index)
    )
    questions = questions_result.scalars().all()

    return APIResponse(
        success=True,
        data=QuizDetailResponse(
            id=quiz.id,
            course_id=quiz.course_id,
            title=quiz.title,
            description=quiz.description,
            quiz_type=quiz.quiz_type,
            is_published=quiz.is_published,
            questions=questions,
            created_at=quiz.created_at,
        ),
    )


@router.put("/quizzes/{quiz_id}", response_model=APIResponse[QuizDetailResponse])
async def update_quiz(
    quiz_id: uuid.UUID,
    body: QuizUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(Quiz).where(
            Quiz.id == quiz_id,
            Quiz.created_by == user.id,
            Quiz.deleted_at.is_(None),
        )
    )
    quiz = result.scalar_one_or_none()
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(quiz, field, value)

    await db.commit()
    await db.refresh(quiz)

    questions_result = await db.execute(
        select(Question).where(Question.quiz_id == quiz.id).order_by(Question.question_index)
    )
    questions = questions_result.scalars().all()

    return APIResponse(
        success=True,
        data=QuizDetailResponse(
            id=quiz.id,
            course_id=quiz.course_id,
            title=quiz.title,
            description=quiz.description,
            quiz_type=quiz.quiz_type,
            is_published=quiz.is_published,
            questions=questions,
            created_at=quiz.created_at,
        ),
    )


@router.delete("/quizzes/{quiz_id}", response_model=APIResponse[None])
async def delete_quiz(
    quiz_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(Quiz).where(
            Quiz.id == quiz_id,
            Quiz.created_by == user.id,
            Quiz.deleted_at.is_(None),
        )
    )
    quiz = result.scalar_one_or_none()
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")

    quiz.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return APIResponse(success=True, data=None)


@router.post("/quizzes/{quiz_id}/publish", response_model=APIResponse[QuizResponse])
async def publish_quiz(
    quiz_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_instructor),
):
    result = await db.execute(
        select(Quiz).where(
            Quiz.id == quiz_id,
            Quiz.created_by == user.id,
            Quiz.deleted_at.is_(None),
        )
    )
    quiz = result.scalar_one_or_none()
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")

    quiz.is_published = True
    await db.commit()
    await db.refresh(quiz)

    count_result = await db.execute(
        select(func.count()).where(Question.quiz_id == quiz.id)
    )
    question_count = count_result.scalar() or 0

    return APIResponse(
        success=True,
        data=QuizResponse(
            id=quiz.id,
            course_id=quiz.course_id,
            title=quiz.title,
            description=quiz.description,
            quiz_type=quiz.quiz_type,
            is_published=quiz.is_published,
            question_count=question_count,
            created_at=quiz.created_at,
        ),
    )


@router.post("/quizzes/{quiz_id}/attempt", response_model=APIResponse[QuizAttemptResponse], status_code=201)
async def submit_quiz_attempt(
    quiz_id: uuid.UUID,
    body: QuizAttemptCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Only students can attempt quizzes
    if user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only students can attempt quizzes"
        )

    result = await db.execute(
        select(Quiz).where(
            Quiz.id == quiz_id,
            Quiz.is_published.is_(True),
            Quiz.deleted_at.is_(None),
        )
    )
    quiz = result.scalar_one_or_none()
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")

    # Verify enrollment
    enrollment = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == quiz.course_id, Enrollment.user_id == user.id
        )
    )
    if not enrollment.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enrolled")

    # Load questions
    questions_result = await db.execute(
        select(Question).where(Question.quiz_id == quiz.id).order_by(Question.question_index)
    )
    questions = questions_result.scalars().all()

    # Grade
    correct_count = 0
    results: list[QuizAttemptResult] = []
    for question in questions:
        selected = body.answers.get(str(question.id), "")
        is_correct = selected == question.correct_answer
        if is_correct:
            correct_count += 1
        results.append(
            QuizAttemptResult(
                question_id=question.id,
                question_text=question.question_text,
                selected_answer=selected,
                correct_answer=question.correct_answer,
                is_correct=is_correct,
                explanation=question.explanation,
            )
        )

    total = len(questions)
    score = Decimal(correct_count) / Decimal(total) * 100 if total > 0 else Decimal(0)
    now = datetime.now(timezone.utc)

    attempt = QuizAttempt(
        quiz_id=quiz.id,
        user_id=user.id,
        answers=body.answers,
        score=score,
        total_questions=total,
        correct_count=correct_count,
        time_taken_seconds=body.time_taken_seconds,
        completed_at=now,
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)

    return APIResponse(
        success=True,
        data=QuizAttemptResponse(
            id=attempt.id,
            quiz_id=attempt.quiz_id,
            score=attempt.score,
            total_questions=attempt.total_questions,
            correct_count=attempt.correct_count,
            time_taken_seconds=attempt.time_taken_seconds,
            results=results,
            completed_at=attempt.completed_at,
        ),
    )
```

- [ ] **Step 2: Update api/__init__.py to add quizzes router**

Add to `backend/app/api/__init__.py`:

```python
from app.api.quizzes import router as quizzes_router
```

And add:

```python
api_router.include_router(quizzes_router)
```

- [ ] **Step 3: Verify imports**

```bash
cd backend && python -c "from app.api import api_router; print('Router OK')"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/quizzes.py backend/app/api/__init__.py
git commit -m "feat: add quiz CRUD, publish, and attempt submission endpoints"
```

---

## Task 10: Flashcard CRUD API

**Files:**
- Create: `backend/app/api/flashcards.py`
- Modify: `backend/app/api/__init__.py`

- [ ] **Step 1: Create api/flashcards.py**

```python
# backend/app/api/flashcards.py
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.course import Enrollment
from app.models.flashcard import FlashcardCard, FlashcardProgress, FlashcardSet
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.flashcard import (
    FlashcardCardResponse,
    FlashcardProgressResponse,
    FlashcardProgressUpdate,
    FlashcardSetDetailResponse,
    FlashcardSetResponse,
)

router = APIRouter(tags=["flashcards"])


@router.get("/courses/{course_id}/flashcard-sets", response_model=APIResponse[list[FlashcardSetResponse]])
async def list_flashcard_sets(
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
        select(FlashcardSet)
        .where(FlashcardSet.course_id == course_id, FlashcardSet.deleted_at.is_(None))
        .order_by(FlashcardSet.created_at.desc())
    )
    sets = result.scalars().all()

    set_responses = []
    for s in sets:
        count_result = await db.execute(
            select(func.count()).where(FlashcardCard.flashcard_set_id == s.id)
        )
        card_count = count_result.scalar() or 0
        set_responses.append(
            FlashcardSetResponse(
                id=s.id,
                course_id=s.course_id,
                title=s.title,
                card_count=card_count,
                created_at=s.created_at,
            )
        )

    return APIResponse(success=True, data=set_responses)


@router.get("/flashcard-sets/{set_id}", response_model=APIResponse[FlashcardSetDetailResponse])
async def get_flashcard_set(
    set_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(FlashcardSet).where(
            FlashcardSet.id == set_id, FlashcardSet.deleted_at.is_(None)
        )
    )
    fs = result.scalar_one_or_none()
    if not fs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flashcard set not found")

    enrollment = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == fs.course_id, Enrollment.user_id == user.id
        )
    )
    if not enrollment.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enrolled")

    cards_result = await db.execute(
        select(FlashcardCard)
        .where(FlashcardCard.flashcard_set_id == fs.id)
        .order_by(FlashcardCard.card_index)
    )
    cards = cards_result.scalars().all()

    return APIResponse(
        success=True,
        data=FlashcardSetDetailResponse(
            id=fs.id,
            course_id=fs.course_id,
            title=fs.title,
            cards=cards,
            created_at=fs.created_at,
        ),
    )


@router.put("/flashcard-sets/{set_id}/progress", response_model=APIResponse[FlashcardProgressResponse])
async def update_flashcard_progress(
    set_id: uuid.UUID,
    body: FlashcardProgressUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only students can track progress"
        )

    # Verify card belongs to this set
    card_result = await db.execute(
        select(FlashcardCard).where(
            FlashcardCard.id == body.card_id,
            FlashcardCard.flashcard_set_id == set_id,
        )
    )
    if not card_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found in this set")

    # Get or create progress record
    progress_result = await db.execute(
        select(FlashcardProgress).where(
            FlashcardProgress.user_id == user.id,
            FlashcardProgress.flashcard_card_id == body.card_id,
        )
    )
    progress = progress_result.scalar_one_or_none()

    if not progress:
        progress = FlashcardProgress(
            user_id=user.id,
            flashcard_card_id=body.card_id,
        )
        db.add(progress)

    # SM-2 algorithm
    q = body.quality
    if q < 3:
        # Reset on failure
        progress.repetitions = 0
        progress.interval_days = 0
    else:
        if progress.repetitions == 0:
            progress.interval_days = 1
        elif progress.repetitions == 1:
            progress.interval_days = 6
        else:
            progress.interval_days = ceil(progress.interval_days * float(progress.ease_factor))
        progress.repetitions += 1

    # Update ease factor
    ef = float(progress.ease_factor) + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    progress.ease_factor = Decimal(str(max(1.3, ef)))

    now = datetime.now(timezone.utc)
    progress.last_reviewed = now
    from datetime import timedelta
    progress.next_review = now + timedelta(days=progress.interval_days)

    await db.commit()
    await db.refresh(progress)

    return APIResponse(
        success=True,
        data=FlashcardProgressResponse(
            card_id=progress.flashcard_card_id,
            ease_factor=progress.ease_factor,
            interval_days=progress.interval_days,
            repetitions=progress.repetitions,
            next_review=progress.next_review,
            last_reviewed=progress.last_reviewed,
        ),
    )
```

- [ ] **Step 2: Update api/__init__.py to add flashcards router**

Add to `backend/app/api/__init__.py`:

```python
from app.api.flashcards import router as flashcards_router
```

And add:

```python
api_router.include_router(flashcards_router)
```

- [ ] **Step 3: Verify imports**

```bash
cd backend && python -c "from app.api import api_router; print('Router OK')"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/flashcards.py backend/app/api/__init__.py
git commit -m "feat: add flashcard set listing, detail, and SM-2 progress tracking endpoints"
```

---

## Task 11: Integration Verification

Verify the full backend starts and all routes are registered.

**Files:** None (verification only)

- [ ] **Step 1: Verify backend starts**

```bash
cd backend && source .venv/bin/activate && python -c "
from app.main import app
routes = [r.path for r in app.routes]
print('Routes:')
for r in sorted(routes):
    print(f'  {r}')
print(f'Total: {len(routes)} routes')
"
```

Expected: Should list all RAG, quiz, and flashcard routes plus existing routes.

- [ ] **Step 2: Run all tests**

```bash
cd backend && python -m pytest tests/ -v --tb=short
```

Expected: All tests pass.

- [ ] **Step 3: Test health endpoint with running server**

```bash
curl -s http://localhost:8000/health | python -m json.tool
```

Expected: `{"status": "ok"}`

- [ ] **Step 4: Verify OpenAPI docs**

```bash
curl -s http://localhost:8000/openapi.json | python -c "
import json, sys
spec = json.load(sys.stdin)
paths = list(spec['paths'].keys())
print('API paths:')
for p in sorted(paths):
    methods = list(spec['paths'][p].keys())
    print(f'  {\" \".join(m.upper() for m in methods)} {p}')
"
```

Expected: All new endpoints appear in the OpenAPI spec.

- [ ] **Step 5: Commit (if any fixes were needed)**

```bash
git add -A && git commit -m "fix: integration fixes for Phase 1b endpoints"
```

---

## Summary

| Task | Component | Files Created | Tests |
|------|-----------|--------------|-------|
| 1 | Chunker | `services/chunker.py` | `tests/test_chunker.py` (7 tests) |
| 2 | Parser | `services/parser.py` | `tests/test_parser.py` (6 tests) |
| 3 | Embedder | `services/embedder.py` | `tests/test_embedder.py` (5 tests) |
| 4 | Retriever | `services/retriever.py` | `tests/test_retriever.py` (4 tests) |
| 5 | Generator | `services/generator.py` | `tests/test_generator.py` (4 tests) |
| 6 | Pipeline + Worker | `services/pipeline.py` | `tests/test_pipeline.py` (2 tests) |
| 7 | Schemas | `schemas/rag.py`, `quiz.py`, `flashcard.py` | Import verification |
| 8 | RAG API | `api/rag.py` | Import verification |
| 9 | Quiz API | `api/quizzes.py` | Import verification |
| 10 | Flashcard API | `api/flashcards.py` | Import verification |
| 11 | Integration | — | Full suite run |

**Total: 11 tasks, 28+ tests, 10 new files.**
