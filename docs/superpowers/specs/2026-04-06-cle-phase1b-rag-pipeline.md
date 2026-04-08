# CLE Phase 1b — RAG Pipeline Design Specification

**Date:** 2026-04-06
**Status:** Approved
**Parent Spec:** [CLE Platform Design](2026-04-05-cle-platform-design.md)

---

## 1. Scope

Phase 1b implements the core AI pipeline: document processing (parse → chunk → embed → store) and content generation (quiz, summary, flashcard) via RAG retrieval + LLM generation. Also adds Quiz and Flashcard CRUD APIs.

**Builds on Phase 1a:** models, worker skeleton, R2 storage, auth, document upload.

**Does NOT include:** pronunciation grading, live quiz WebSocket, hybrid search, spaced repetition algorithm, gamification, i18n — those are Phase 2.

## 2. Architecture

### 2.1 Document Processing Pipeline

```
Worker claims task (process_document)
  → Download file bytes from R2 (storage.py)
  → Parse to text (parser.py)
      - PDF/DOCX/PPTX → Docling
      - MP4/MP3 → OpenAI Whisper API
  → Chunk text (chunker.py)
      - ~500 tokens per chunk, 50-token overlap
      - Sentence boundary alignment
      - Preserve page numbers from parser metadata
  → Embed chunks (embedder.py)
      - OpenAI text-embedding-3-large (1536 dims)
      - Batch of up to 100 chunks per API call
  → Store chunks + vectors in DB (Chunk model)
  → Update document status → "ready"
  → Update document metadata (page_count, word_count)
```

### 2.2 RAG Query Flow

```
User request (generate quiz/summary/flashcards)
  → Embed query text (embedder.py)
  → Cosine similarity search over course chunks (retriever.py)
      - Filter by course_id
      - Top-k results (default k=10)
  → Build prompt with retrieved chunks (generator.py)
  → Call OpenRouter LLM → structured JSON output
  → Parse response → store in DB (Quiz/Flashcard models)
  → Return to user
```

## 3. Service Contracts

### 3.1 parser.py

```python
async def parse_document(file_data: bytes, file_type: str, filename: str) -> ParseResult

@dataclass
class ParseResult:
    text: str                    # Full extracted text
    pages: list[PageContent]     # Per-page text (if applicable)
    word_count: int
    page_count: int

@dataclass
class PageContent:
    page_number: int
    text: str
```

- PDF/DOCX/PPTX: Docling library (already in requirements.txt)
- MP4/MP3: OpenAI Whisper API via `openai` SDK (already in requirements.txt)
- Whisper: upload audio bytes → receive transcript text

### 3.2 chunker.py

```python
def chunk_text(text: str, pages: list[PageContent] | None = None) -> list[ChunkData]

@dataclass
class ChunkData:
    content: str
    chunk_index: int
    page_number: int | None
    token_count: int
```

- Target: ~500 tokens per chunk, 50-token overlap
- Split on sentence boundaries (`. `, `? `, `! `, newlines)
- Token counting: `len(text.split())` as approximation (no tiktoken dependency)
- Preserves page_number from parser output

### 3.3 embedder.py

```python
async def embed_texts(texts: list[str]) -> list[list[float]]
async def embed_query(query: str) -> list[float]
```

- Model: `text-embedding-3-large` (1536 dims)
- Batch size: up to 100 texts per API call
- Uses `openai.AsyncOpenAI` client

### 3.4 retriever.py

```python
async def retrieve_chunks(
    db: AsyncSession,
    course_id: uuid.UUID,
    query_embedding: list[float],
    top_k: int = 10,
    document_ids: list[uuid.UUID] | None = None,  # optional filter
) -> list[RetrievedChunk]

@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    content: str
    document_id: uuid.UUID
    page_number: int | None
    similarity_score: float
```

- Uses pgvector `<=>` cosine distance operator
- Filters by course_id (mandatory) and optionally by document_ids
- Returns chunks ordered by similarity descending

### 3.5 generator.py

```python
async def generate_quiz(
    chunks: list[RetrievedChunk],
    num_questions: int = 5,
    quiz_type: str = "multiple_choice",
    language: str = "english",
) -> list[GeneratedQuestion]

async def generate_summary(
    chunks: list[RetrievedChunk],
    language: str = "english",
) -> str

async def generate_flashcards(
    chunks: list[RetrievedChunk],
    num_cards: int = 10,
    language: str = "english",
) -> list[GeneratedFlashcard]
```

- Uses OpenRouter API (OpenAI-compatible) via `openai.AsyncOpenAI`
- Primary model: `qwen/qwen3.6-plus:free`, fallback: `gemini-2.5-flash-lite`
- Structured JSON output via system prompts with output format instructions
- Automatic fallback: if primary returns invalid JSON or errors, retry with fallback model

## 4. API Endpoints

### 4.1 RAG Endpoints (new: `api/rag.py`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/rag/query` | any enrolled | Retrieve relevant chunks for a question |
| POST | `/api/rag/generate-quiz` | instructor | Generate quiz from course materials |
| POST | `/api/rag/generate-summary` | any enrolled | Generate summary from course materials |
| POST | `/api/rag/generate-flashcards` | any enrolled | Generate flashcard set from course materials |

All RAG generation endpoints are rate-limited via existing middleware.

### 4.2 Quiz Endpoints (new: `api/quizzes.py`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/courses/{id}/quizzes` | any enrolled | List quizzes for a course |
| GET | `/api/quizzes/{id}` | any enrolled | Quiz detail with questions |
| PUT | `/api/quizzes/{id}` | instructor | Update quiz metadata |
| DELETE | `/api/quizzes/{id}` | instructor | Soft delete quiz |
| POST | `/api/quizzes/{id}/publish` | instructor | Publish quiz (makes visible to students) |
| POST | `/api/quizzes/{id}/attempt` | student | Submit quiz attempt |

### 4.3 Flashcard Endpoints (new: `api/flashcards.py`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/courses/{id}/flashcard-sets` | any enrolled | List flashcard sets |
| GET | `/api/flashcard-sets/{id}` | any enrolled | Set detail with cards |
| PUT | `/api/flashcard-sets/{id}/progress` | student | Update spaced repetition progress for a card |

## 5. Pydantic Schemas

### 5.1 schemas/rag.py

- `RAGQueryRequest`: course_id, query, top_k (default 10)
- `RAGQueryResponse`: list of chunks with content, page, similarity
- `GenerateQuizRequest`: course_id, document_ids (optional), num_questions (default 5), title
- `GenerateSummaryRequest`: course_id, document_ids (optional)
- `GenerateFlashcardsRequest`: course_id, document_ids (optional), num_cards (default 10), title

### 5.2 schemas/quiz.py

- `QuizResponse`: id, title, description, quiz_type, is_published, question_count, created_at
- `QuizDetailResponse`: extends QuizResponse with questions list
- `QuestionResponse`: id, question_index, type, question_text, options, explanation (no correct_answer for students)
- `QuizAttemptCreate`: answers dict (question_id → selected_answer)
- `QuizAttemptResponse`: score, total_questions, correct_count, per-question results

### 5.3 schemas/flashcard.py

- `FlashcardSetResponse`: id, title, card_count, created_at
- `FlashcardSetDetailResponse`: extends with cards list
- `FlashcardCardResponse`: id, front, back, card_index
- `FlashcardProgressUpdate`: card_id, quality (0-5 SM-2 rating)
- `FlashcardProgressResponse`: ease_factor, interval_days, next_review

## 6. New Dependencies

```
# Add to requirements.txt
tiktoken==0.9.0          # Accurate token counting for chunking (optional, can use word approximation)
```

No other new dependencies — `openai`, `docling`, `pgvector` already in requirements.txt.

## 7. Error Handling

- Parser failures: mark document status as "failed", store error in task.error_message
- Embedding API errors: retry up to 3 times (via existing task retry logic)
- LLM generation errors: try primary model, fallback to secondary, return error envelope if both fail
- Invalid LLM JSON output: retry once with stricter prompt, then return error
- Rate limit exceeded: 429 response (existing middleware)

## 8. Testing Strategy

- **Unit tests**: parser (mock Docling/Whisper), chunker (pure function), embedder (mock OpenAI), generator (mock OpenRouter)
- **Integration tests**: retriever (needs pgvector DB), full pipeline (mock external APIs)
- **Target**: 80%+ coverage on new services
