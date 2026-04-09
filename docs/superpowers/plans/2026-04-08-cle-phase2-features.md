# CLE Phase 2 — Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add five feature areas on top of the Phase 1 foundation: hybrid search (tsvector + pgvector RRF), gamification (XP/streaks/badges/leaderboard), pronunciation grading (Azure Speech + iFlytek), live quiz (WebSocket Kahoot-style), and i18n (Traditional Chinese).

**Architecture:** Each sub-phase is independently deployable. Backend services follow the existing stateless-function pattern. Frontend adds new hooks, components, and pages. Database changes via Alembic migrations.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, pgvector, Next.js 16, React 19, TanStack Query, Clerk, Playwright.

**Parent Spec:** [Phase 2 Features Design Spec](../specs/2026-04-08-cle-phase2-features.md)

---

## Implementation Order

| Phase | Feature | Risk | Dependencies |
|-------|---------|------|-------------|
| 2a | Hybrid Search | Low | Existing retriever + chunks table |
| 2b | Gamification | Medium | StudentProgress model exists, needs service + UI |
| 2c | Pronunciation Grading | High | External APIs (Azure Speech, iFlytek), new service |
| 2d | Live Quiz | High | WebSocket, in-memory state, new model (LiveAnswer) |
| 2e | i18n | Medium | Cross-cutting, apply after all UI is stable |

---

# Phase 2a — Hybrid Search

**Goal:** Combine tsvector full-text search with pgvector cosine similarity via Reciprocal Rank Fusion (RRF) to improve retrieval quality for keyword-heavy queries (terminology, formulas, proper nouns).

## File Structure

### New/Modified Files

```
backend/
├── alembic/versions/xxxx_hybrid_search.py   # Migration: GIN index + trigger
├── app/
│   ├── services/
│   │   └── retriever.py                      # MODIFY: add hybrid_retrieve()
│   ├── api/
│   │   └── rag.py                            # MODIFY: add search_mode param
│   └── schemas/
│       └── rag.py                            # MODIFY: add search_mode field
└── tests/
    ├── test_retriever.py                     # MODIFY: add hybrid search tests
    └── test_api_rag.py                       # MODIFY: test search_mode param
```

## Task 1: Alembic Migration — GIN Index + tsvector Trigger

**Files:**
- Create: `backend/alembic/versions/xxxx_hybrid_search.py`

- [ ] **Step 1: Create migration**

```python
# backend/alembic/versions/xxxx_hybrid_search.py
"""hybrid search: GIN index and tsvector auto-populate trigger"""

from alembic import op

revision = "..."
down_revision = "505ded56ba1e"


def upgrade() -> None:
    # Populate tsvector for existing chunks
    op.execute("""
        UPDATE chunks SET tsvector_content = to_tsvector('english', content)
        WHERE tsvector_content IS NULL
    """)

    # GIN index for fast full-text search
    op.execute("""
        CREATE INDEX idx_chunks_tsvector ON chunks USING GIN (tsvector_content)
    """)

    # Auto-populate trigger on INSERT/UPDATE
    op.execute("""
        CREATE OR REPLACE FUNCTION chunks_tsvector_trigger() RETURNS trigger AS $$
        BEGIN
            NEW.tsvector_content := to_tsvector('english', NEW.content);
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE TRIGGER tsvector_update BEFORE INSERT OR UPDATE OF content
        ON chunks FOR EACH ROW EXECUTE FUNCTION chunks_tsvector_trigger()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS tsvector_update ON chunks")
    op.execute("DROP FUNCTION IF EXISTS chunks_tsvector_trigger()")
    op.execute("DROP INDEX IF EXISTS idx_chunks_tsvector")
    op.execute("UPDATE chunks SET tsvector_content = NULL")
```

- [ ] **Step 2: Run migration**

```bash
cd backend && alembic upgrade head
```

- [ ] **Step 3: Verify tsvector populated**

```bash
cd backend && python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/langassistant')
    async with engine.connect() as conn:
        result = await conn.execute(text('SELECT COUNT(*) FROM chunks WHERE tsvector_content IS NOT NULL'))
        print(f'Chunks with tsvector: {result.scalar()}')

asyncio.run(check())
"
```

## Task 2: Hybrid Retriever

**Files:**
- Modify: `backend/app/services/retriever.py`
- Create: `backend/tests/test_retriever_hybrid.py`

- [ ] **Step 1: Write hybrid search tests**

```python
# backend/tests/test_retriever_hybrid.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.retriever import (
    RetrievedChunk,
    fulltext_retrieve,
    hybrid_retrieve,
    rrf_merge,
)


class TestRRFMerge:
    def test_rrf_merge_combines_both_lists(self):
        vector_results = [
            RetrievedChunk(chunk_id="a", content="A", document_id="d1", page_number=1, similarity_score=0.95),
            RetrievedChunk(chunk_id="b", content="B", document_id="d1", page_number=2, similarity_score=0.85),
        ]
        text_results = [
            RetrievedChunk(chunk_id="b", content="B", document_id="d1", page_number=2, similarity_score=0.9),
            RetrievedChunk(chunk_id="c", content="C", document_id="d2", page_number=1, similarity_score=0.8),
        ]
        merged = rrf_merge(vector_results, text_results, k=60, top_k=10)
        ids = [c.chunk_id for c in merged]
        # "b" appears in both lists so should rank highest
        assert ids[0] == "b"
        assert len(merged) == 3

    def test_rrf_merge_respects_top_k(self):
        vector_results = [
            RetrievedChunk(chunk_id=f"v{i}", content=f"V{i}", document_id="d1", page_number=1, similarity_score=0.9 - i*0.01)
            for i in range(10)
        ]
        text_results = []
        merged = rrf_merge(vector_results, text_results, k=60, top_k=5)
        assert len(merged) == 5

    def test_rrf_merge_empty_inputs(self):
        merged = rrf_merge([], [], k=60, top_k=10)
        assert merged == []


class TestFulltextRetrieve:
    @pytest.mark.asyncio
    async def test_fulltext_retrieve_returns_chunks(self):
        # Integration test — requires test DB with populated tsvector
        pass  # Implemented as integration test below
```

- [ ] **Step 2: Run tests — should fail**

```bash
cd backend && python -m pytest tests/test_retriever_hybrid.py -v
```

- [ ] **Step 3: Implement fulltext_retrieve and rrf_merge in retriever.py**

Add to `backend/app/services/retriever.py`:

```python
from sqlalchemy import func, text


async def fulltext_retrieve(
    db: AsyncSession,
    course_id: str,
    query: str,
    top_k: int = 10,
    document_ids: list[str] | None = None,
) -> list[RetrievedChunk]:
    """Full-text search using tsvector + ts_rank."""
    tsquery = func.plainto_tsquery("english", query)

    stmt = (
        select(
            Chunk.id,
            Chunk.content,
            Chunk.document_id,
            Chunk.page_number,
            func.ts_rank(Chunk.tsvector_content, tsquery).label("rank"),
        )
        .where(
            Chunk.course_id == course_id,
            Chunk.tsvector_content.op("@@")(tsquery),
        )
        .order_by(text("rank DESC"))
        .limit(top_k)
    )

    if document_ids:
        stmt = stmt.where(Chunk.document_id.in_(document_ids))

    result = await db.execute(stmt)
    rows = result.all()

    return [
        RetrievedChunk(
            chunk_id=str(row.id),
            content=row.content,
            document_id=str(row.document_id),
            page_number=row.page_number,
            similarity_score=float(row.rank),
        )
        for row in rows
    ]


def rrf_merge(
    vector_results: list[RetrievedChunk],
    text_results: list[RetrievedChunk],
    k: int = 60,
    top_k: int = 10,
) -> list[RetrievedChunk]:
    """Reciprocal Rank Fusion: merge two ranked lists."""
    scores: dict[str, float] = {}
    chunk_map: dict[str, RetrievedChunk] = {}

    for rank, chunk in enumerate(vector_results):
        scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0) + 1.0 / (k + rank + 1)
        chunk_map[chunk.chunk_id] = chunk

    for rank, chunk in enumerate(text_results):
        scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0) + 1.0 / (k + rank + 1)
        if chunk.chunk_id not in chunk_map:
            chunk_map[chunk.chunk_id] = chunk

    sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:top_k]
    return [
        RetrievedChunk(
            chunk_id=chunk_map[cid].chunk_id,
            content=chunk_map[cid].content,
            document_id=chunk_map[cid].document_id,
            page_number=chunk_map[cid].page_number,
            similarity_score=scores[cid],
        )
        for cid in sorted_ids
    ]


async def hybrid_retrieve(
    db: AsyncSession,
    course_id: str,
    query: str,
    query_embedding: list[float],
    top_k: int = 10,
    document_ids: list[str] | None = None,
) -> list[RetrievedChunk]:
    """Run vector + fulltext in parallel, merge via RRF."""
    import asyncio

    vector_task = asyncio.create_task(
        retrieve_chunks(db, course_id, query_embedding, top_k=top_k * 2, document_ids=document_ids)
    )
    text_task = asyncio.create_task(
        fulltext_retrieve(db, course_id, query, top_k=top_k * 2, document_ids=document_ids)
    )
    vector_results, text_results = await asyncio.gather(vector_task, text_task)
    return rrf_merge(vector_results, text_results, k=60, top_k=top_k)
```

- [ ] **Step 4: Run tests — should pass**

```bash
cd backend && python -m pytest tests/test_retriever_hybrid.py -v
```

## Task 3: Update RAG API to Support search_mode

**Files:**
- Modify: `backend/app/schemas/rag.py`
- Modify: `backend/app/api/rag.py`

- [ ] **Step 1: Add search_mode to RAGQueryRequest schema**

```python
# In backend/app/schemas/rag.py — add to RAGQueryRequest
from typing import Literal

class RAGQueryRequest(BaseModel):
    course_id: str
    query: str
    top_k: int = Field(default=10, ge=1, le=50)
    search_mode: Literal["vector", "fulltext", "hybrid"] = "hybrid"
    document_ids: list[str] | None = None
```

- [ ] **Step 2: Update rag.py query endpoint to dispatch by search_mode**

In the `POST /rag/query` handler:
- If `search_mode == "vector"`: use existing `retrieve_chunks()`
- If `search_mode == "fulltext"`: use new `fulltext_retrieve()`
- If `search_mode == "hybrid"`: use new `hybrid_retrieve()`

- [ ] **Step 3: Test the endpoint**

```bash
cd backend && python -m pytest tests/test_api_rag.py -v
```

**Checkpoint: Phase 2a complete.** Hybrid search is live. All RAG endpoints (query, generate-quiz, generate-summary, generate-flashcards) can use it.

---

# Phase 2b — Gamification

**Goal:** Build XP, streaks, badges, and leaderboard system to motivate students. The `StudentProgress` model already exists with all needed columns — we need a service layer, API endpoints, and frontend UI.

## File Structure

### New Files

```
backend/
├── app/
│   ├── services/
│   │   └── gamification.py              # XP, streaks, badges logic
│   ├── api/
│   │   └── progress.py                  # Leaderboard + progress endpoints
│   └── schemas/
│       └── progress.py                  # Progress/leaderboard schemas
└── tests/
    ├── test_gamification.py             # Unit tests for XP/streak/badge logic
    └── test_api_progress.py             # API endpoint tests

frontend/src/
├── hooks/
│   └── use-progress.ts                  # useProgress, useLeaderboard hooks
├── components/
│   └── gamification/
│       ├── progress-card.tsx            # XP, streak, badges display
│       ├── leaderboard.tsx              # Course leaderboard table
│       ├── badge-display.tsx            # Badge grid with icons
│       └── xp-toast.tsx                 # XP gained notification
└── app/dashboard/courses/[courseId]/
    └── page.tsx                         # MODIFY: add leaderboard tab
```

### Modified Files

```
backend/app/api/quizzes.py              # Call award_xp after quiz attempt
backend/app/api/flashcards.py           # Call award_xp after review session
backend/app/api/__init__.py             # Register progress router
```

## Task 4: Gamification Service

**Files:**
- Create: `backend/app/services/gamification.py`
- Create: `backend/tests/test_gamification.py`

- [ ] **Step 1: Write gamification tests**

```python
# backend/tests/test_gamification.py
import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

from app.services.gamification import (
    calculate_quiz_xp,
    calculate_streak,
    check_badges,
    BADGE_DEFINITIONS,
)


class TestCalculateQuizXP:
    def test_perfect_score(self):
        assert calculate_quiz_xp(score=100.0) == 1000

    def test_partial_score(self):
        assert calculate_quiz_xp(score=80.0) == 800

    def test_zero_score(self):
        assert calculate_quiz_xp(score=0.0) == 0

    def test_rounds_down(self):
        assert calculate_quiz_xp(score=33.33) == 333


class TestCalculateStreak:
    def test_first_activity(self):
        streak, new_date = calculate_streak(
            current_streak=0,
            last_activity_date=None,
            today=date(2026, 4, 8),
        )
        assert streak == 1
        assert new_date == date(2026, 4, 8)

    def test_consecutive_day(self):
        streak, new_date = calculate_streak(
            current_streak=5,
            last_activity_date=date(2026, 4, 7),
            today=date(2026, 4, 8),
        )
        assert streak == 6

    def test_same_day_no_increment(self):
        streak, new_date = calculate_streak(
            current_streak=5,
            last_activity_date=date(2026, 4, 8),
            today=date(2026, 4, 8),
        )
        assert streak == 5

    def test_gap_resets_streak(self):
        streak, new_date = calculate_streak(
            current_streak=10,
            last_activity_date=date(2026, 4, 5),
            today=date(2026, 4, 8),
        )
        assert streak == 1


class TestCheckBadges:
    def test_first_quiz_badge(self):
        progress = MagicMock(
            quizzes_completed=1,
            flashcards_reviewed=0,
            speaking_sessions=0,
            streak_days=0,
            badges=[],
        )
        new_badges = check_badges(progress, quiz_score=80.0, quiz_time_seconds=None)
        assert "first_quiz" in new_badges

    def test_perfect_score_badge(self):
        progress = MagicMock(
            quizzes_completed=5,
            flashcards_reviewed=0,
            speaking_sessions=0,
            streak_days=0,
            badges=["first_quiz"],
        )
        new_badges = check_badges(progress, quiz_score=100.0, quiz_time_seconds=None)
        assert "perfect_score" in new_badges

    def test_streak_7_badge(self):
        progress = MagicMock(
            quizzes_completed=5,
            flashcards_reviewed=10,
            speaking_sessions=0,
            streak_days=7,
            badges=["first_quiz"],
        )
        new_badges = check_badges(progress, quiz_score=None, quiz_time_seconds=None)
        assert "streak_7" in new_badges

    def test_no_duplicate_badges(self):
        progress = MagicMock(
            quizzes_completed=5,
            flashcards_reviewed=0,
            speaking_sessions=0,
            streak_days=7,
            badges=["first_quiz", "streak_7"],
        )
        new_badges = check_badges(progress, quiz_score=100.0, quiz_time_seconds=None)
        assert "first_quiz" not in new_badges  # already earned
        assert "streak_7" not in new_badges    # already earned

    def test_speed_learner_badge(self):
        progress = MagicMock(
            quizzes_completed=3,
            flashcards_reviewed=0,
            speaking_sessions=0,
            streak_days=0,
            badges=[],
        )
        new_badges = check_badges(progress, quiz_score=90.0, quiz_time_seconds=45)
        assert "speed_learner" in new_badges
```

- [ ] **Step 2: Run tests — should fail**

```bash
cd backend && python -m pytest tests/test_gamification.py -v
```

- [ ] **Step 3: Implement gamification service**

```python
# backend/app/services/gamification.py
from datetime import date, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.score import StudentProgress


BADGE_DEFINITIONS = {
    "first_quiz": lambda p, **kw: p.quizzes_completed >= 1,
    "perfect_score": lambda p, **kw: kw.get("quiz_score") == 100.0,
    "streak_7": lambda p, **kw: p.streak_days >= 7,
    "streak_30": lambda p, **kw: p.streak_days >= 30,
    "flashcard_master": lambda p, **kw: p.flashcards_reviewed >= 100,
    "speed_learner": lambda p, **kw: (
        kw.get("quiz_score", 0) >= 80.0
        and kw.get("quiz_time_seconds") is not None
        and kw.get("quiz_time_seconds") < 60
    ),
}


def calculate_quiz_xp(score: float) -> int:
    return int(score * 10)


def calculate_streak(
    current_streak: int,
    last_activity_date: date | None,
    today: date,
) -> tuple[int, date]:
    if last_activity_date is None:
        return 1, today
    if last_activity_date == today:
        return current_streak, today
    if last_activity_date == today - timedelta(days=1):
        return current_streak + 1, today
    return 1, today


def check_badges(
    progress: StudentProgress,
    quiz_score: float | None = None,
    quiz_time_seconds: int | None = None,
) -> list[str]:
    existing = set(progress.badges or [])
    new_badges = []
    for badge_id, check_fn in BADGE_DEFINITIONS.items():
        if badge_id not in existing and check_fn(
            progress, quiz_score=quiz_score, quiz_time_seconds=quiz_time_seconds
        ):
            new_badges.append(badge_id)
    return new_badges


async def get_or_create_progress(
    db: AsyncSession, user_id: str, course_id: str
) -> StudentProgress:
    stmt = select(StudentProgress).where(
        StudentProgress.user_id == user_id,
        StudentProgress.course_id == course_id,
    )
    result = await db.execute(stmt)
    progress = result.scalar_one_or_none()
    if progress is None:
        progress = StudentProgress(user_id=user_id, course_id=course_id)
        db.add(progress)
        await db.flush()
    return progress


async def award_xp(
    db: AsyncSession,
    user_id: str,
    course_id: str,
    xp: int,
    activity: str,
    quiz_score: float | None = None,
    quiz_time_seconds: int | None = None,
) -> dict:
    """Award XP, update streak, check badges. Returns summary."""
    progress = await get_or_create_progress(db, user_id, course_id)

    # XP
    progress.xp_points = (progress.xp_points or 0) + xp

    # Activity counters
    if activity == "quiz":
        progress.quizzes_completed = (progress.quizzes_completed or 0) + 1
    elif activity == "flashcard":
        progress.flashcards_reviewed = (progress.flashcards_reviewed or 0) + 1
    elif activity == "pronunciation":
        progress.speaking_sessions = (progress.speaking_sessions or 0) + 1

    # Streak
    today = date.today()
    new_streak, new_date = calculate_streak(
        progress.streak_days or 0, progress.last_activity_date, today
    )
    progress.streak_days = new_streak
    progress.last_activity_date = new_date

    # Badges
    new_badges = check_badges(progress, quiz_score=quiz_score, quiz_time_seconds=quiz_time_seconds)
    if new_badges:
        progress.badges = list(set((progress.badges or []) + new_badges))

    await db.flush()
    return {
        "xp_earned": xp,
        "total_xp": progress.xp_points,
        "streak_days": progress.streak_days,
        "new_badges": new_badges,
    }
```

- [ ] **Step 4: Run tests — should pass**

```bash
cd backend && python -m pytest tests/test_gamification.py -v
```

## Task 5: Progress & Leaderboard API

**Files:**
- Create: `backend/app/schemas/progress.py`
- Create: `backend/app/api/progress.py`
- Modify: `backend/app/api/__init__.py`
- Create: `backend/tests/test_api_progress.py`

- [ ] **Step 1: Create progress schemas**

```python
# backend/app/schemas/progress.py
from pydantic import BaseModel
from datetime import date


class ProgressResponse(BaseModel):
    course_id: str
    xp_points: int
    streak_days: int
    last_activity_date: date | None
    quizzes_completed: int
    flashcards_reviewed: int
    speaking_sessions: int
    badges: list[str]


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    full_name: str
    avatar_url: str | None
    xp_points: int


class XPAwardResponse(BaseModel):
    xp_earned: int
    total_xp: int
    streak_days: int
    new_badges: list[str]
```

- [ ] **Step 2: Create progress API endpoints**

```python
# backend/app/api/progress.py
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.score import StudentProgress
from app.models.user import User
from app.schemas.progress import LeaderboardEntry, ProgressResponse
from app.schemas.response import APIResponse, PaginatedResponse

router = APIRouter(tags=["progress"])


@router.get("/courses/{course_id}/progress")
async def get_my_progress(
    course_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ProgressResponse]:
    stmt = select(StudentProgress).where(
        StudentProgress.user_id == user.id,
        StudentProgress.course_id == course_id,
    )
    result = await db.execute(stmt)
    progress = result.scalar_one_or_none()

    if progress is None:
        return APIResponse(
            success=True,
            data=ProgressResponse(
                course_id=course_id,
                xp_points=0, streak_days=0, last_activity_date=None,
                quizzes_completed=0, flashcards_reviewed=0,
                speaking_sessions=0, badges=[],
            ),
        )

    return APIResponse(
        success=True,
        data=ProgressResponse(
            course_id=str(progress.course_id),
            xp_points=progress.xp_points or 0,
            streak_days=progress.streak_days or 0,
            last_activity_date=progress.last_activity_date,
            quizzes_completed=progress.quizzes_completed or 0,
            flashcards_reviewed=progress.flashcards_reviewed or 0,
            speaking_sessions=progress.speaking_sessions or 0,
            badges=progress.badges or [],
        ),
    )


@router.get("/courses/{course_id}/leaderboard")
async def get_leaderboard(
    course_id: str,
    page: int = 1,
    limit: int = 10,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[list[LeaderboardEntry]]:
    # Count total
    count_stmt = select(func.count()).select_from(StudentProgress).where(
        StudentProgress.course_id == course_id,
        StudentProgress.xp_points > 0,
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    # Fetch ranked entries
    stmt = (
        select(StudentProgress, User)
        .join(User, StudentProgress.user_id == User.id)
        .where(
            StudentProgress.course_id == course_id,
            StudentProgress.xp_points > 0,
        )
        .order_by(StudentProgress.xp_points.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    entries = [
        LeaderboardEntry(
            rank=(page - 1) * limit + i + 1,
            user_id=str(progress.user_id),
            full_name=user_row.full_name or "Anonymous",
            avatar_url=user_row.avatar_url,
            xp_points=progress.xp_points or 0,
        )
        for i, (progress, user_row) in enumerate(rows)
    ]

    return PaginatedResponse(
        success=True,
        data=entries,
        meta={"total": total, "page": page, "limit": limit, "pages": -(-total // limit)},
    )
```

- [ ] **Step 3: Register router in `backend/app/api/__init__.py`**

Add `from app.api.progress import router as progress_router` and include it.

- [ ] **Step 4: Write and run endpoint tests**

```bash
cd backend && python -m pytest tests/test_api_progress.py -v
```

## Task 6: Integrate Gamification into Quiz & Flashcard Endpoints

**Files:**
- Modify: `backend/app/api/quizzes.py` — after quiz attempt creation
- Modify: `backend/app/api/flashcards.py` — after flashcard progress update

- [ ] **Step 1: Call award_xp in quiz attempt endpoint**

In `POST /quizzes/{quiz_id}/attempts` handler, after scoring:

```python
from app.services.gamification import award_xp

# After calculating score and creating QuizAttempt:
xp = int(attempt.score * 10)
gamification_result = await award_xp(
    db, user_id=str(user.id), course_id=str(quiz.course_id),
    xp=xp, activity="quiz",
    quiz_score=float(attempt.score),
    quiz_time_seconds=attempt.time_taken_seconds,
)
```

- [ ] **Step 2: Call award_xp in flashcard progress endpoint**

In `PUT /flashcard-sets/{set_id}/progress` handler, after SM-2 update:

```python
# Award 50 XP for flashcard review sessions (every 5 cards)
# Track card count and award when threshold is met
gamification_result = await award_xp(
    db, user_id=str(user.id), course_id=str(flashcard_set.course_id),
    xp=50, activity="flashcard",
)
```

- [ ] **Step 3: Verify integration with existing tests**

```bash
cd backend && python -m pytest tests/test_api_quizzes.py tests/test_api_flashcards.py -v
```

## Task 7: Frontend — Progress & Leaderboard UI

**Files:**
- Create: `frontend/src/hooks/use-progress.ts`
- Create: `frontend/src/components/gamification/progress-card.tsx`
- Create: `frontend/src/components/gamification/leaderboard.tsx`
- Create: `frontend/src/components/gamification/badge-display.tsx`
- Modify: `frontend/src/app/dashboard/courses/[courseId]/page.tsx`

- [ ] **Step 1: Create progress hooks**

```typescript
// frontend/src/hooks/use-progress.ts
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@clerk/nextjs";
import { apiFetch } from "@/lib/api";

interface ProgressResponse {
  course_id: string;
  xp_points: number;
  streak_days: number;
  last_activity_date: string | null;
  quizzes_completed: number;
  flashcards_reviewed: number;
  speaking_sessions: number;
  badges: string[];
}

interface LeaderboardEntry {
  rank: number;
  user_id: string;
  full_name: string;
  avatar_url: string | null;
  xp_points: number;
}

export function useProgress(courseId: string) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["progress", courseId],
    queryFn: async () => {
      const token = await getToken();
      const res = await apiFetch<{ data: ProgressResponse }>(
        `/courses/${courseId}/progress`,
        { token: token ?? undefined }
      );
      return res.data;
    },
  });
}

export function useLeaderboard(courseId: string, page = 1) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["leaderboard", courseId, page],
    queryFn: async () => {
      const token = await getToken();
      return apiFetch<{ data: LeaderboardEntry[]; meta: any }>(
        `/courses/${courseId}/leaderboard?page=${page}`,
        { token: token ?? undefined }
      );
    },
  });
}
```

- [ ] **Step 2: Create progress-card component**

Show XP (with level calculation), streak fire icon, activity counts, and badge grid.

- [ ] **Step 3: Create leaderboard component**

Table with rank, avatar, name, XP. Highlight current user. Paginated.

- [ ] **Step 4: Create badge-display component**

Grid of badge icons with tooltips. Earned badges in color, unearned grayed out.

- [ ] **Step 5: Add Progress and Leaderboard tabs to course page**

Modify the course detail page to include a "Progress" tab (student view) and "Leaderboard" tab (all enrolled).

- [ ] **Step 6: Run frontend build + lint**

```bash
cd frontend && npm run build && npm run lint
```

**Checkpoint: Phase 2b complete.** Students earn XP from quizzes and flashcards, see their streak, earn badges, and compete on the leaderboard.

---

# Phase 2c — Pronunciation Grading

**Goal:** Enable spoken language practice with automated pronunciation feedback. Azure Speech SDK for English, iFlytek for Chinese. Scores stored in existing `PronunciationScore` model.

## File Structure

### New Files

```
backend/
├── app/
│   ├── services/
│   │   └── speech.py                    # Azure Speech + iFlytek providers
│   ├── api/
│   │   └── speech.py                    # POST /api/speech/grade, GET history
│   └── schemas/
│       └── speech.py                    # Request/response schemas
└── tests/
    ├── test_speech_service.py           # Mocked provider tests
    └── test_api_speech.py               # API endpoint tests

frontend/src/
├── hooks/
│   └── use-pronunciation.ts             # usePronunciationGrade, useHistory
├── components/
│   └── pronunciation/
│       ├── recorder.tsx                 # Audio recorder with waveform
│       ├── score-display.tsx            # Overall + per-word heatmap
│       └── history-chart.tsx            # Trend chart of past attempts
└── app/dashboard/courses/[courseId]/
    └── pronunciation/page.tsx           # Pronunciation practice page
```

## Task 8: Speech Service

**Files:**
- Create: `backend/app/services/speech.py`
- Create: `backend/tests/test_speech_service.py`

- [ ] **Step 1: Write speech service tests (mocked providers)**

Test both Azure and iFlytek code paths with mocked HTTP responses. Verify score normalization to common format.

- [ ] **Step 2: Run tests — should fail**

```bash
cd backend && python -m pytest tests/test_speech_service.py -v
```

- [ ] **Step 3: Implement speech service**

```python
# backend/app/services/speech.py
from dataclasses import dataclass

from app.config import settings


@dataclass
class WordScore:
    word: str
    accuracy: float  # 0-100
    error_type: str | None  # None, "Mispronunciation", "Omission", "Insertion"


@dataclass
class PronunciationResult:
    overall_score: float     # 0-100
    accuracy_score: float    # 0-100
    fluency_score: float     # 0-100
    completeness_score: float  # 0-100
    prosody_score: float | None  # 0-100, Azure only
    word_scores: list[WordScore]
    provider: str


async def grade_azure(audio_bytes: bytes, reference_text: str) -> PronunciationResult:
    """Grade pronunciation using Azure Speech SDK."""
    import azure.cognitiveservices.speech as speechsdk
    import tempfile, os

    speech_config = speechsdk.SpeechConfig(
        subscription=settings.azure_speech_key,
        region=settings.azure_speech_region,
    )
    pronunciation_config = speechsdk.PronunciationAssessmentConfig(
        reference_text=reference_text,
        grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
        granularity=speechsdk.PronunciationAssessmentGranularity.Word,
        enable_prosody_assessment=True,
    )

    # Write audio to temp file for SDK
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_bytes)
        temp_path = f.name

    try:
        audio_config = speechsdk.AudioConfig(filename=temp_path)
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config, audio_config=audio_config
        )
        pronunciation_config.apply_to(recognizer)

        result = recognizer.recognize_once()
        assessment = speechsdk.PronunciationAssessmentResult(result)

        word_scores = []
        for word in assessment.words:
            word_scores.append(WordScore(
                word=word.word,
                accuracy=word.accuracy_score,
                error_type=word.error_type if hasattr(word, "error_type") else None,
            ))

        return PronunciationResult(
            overall_score=assessment.pronunciation_score,
            accuracy_score=assessment.accuracy_score,
            fluency_score=assessment.fluency_score,
            completeness_score=assessment.completeness_score,
            prosody_score=getattr(assessment, "prosody_score", None),
            word_scores=word_scores,
            provider="azure",
        )
    finally:
        os.unlink(temp_path)


async def grade_iflytek(audio_bytes: bytes, reference_text: str) -> PronunciationResult:
    """Grade pronunciation using iFlytek Speech Evaluation API."""
    import hashlib, hmac, base64, time, json
    import httpx

    # Build HMAC-SHA256 auth headers per iFlytek docs
    ts = str(int(time.time()))
    base_string = f"{settings.iflytek_app_id}{ts}"
    signature = hmac.new(
        settings.iflytek_api_secret.encode(),
        base_string.encode(),
        hashlib.sha256,
    ).digest()
    sig_b64 = base64.b64encode(signature).decode()

    audio_b64 = base64.b64encode(audio_bytes).decode()

    payload = {
        "common": {"app_id": settings.iflytek_app_id},
        "business": {
            "category": "read_sentence",
            "rstcd": "utf8",
            "text": reference_text,
        },
        "data": {"audio": audio_b64},
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.xfyun.cn/v1/service/v1/ise",
            json=payload,
            headers={
                "X-Appid": settings.iflytek_app_id,
                "X-CurTime": ts,
                "X-Param": sig_b64,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

    # Normalize iFlytek scores to 0-100 format
    result_data = data.get("data", {})
    return PronunciationResult(
        overall_score=result_data.get("total_score", 0),
        accuracy_score=result_data.get("accuracy_score", 0),
        fluency_score=result_data.get("fluency_score", 0),
        completeness_score=result_data.get("integrity_score", 0),
        prosody_score=None,
        word_scores=[],  # iFlytek word-level parsing varies by plan
        provider="iflytek",
    )


async def grade_pronunciation(
    audio_bytes: bytes,
    reference_text: str,
    language: str,
) -> PronunciationResult:
    """Route to appropriate provider based on language."""
    if language.startswith("zh") or language == "chinese":
        return await grade_iflytek(audio_bytes, reference_text)
    return await grade_azure(audio_bytes, reference_text)
```

- [ ] **Step 4: Run tests — should pass**

```bash
cd backend && python -m pytest tests/test_speech_service.py -v
```

## Task 9: Speech API Endpoints

**Files:**
- Create: `backend/app/schemas/speech.py`
- Create: `backend/app/api/speech.py`
- Modify: `backend/app/api/__init__.py`
- Create: `backend/tests/test_api_speech.py`

- [ ] **Step 1: Create speech schemas**

```python
# backend/app/schemas/speech.py
from pydantic import BaseModel


class WordScoreResponse(BaseModel):
    word: str
    accuracy: float
    error_type: str | None = None


class PronunciationGradeResponse(BaseModel):
    id: str
    overall_score: float
    accuracy_score: float
    fluency_score: float
    completeness_score: float
    prosody_score: float | None = None
    word_scores: list[WordScoreResponse]
    provider: str


class PronunciationHistoryEntry(BaseModel):
    id: str
    target_text: str
    overall_score: float
    accuracy_score: float
    fluency_score: float
    created_at: str
```

- [ ] **Step 2: Create speech API router**

```python
# backend/app/api/speech.py
from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.score import PronunciationScore
from app.services.gamification import award_xp
from app.services.speech import grade_pronunciation
from app.services.storage import upload_file
from app.schemas.response import APIResponse

router = APIRouter(prefix="/speech", tags=["speech"])


@router.post("/grade")
async def grade(
    audio: UploadFile = File(...),
    reference_text: str = Form(...),
    course_id: str = Form(...),
    language: str = Form(default="english"),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    audio_bytes = await audio.read()

    # Upload audio to R2
    r2_key = f"pronunciation/{user.id}/{audio.filename}"
    await upload_file(audio_bytes, r2_key, audio.content_type or "audio/wav")

    # Grade pronunciation
    result = await grade_pronunciation(audio_bytes, reference_text, language)

    # Store in DB
    score = PronunciationScore(
        user_id=user.id,
        course_id=course_id,
        language=language,
        target_text=reference_text,
        audio_r2_key=r2_key,
        overall_score=result.overall_score,
        accuracy_score=result.accuracy_score,
        fluency_score=result.fluency_score,
        completeness_score=result.completeness_score,
        prosody_score=result.prosody_score,
        detailed_result={"word_scores": [vars(w) for w in result.word_scores]},
        grading_provider=result.provider,
    )
    db.add(score)

    # Award XP
    await award_xp(db, str(user.id), course_id, xp=30, activity="pronunciation")
    await db.commit()

    return APIResponse(success=True, data={
        "id": str(score.id),
        "overall_score": result.overall_score,
        "accuracy_score": result.accuracy_score,
        "fluency_score": result.fluency_score,
        "completeness_score": result.completeness_score,
        "prosody_score": result.prosody_score,
        "word_scores": [vars(w) for w in result.word_scores],
        "provider": result.provider,
    })
```

- [ ] **Step 3: Add pronunciation history endpoint**

```python
# Add to backend/app/api/speech.py
@router.get("/courses/{course_id}/pronunciation-history")
async def pronunciation_history(
    course_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    stmt = (
        select(PronunciationScore)
        .where(
            PronunciationScore.user_id == user.id,
            PronunciationScore.course_id == course_id,
        )
        .order_by(PronunciationScore.created_at.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    scores = result.scalars().all()
    # ... serialize and return
```

- [ ] **Step 4: Register router and add config keys**

Add `azure_speech_key`, `azure_speech_region`, `iflytek_app_id`, `iflytek_api_key`, `iflytek_api_secret` to `backend/app/config.py`.

- [ ] **Step 5: Update requirements.txt**

Add `azure-cognitiveservices-speech==1.42.0`.

- [ ] **Step 6: Run tests**

```bash
cd backend && python -m pytest tests/test_api_speech.py -v
```

## Task 10: Frontend — Pronunciation Practice UI

**Files:**
- Create: `frontend/src/hooks/use-pronunciation.ts`
- Create: `frontend/src/components/pronunciation/recorder.tsx`
- Create: `frontend/src/components/pronunciation/score-display.tsx`
- Create: `frontend/src/components/pronunciation/history-chart.tsx`
- Create: `frontend/src/app/dashboard/courses/[courseId]/pronunciation/page.tsx`

- [ ] **Step 1: Create pronunciation hooks**

`usePronunciationGrade()` — mutation that POSTs audio + text to `/api/speech/grade`
`usePronunciationHistory(courseId)` — query for past attempts

- [ ] **Step 2: Create audio recorder component**

Use `MediaRecorder` API. Show waveform visualization via `AnalyserNode`. Start/stop controls. Return audio blob on stop.

- [ ] **Step 3: Create score display component**

Circular overall score gauge. Per-word heatmap: green (>80), yellow (60-80), red (<60). Breakdown bars for accuracy, fluency, completeness.

- [ ] **Step 4: Create history chart component**

Line chart showing overall scores over time. Use a lightweight chart library or CSS-based bars.

- [ ] **Step 5: Create pronunciation practice page**

Page layout: text display → record button → results → history. Course context for language detection.

- [ ] **Step 6: Add navigation link**

Add "Pronunciation" to the course page tabs and sidebar navigation.

- [ ] **Step 7: Run frontend build + lint**

```bash
cd frontend && npm run build && npm run lint
```

**Checkpoint: Phase 2c complete.** Students can practice pronunciation and get per-word feedback.

---

# Phase 2d — Live Quiz (Kahoot-style)

**Goal:** Real-time in-class quiz competitions via WebSocket. Instructor hosts, students answer, live scoring and leaderboard.

## File Structure

### New Files

```
backend/
├── app/
│   ├── services/
│   │   └── live_quiz.py                 # Session state, scoring, WebSocket manager
│   ├── api/
│   │   └── live.py                      # REST + WebSocket endpoints
│   ├── models/
│   │   └── live_answer.py               # LiveAnswer model (NEW)
│   └── schemas/
│       └── live.py                      # Session/answer schemas
├── alembic/versions/
│   └── xxxx_live_quiz.py               # Migration: join_code, settings, live_answers table
└── tests/
    ├── test_live_quiz_service.py        # Unit tests for scoring, state machine
    └── test_api_live.py                 # WebSocket integration tests

frontend/src/
├── hooks/
│   └── use-live-quiz.ts                 # WebSocket hook + REST hooks
├── components/
│   └── live-quiz/
│       ├── host-panel.tsx               # Instructor: question control, answer stats
│       ├── player-view.tsx              # Student: answer buttons, waiting screen
│       ├── lobby.tsx                    # Join code, participant list, QR
│       ├── answer-distribution.tsx      # Real-time bar chart of answers
│       └── podium.tsx                   # Final results animation
└── app/dashboard/courses/[courseId]/
    └── live/
        ├── [sessionId]/page.tsx         # Live session (host or player)
        └── page.tsx                     # List active sessions
```

## Task 11: Database Migration — LiveAnswer + LiveSession Extensions

**Files:**
- Create: `backend/alembic/versions/xxxx_live_quiz.py`
- Create: `backend/app/models/live_answer.py`

- [ ] **Step 1: Create migration**

```python
# Adds: join_code, time_limit_seconds, settings to live_sessions
# Creates: live_answers table
```

Columns per the spec:
- `live_sessions.join_code` VARCHAR(6), unique while active
- `live_sessions.time_limit_seconds` INTEGER DEFAULT 30
- `live_sessions.settings` JSONB DEFAULT '{}'
- `live_answers`: id, session_id, user_id, question_index, answer, answered_at, points_earned, UNIQUE(session_id, user_id, question_index)

- [ ] **Step 2: Create LiveAnswer SQLAlchemy model**

```python
# backend/app/models/live_answer.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime, timezone
from app.models.base import Base


class LiveAnswer(Base):
    __tablename__ = "live_answers"
    __table_args__ = (
        UniqueConstraint("session_id", "user_id", "question_index"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("live_sessions.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    question_index = Column(Integer, nullable=False)
    answer = Column(String(10), nullable=False)
    answered_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    points_earned = Column(Integer, default=0)
```

- [ ] **Step 3: Update LiveSession model**

Add `join_code`, `time_limit_seconds`, `settings` columns.

- [ ] **Step 4: Run migration**

```bash
cd backend && alembic upgrade head
```

## Task 12: Live Quiz Service

**Files:**
- Create: `backend/app/services/live_quiz.py`
- Create: `backend/tests/test_live_quiz_service.py`

- [ ] **Step 1: Write tests for scoring and state machine**

```python
# backend/tests/test_live_quiz_service.py
import pytest
from app.services.live_quiz import calculate_points, SessionState


class TestCalculatePoints:
    def test_instant_correct_answer(self):
        points = calculate_points(
            is_correct=True, elapsed_seconds=0, time_limit=30, base_points=1000
        )
        assert points == 1000

    def test_half_time_correct(self):
        points = calculate_points(
            is_correct=True, elapsed_seconds=15, time_limit=30, base_points=1000
        )
        assert points == 500

    def test_wrong_answer_zero_points(self):
        points = calculate_points(
            is_correct=False, elapsed_seconds=5, time_limit=30, base_points=1000
        )
        assert points == 0

    def test_at_time_limit(self):
        points = calculate_points(
            is_correct=True, elapsed_seconds=30, time_limit=30, base_points=1000
        )
        assert points == 0


class TestSessionState:
    def test_initial_state(self):
        state = SessionState(session_id="test", total_questions=5, time_limit=30)
        assert state.status == "waiting"
        assert state.current_question_index == 0

    def test_start_transitions_to_active(self):
        state = SessionState(session_id="test", total_questions=5, time_limit=30)
        state.start()
        assert state.status == "active"

    def test_next_question_advances(self):
        state = SessionState(session_id="test", total_questions=5, time_limit=30)
        state.start()
        state.next_question()
        assert state.current_question_index == 1

    def test_last_question_finishes(self):
        state = SessionState(session_id="test", total_questions=2, time_limit=30)
        state.start()
        state.next_question()  # index 1 (last)
        state.next_question()  # past last
        assert state.status == "finished"
```

- [ ] **Step 2: Run tests — should fail**

```bash
cd backend && python -m pytest tests/test_live_quiz_service.py -v
```

- [ ] **Step 3: Implement live quiz service**

```python
# backend/app/services/live_quiz.py
import secrets
import string
from dataclasses import dataclass, field
from datetime import datetime, timezone
from fastapi import WebSocket


def generate_join_code(length: int = 6) -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


def calculate_points(
    is_correct: bool, elapsed_seconds: float, time_limit: int, base_points: int = 1000
) -> int:
    if not is_correct:
        return 0
    ratio = max(0, 1 - elapsed_seconds / time_limit)
    return int(base_points * ratio)


@dataclass
class SessionState:
    session_id: str
    total_questions: int
    time_limit: int
    status: str = "waiting"
    current_question_index: int = 0
    question_started_at: datetime | None = None
    player_scores: dict[str, int] = field(default_factory=dict)  # user_id -> total
    player_answers: dict[str, dict[int, str]] = field(default_factory=dict)  # user_id -> {q_index: answer}

    def start(self):
        self.status = "active"
        self.question_started_at = datetime.now(timezone.utc)

    def next_question(self):
        self.current_question_index += 1
        if self.current_question_index >= self.total_questions:
            self.status = "finished"
        else:
            self.question_started_at = datetime.now(timezone.utc)

    def record_answer(self, user_id: str, answer: str, points: int):
        if user_id not in self.player_answers:
            self.player_answers[user_id] = {}
        self.player_answers[user_id][self.current_question_index] = answer
        self.player_scores[user_id] = self.player_scores.get(user_id, 0) + points

    def get_leaderboard(self, top_n: int = 10) -> list[dict]:
        sorted_players = sorted(
            self.player_scores.items(), key=lambda x: x[1], reverse=True
        )[:top_n]
        return [
            {"user_id": uid, "score": score, "rank": i + 1}
            for i, (uid, score) in enumerate(sorted_players)
        ]


class ConnectionManager:
    """Manage WebSocket connections per session."""

    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}  # session_id -> [ws]
        self.sessions: dict[str, SessionState] = {}        # session_id -> state

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        if session_id not in self.connections:
            self.connections[session_id] = []
        self.connections[session_id].append(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket):
        if session_id in self.connections:
            self.connections[session_id] = [
                ws for ws in self.connections[session_id] if ws != websocket
            ]

    async def broadcast(self, session_id: str, message: dict):
        import json
        if session_id in self.connections:
            data = json.dumps(message)
            for ws in self.connections[session_id]:
                try:
                    await ws.send_text(data)
                except Exception:
                    pass  # connection closed

    def get_session(self, session_id: str) -> SessionState | None:
        return self.sessions.get(session_id)

    def create_session(self, session_id: str, total_questions: int, time_limit: int) -> SessionState:
        state = SessionState(
            session_id=session_id,
            total_questions=total_questions,
            time_limit=time_limit,
        )
        self.sessions[session_id] = state
        return state

    def remove_session(self, session_id: str):
        self.sessions.pop(session_id, None)
        self.connections.pop(session_id, None)


# Singleton — in-memory, single process
manager = ConnectionManager()
```

- [ ] **Step 4: Run tests — should pass**

```bash
cd backend && python -m pytest tests/test_live_quiz_service.py -v
```

## Task 13: Live Quiz API Endpoints

**Files:**
- Create: `backend/app/schemas/live.py`
- Create: `backend/app/api/live.py`
- Modify: `backend/app/api/__init__.py`
- Create: `backend/tests/test_api_live.py`

- [ ] **Step 1: Create live session schemas**

```python
# backend/app/schemas/live.py
from pydantic import BaseModel


class CreateLiveSessionRequest(BaseModel):
    quiz_id: str
    time_limit_seconds: int = 30
    settings: dict = {}  # shuffle_questions, show_leaderboard_after_each


class LiveSessionResponse(BaseModel):
    id: str
    quiz_id: str
    course_id: str
    host_id: str
    join_code: str
    status: str
    participant_count: int
    time_limit_seconds: int
    created_at: str


class LiveLeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    full_name: str
    score: int
```

- [ ] **Step 2: Create REST endpoints**

```python
# backend/app/api/live.py
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from app.services.live_quiz import manager, generate_join_code

router = APIRouter(tags=["live-quiz"])

@router.post("/courses/{course_id}/live-sessions")
async def create_live_session(course_id: str, req: CreateLiveSessionRequest, ...):
    """Instructor creates a live session from an existing quiz."""
    # Verify instructor, fetch quiz, generate join_code
    # Create LiveSession DB row with join_code
    # Initialize in-memory SessionState via manager
    ...

@router.get("/courses/{course_id}/live-sessions")
async def list_live_sessions(course_id: str, ...):
    """List active sessions for a course."""
    ...

@router.get("/live-sessions/{session_id}")
async def get_live_session(session_id: str, ...):
    """Session detail including join code."""
    ...
```

- [ ] **Step 3: Create WebSocket endpoint**

```python
@router.websocket("/live/{session_id}")
async def websocket_live(websocket: WebSocket, session_id: str):
    """
    WebSocket handler for live quiz.
    
    Messages from host:
      {"type": "next_question"}
      {"type": "end_session"}
    
    Messages from player:
      {"type": "answer", "question_index": 0, "answer": "B"}
    
    Broadcasts:
      {"type": "session_state", "status": ..., "participant_count": ...}
      {"type": "question", "index": ..., "question_text": ..., "options": ..., "time_limit": ...}
      {"type": "answer_reveal", "correct_answer": ..., "stats": {...}}
      {"type": "leaderboard", "top_10": [...]}
      {"type": "session_ended", "final_leaderboard": [...]}
    """
    await manager.connect(session_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            
            if msg_type == "next_question":
                # Host advances to next question
                # Broadcast question to all
                ...
            elif msg_type == "answer":
                # Player submits answer
                # Calculate points, store LiveAnswer
                # Broadcast updated stats
                ...
            elif msg_type == "end_session":
                # Host ends session
                # Broadcast final leaderboard
                # Award XP to participants
                ...
    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)
```

- [ ] **Step 4: Register router**

- [ ] **Step 5: Write WebSocket integration tests**

Test with multiple concurrent WebSocket clients, verify message flow and scoring.

```bash
cd backend && python -m pytest tests/test_api_live.py -v
```

## Task 14: Frontend — Live Quiz UI

**Files:**
- Create: `frontend/src/hooks/use-live-quiz.ts`
- Create: `frontend/src/components/live-quiz/lobby.tsx`
- Create: `frontend/src/components/live-quiz/host-panel.tsx`
- Create: `frontend/src/components/live-quiz/player-view.tsx`
- Create: `frontend/src/components/live-quiz/answer-distribution.tsx`
- Create: `frontend/src/components/live-quiz/podium.tsx`
- Create: `frontend/src/app/dashboard/courses/[courseId]/live/page.tsx`
- Create: `frontend/src/app/dashboard/courses/[courseId]/live/[sessionId]/page.tsx`

- [ ] **Step 1: Create WebSocket hook**

```typescript
// frontend/src/hooks/use-live-quiz.ts
import { useCallback, useEffect, useRef, useState } from "react";

type MessageHandler = (data: any) => void;

export function useLiveQuiz(sessionId: string, token: string) {
  const wsRef = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<string>("connecting");
  const [participants, setParticipants] = useState(0);
  const [currentQuestion, setCurrentQuestion] = useState<any>(null);
  const [leaderboard, setLeaderboard] = useState<any[]>([]);

  useEffect(() => {
    const wsUrl = `${process.env.NEXT_PUBLIC_WS_URL}/api/live/${sessionId}?token=${token}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      switch (data.type) {
        case "session_state":
          setStatus(data.status);
          setParticipants(data.participant_count);
          break;
        case "question":
          setCurrentQuestion(data);
          break;
        case "leaderboard":
          setLeaderboard(data.top_10);
          break;
        case "session_ended":
          setStatus("finished");
          setLeaderboard(data.final_leaderboard);
          break;
      }
    };

    ws.onclose = () => setStatus("disconnected");
    return () => ws.close();
  }, [sessionId, token]);

  const sendAnswer = useCallback((questionIndex: number, answer: string) => {
    wsRef.current?.send(JSON.stringify({ type: "answer", question_index: questionIndex, answer }));
  }, []);

  const nextQuestion = useCallback(() => {
    wsRef.current?.send(JSON.stringify({ type: "next_question" }));
  }, []);

  const endSession = useCallback(() => {
    wsRef.current?.send(JSON.stringify({ type: "end_session" }));
  }, []);

  return { status, participants, currentQuestion, leaderboard, sendAnswer, nextQuestion, endSession };
}
```

- [ ] **Step 2: Create lobby component**

Show join code (large text), QR code (using a QR library or canvas), participant list updating in real-time. "Start" button for host.

- [ ] **Step 3: Create host panel component**

Question display, "Next Question" button, real-time answer distribution chart, timer countdown, mini leaderboard.

- [ ] **Step 4: Create player view component**

Question text + 4 answer buttons (A/B/C/D) with color coding. Timer bar. Waiting screen between questions. Points animation on correct answer.

- [ ] **Step 5: Create answer distribution chart**

Horizontal bar chart showing count per option (A: 7, B: 12, C: 3, D: 2). Updates in real-time. Highlight correct answer on reveal.

- [ ] **Step 6: Create podium component**

Top 3 players with animated podium. Full leaderboard below. Confetti animation for winner.

- [ ] **Step 7: Create live session pages**

- List page: shows active sessions in course, "Create Live Session" button for instructors
- Session page: routes to host-panel (if instructor) or player-view (if student)

- [ ] **Step 8: Add navigation links**

Add "Live Quiz" to course page tabs and sidebar.

- [ ] **Step 9: Run frontend build + lint**

```bash
cd frontend && npm run build && npm run lint
```

**Checkpoint: Phase 2d complete.** Instructors can host live quiz sessions. Students join via code, answer in real-time, see live leaderboard.

---

# Phase 2e — i18n (Traditional Chinese)

**Goal:** Support Traditional Chinese UI for HKUST Cantonese/Mandarin speakers. All static strings translated, locale-aware formatting, user preference persisted.

## File Structure

### New Files

```
frontend/
├── messages/
│   ├── en.json                          # English strings (extracted from hardcoded)
│   └── zh-Hant.json                     # Traditional Chinese translations
├── src/
│   ├── i18n/
│   │   ├── request.ts                   # next-intl server config
│   │   └── routing.ts                   # Locale routing config
│   └── components/
│       └── layout/
│           └── language-toggle.tsx       # Language switcher in navbar
```

### Modified Files

```
frontend/
├── package.json                         # Add next-intl dependency
├── src/app/layout.tsx                   # Wrap with NextIntlClientProvider
├── src/app/**/*.tsx                     # Replace hardcoded strings with t() calls
├── src/components/**/*.tsx              # Replace hardcoded strings with t() calls
└── src/proxy.ts                         # Add locale detection
```

## Task 15: Install and Configure next-intl

- [ ] **Step 1: Install next-intl**

```bash
cd frontend && npm install next-intl
```

- [ ] **Step 2: Create i18n configuration**

```typescript
// frontend/src/i18n/request.ts
import { getRequestConfig } from "next-intl/server";
import { cookies } from "next/headers";

export default getRequestConfig(async () => {
  const cookieStore = await cookies();
  const locale = cookieStore.get("NEXT_LOCALE")?.value || "en";
  return {
    locale,
    messages: (await import(`../../messages/${locale}.json`)).default,
  };
});
```

- [ ] **Step 3: Create English message file**

Extract all hardcoded strings from existing components into `messages/en.json`.

Structure:
```json
{
  "common": {
    "loading": "Loading...",
    "error": "Something went wrong",
    "save": "Save",
    "cancel": "Cancel",
    "delete": "Delete",
    "search": "Search..."
  },
  "nav": {
    "dashboard": "Dashboard",
    "courses": "Courses",
    "quizzes": "Quizzes",
    "flashcards": "Flashcards",
    "pronunciation": "Pronunciation",
    "liveQuiz": "Live Quiz",
    "signOut": "Sign Out"
  },
  "dashboard": {
    "welcome": "Welcome back",
    "recentCourses": "Recent Courses",
    "yourProgress": "Your Progress"
  },
  "course": {
    "create": "Create Course",
    "materials": "Materials",
    "students": "Students",
    "leaderboard": "Leaderboard",
    "enrolledStudents": "{count} students"
  },
  "quiz": {
    "startQuiz": "Start Quiz",
    "submitAnswers": "Submit Answers",
    "question": "Question {current} of {total}",
    "score": "Your Score: {score}%",
    "generateQuiz": "Generate Quiz"
  },
  "flashcard": {
    "flip": "Flip",
    "again": "Again",
    "hard": "Hard",
    "good": "Good",
    "easy": "Easy",
    "cardsRemaining": "{count} cards remaining"
  },
  "gamification": {
    "xpPoints": "{xp} XP",
    "streakDays": "{days} day streak",
    "badges": "Badges",
    "leaderboard": "Leaderboard"
  },
  "pronunciation": {
    "record": "Record",
    "stop": "Stop Recording",
    "grading": "Grading your pronunciation...",
    "overallScore": "Overall Score",
    "accuracy": "Accuracy",
    "fluency": "Fluency"
  }
}
```

- [ ] **Step 4: Create Traditional Chinese message file**

```json
// frontend/messages/zh-Hant.json
{
  "common": {
    "loading": "載入中...",
    "error": "發生錯誤",
    "save": "儲存",
    "cancel": "取消",
    "delete": "刪除",
    "search": "搜尋..."
  },
  "nav": {
    "dashboard": "儀表板",
    "courses": "課程",
    "quizzes": "測驗",
    "flashcards": "字卡",
    "pronunciation": "發音練習",
    "liveQuiz": "即時問答",
    "signOut": "登出"
  },
  "dashboard": {
    "welcome": "歡迎回來",
    "recentCourses": "最近課程",
    "yourProgress": "學習進度"
  },
  "course": {
    "create": "建立課程",
    "materials": "教材",
    "students": "學生",
    "leaderboard": "排行榜",
    "enrolledStudents": "{count} 位學生"
  },
  "quiz": {
    "startQuiz": "開始測驗",
    "submitAnswers": "提交答案",
    "question": "第 {current} 題，共 {total} 題",
    "score": "你的分數：{score}%",
    "generateQuiz": "生成測驗"
  },
  "flashcard": {
    "flip": "翻轉",
    "again": "重來",
    "hard": "困難",
    "good": "良好",
    "easy": "簡單",
    "cardsRemaining": "剩餘 {count} 張"
  },
  "gamification": {
    "xpPoints": "{xp} 經驗值",
    "streakDays": "連續 {days} 天",
    "badges": "徽章",
    "leaderboard": "排行榜"
  },
  "pronunciation": {
    "record": "錄音",
    "stop": "停止錄音",
    "grading": "正在評分...",
    "overallScore": "總分",
    "accuracy": "準確度",
    "fluency": "流暢度"
  }
}
```

## Task 16: Integrate i18n into App

- [ ] **Step 1: Wrap root layout with NextIntlClientProvider**

Read Next.js 16 docs first — the integration pattern may differ from Next.js 14/15.

- [ ] **Step 2: Replace hardcoded strings in all components**

Systematically go through each component file and replace English strings with `t('key')` calls:

```tsx
// Before
<Button>Start Quiz</Button>

// After
const t = useTranslations("quiz");
<Button>{t("startQuiz")}</Button>
```

Priority order:
1. Layout components (sidebar, navbar) — seen on every page
2. Dashboard pages
3. Course page tabs
4. Quiz player
5. Flashcard player
6. Gamification components
7. Pronunciation components
8. Live quiz components

- [ ] **Step 3: Create language toggle component**

```tsx
// frontend/src/components/layout/language-toggle.tsx
"use client";
import { useLocale } from "next-intl";

export function LanguageToggle() {
  const locale = useLocale();

  function switchLocale(newLocale: string) {
    document.cookie = `NEXT_LOCALE=${newLocale};path=/;max-age=31536000`;
    window.location.reload();
  }

  return (
    <button onClick={() => switchLocale(locale === "en" ? "zh-Hant" : "en")}>
      {locale === "en" ? "繁體中文" : "English"}
    </button>
  );
}
```

- [ ] **Step 4: Add language toggle to navbar**

- [ ] **Step 5: Verify all keys present in both locales**

Write a test or script that compares `en.json` and `zh-Hant.json` key structures.

```bash
cd frontend && node -e "
const en = require('./messages/en.json');
const zhHant = require('./messages/zh-Hant.json');
function getKeys(obj, prefix='') {
  return Object.entries(obj).flatMap(([k, v]) =>
    typeof v === 'object' ? getKeys(v, prefix+k+'.') : [prefix+k]
  );
}
const enKeys = new Set(getKeys(en));
const zhKeys = new Set(getKeys(zhHant));
const missing = [...enKeys].filter(k => !zhKeys.has(k));
if (missing.length) { console.error('Missing zh-Hant keys:', missing); process.exit(1); }
console.log('All keys present in both locales');
"
```

- [ ] **Step 6: Run frontend build + lint**

```bash
cd frontend && npm run build && npm run lint
```

**Checkpoint: Phase 2e complete.** UI supports English and Traditional Chinese. User can toggle language from the navbar.

---

# Testing Strategy

## Unit Tests (all phases)

| Phase | Test File | What |
|-------|-----------|------|
| 2a | `test_retriever_hybrid.py` | RRF merge, fulltext retrieve |
| 2b | `test_gamification.py` | XP calc, streak logic, badge rules |
| 2b | `test_api_progress.py` | Progress + leaderboard endpoints |
| 2c | `test_speech_service.py` | Mocked Azure/iFlytek, score normalization |
| 2c | `test_api_speech.py` | Grade + history endpoints |
| 2d | `test_live_quiz_service.py` | Scoring, state machine, join code |
| 2d | `test_api_live.py` | REST + WebSocket integration |

## Integration Tests

- **Hybrid search**: Real pgvector + tsvector DB, verify RRF ranking improves on keyword queries
- **Gamification**: End-to-end quiz attempt → XP award → badge check → leaderboard update
- **Live quiz**: Multi-client WebSocket test with concurrent answers

## Frontend E2E (Playwright)

- [ ] Leaderboard loads on course page
- [ ] Pronunciation recorder captures audio and shows results
- [ ] Live quiz join flow: enter code → lobby → answer → results
- [ ] Language toggle switches all visible text

## Coverage Target

80%+ on all new services and API routes.

```bash
cd backend && python -m pytest --cov=app --cov-report=term-missing
```

---

# Deployment Notes

- **Azure Speech SDK**: Requires native binaries. Add to Railway Dockerfile: `apt-get install -y libssl-dev libasound2-dev`
- **WebSocket**: Railway supports WebSocket on the same port. No additional config needed.
- **Environment variables**: Add to Railway: `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION`, `IFLYTEK_APP_ID`, `IFLYTEK_API_KEY`, `IFLYTEK_API_SECRET`
- **Frontend env**: Add `NEXT_PUBLIC_WS_URL` for WebSocket endpoint (same as API URL but `wss://`)
- **Database**: Run migrations via `alembic upgrade head` after deploy

---

# Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Azure Speech SDK binary issues on Railway | Medium | High | Test in Docker locally first, pin version |
| WebSocket scaling (>100 concurrent) | Low | Medium | Single-process sufficient for class sizes; document Redis upgrade path |
| iFlytek API latency from HK | Medium | Medium | Add timeout + retry, consider regional endpoint |
| next-intl + Next.js 16 compatibility | Medium | Medium | Read Next.js 16 docs carefully, test with canary build |
| tsvector CJK tokenization quality | Low | Low | `simple` config for CJK; course language field selects config |
