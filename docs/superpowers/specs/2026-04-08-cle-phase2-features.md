# Meli Phase 2 — Features Design Specification

**Date:** 2026-04-08
**Status:** Draft
**Parent Spec:** [CLE Platform Design](2026-04-05-cle-platform-design.md)

---

## 1. Scope

Phase 2 adds six feature areas on top of the Phase 1 foundation (courses, RAG pipeline, quiz/flashcard generation, frontend UI):

| # | Feature | Priority | Complexity |
|---|---------|----------|------------|
| 2a | Hybrid Search (tsvector + pgvector) | High | Low |
| 2b | Gamification (XP, streaks, badges, leaderboard) | High | Medium |
| 2c | Pronunciation Grading (Azure Speech + iFlytek) | Medium | High |
| 2d | Live Quiz (Kahoot-style WebSocket) | Medium | High |
| 2e | i18n (Traditional Chinese UI) | Low | Medium |

**Spaced Repetition** (SM-2) is already implemented in Phase 1b — `api/flashcards.py:189-215`. No further work needed.

Each sub-phase is independently deployable and testable.

## 2. Existing Infrastructure

These models/columns already exist and will be leveraged:

- **Chunk.tsvector_content** — TSVECTOR column, currently unpopulated (hybrid search)
- **PronunciationScore** — Full model with scores, provider, audio R2 key
- **StudentProgress** — XP, streaks, badges, per-course activity counts
- **LiveSession** — quiz_id, host_id, status, current_question_index, participant_count
- **SessionSummary** — course summaries by session date

---

## 2a. Hybrid Search

### Problem

Current retrieval uses only vector cosine similarity. Exact keyword matches (terminology, formulas, proper nouns) get diluted by semantic neighbors. Combining full-text search with vector search improves recall for both conceptual and keyword queries.

### Design

**Reciprocal Rank Fusion (RRF):** Run both searches independently, merge via RRF scoring:

```
RRF_score(doc) = sum(1 / (k + rank_in_list)) for each list containing doc
```

Where `k = 60` (standard constant).

**Changes:**

1. **Migration**: Add GIN index on `chunks.tsvector_content`, add trigger to auto-populate tsvector on INSERT/UPDATE
2. **Pipeline**: Populate `tsvector_content` during document processing (chunker already stores content)
3. **Retriever**: New `hybrid_retrieve()` that runs vector + tsvector queries in parallel, merges via RRF
4. **Config**: Add `search_mode` setting (vector | fulltext | hybrid), default to hybrid

### tsvector Configuration

Use `english` config by default. For CJK content, use `simple` config (PostgreSQL doesn't have native CJK tokenization, but `simple` splits on whitespace which works adequately for chunked Chinese text).

The course `language` field determines which tsvector config to use.

### API Changes

- `POST /api/rag/query` — add optional `search_mode` param (default: hybrid)
- No new endpoints needed

---

## 2b. Gamification

### Problem

Students lack motivation signals. Activity tracking exists (StudentProgress model) but nothing writes to it or displays it.

### Design

**XP System:**
- Quiz attempt: `score * 10` XP (e.g., 80% score = 800 XP)
- Flashcard review session (5+ cards): 50 XP
- Pronunciation practice: 30 XP per attempt
- Document read (future): 10 XP

**Streak System:**
- Track consecutive days with any learning activity
- Reset to 0 if a day is missed
- Updated via `last_activity_date` comparison

**Badges** (stored as JSON array in `student_progress.badges`):
- `first_quiz` — Complete first quiz
- `perfect_score` — Score 100% on any quiz
- `streak_7` — 7-day streak
- `streak_30` — 30-day streak
- `flashcard_master` — Review 100 flashcards
- `speed_learner` — Complete quiz in under 60 seconds

**Leaderboard:**
- Per-course XP ranking
- Top 10 students visible to all course members
- Instructor sees full leaderboard

### Backend Changes

1. **Service**: `gamification.py` — `award_xp()`, `update_streak()`, `check_badges()`, `get_leaderboard()`
2. **API**: `GET /api/courses/{id}/leaderboard` — paginated leaderboard
3. **API**: `GET /api/courses/{id}/progress` — current user's progress for a course
4. **Integration points**: Call `award_xp()` from quiz attempt, flashcard progress, pronunciation grade endpoints

### Frontend Changes

1. **Student dashboard**: Progress card with XP, streak, recent badges
2. **Course page**: Leaderboard tab
3. **Toast notifications**: XP gained, badge earned animations

---

## 2c. Pronunciation Grading

### Problem

Language learning requires speaking practice. Students need automated pronunciation feedback with detailed scoring.

### Design

**Dual Provider Strategy:**
- **English**: Azure Speech SDK — Pronunciation Assessment API
- **Chinese (Mandarin)**: iFlytek Speech Evaluation API

Both providers return per-word/per-syllable scores. We normalize to a common format.

### Flow

```
Student records audio in browser (MediaRecorder API)
  → Upload audio blob to backend (multipart/form-data)
  → Backend saves to R2 (temporary)
  → Backend calls speech provider based on language
  → Provider returns detailed scoring
  → Backend stores in pronunciation_scores table
  → Backend returns normalized result to frontend
  → Frontend renders word-by-word heatmap
```

### Azure Speech Pronunciation Assessment

```python
# Uses azure-cognitiveservices-speech SDK
speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
pronunciation_config = speechsdk.PronunciationAssessmentConfig(
    reference_text=target_text,
    grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
    granularity=speechsdk.PronunciationAssessmentGranularity.Word,
    enable_prosody_assessment=True,
)
```

Returns: accuracy_score, fluency_score, completeness_score, prosody_score, per-word scores.

### iFlytek Speech Evaluation

REST API with HMAC-SHA256 authentication. Send audio + reference text, receive JSON with scores.

### API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/speech/grade` | any enrolled | Grade pronunciation (audio + reference text) |
| GET | `/api/courses/{id}/pronunciation-history` | any enrolled | User's pronunciation scores for a course |

### Config

```python
# config.py additions
azure_speech_key: str = ""
azure_speech_region: str = ""
iflytek_app_id: str = ""
iflytek_api_key: str = ""
iflytek_api_secret: str = ""
```

### Frontend

1. **Pronunciation practice page**: Text display + record button + waveform
2. **Results view**: Overall score + word-by-word heatmap (green/yellow/red)
3. **History**: Past attempts with trend chart

---

## 2d. Live Quiz (Kahoot-style)

### Problem

Instructors want real-time in-class quiz competitions. Current quizzes are async/self-paced.

### Design

**Session Lifecycle:**

```
WAITING → ACTIVE → QUESTION → ANSWER_REVEAL → (next question or) FINISHED
```

**WebSocket Protocol:**

Instructor (host) controls flow. Students (players) answer questions.

**Server → All:**
```json
{"type": "session_state", "status": "waiting", "participant_count": 12}
{"type": "question", "index": 0, "question_text": "...", "options": {...}, "time_limit": 30}
{"type": "time_up"}
{"type": "answer_reveal", "correct_answer": "B", "stats": {"A": 3, "B": 7, "C": 1, "D": 1}}
{"type": "leaderboard", "top_10": [...]}
{"type": "session_ended", "final_leaderboard": [...]}
```

**Player → Server:**
```json
{"type": "answer", "question_index": 0, "answer": "B"}
```

**Host → Server:**
```json
{"type": "next_question"}
{"type": "end_session"}
```

**Scoring:** Points = `base_points * (1 - elapsed / time_limit)`. Faster correct answers earn more.

### Backend Architecture

- **In-memory session state** (dict of session_id → SessionState). No Redis needed — single-process monolith.
- **WebSocket manager**: Track connections per session, broadcast messages
- **Session CRUD API**: REST endpoints to create/list/join sessions
- **Cleanup**: Sessions auto-expire after 2 hours of inactivity

### API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/courses/{id}/live-sessions` | instructor | Create live session from a quiz |
| GET | `/api/courses/{id}/live-sessions` | any enrolled | List active sessions |
| GET | `/api/live-sessions/{id}` | any enrolled | Session detail + join code |
| WS | `/api/live/{session_id}` | any enrolled | WebSocket connection |

### Frontend

1. **Host view**: Question control panel, real-time answer distribution chart, leaderboard
2. **Player view**: Join screen (enter code), question display, answer buttons, waiting screens
3. **Lobby**: QR code / session code, participant list
4. **Results**: Final leaderboard with podium animation

### Models

Extend `LiveSession` with:
- `join_code` (6-char alphanumeric, unique while active)
- `time_limit_seconds` (per question, default 30)
- `settings` JSONB (shuffle_questions, show_leaderboard_after_each)

New model: `LiveAnswer` (session_id, user_id, question_index, answer, answered_at, points_earned)

---

## 2e. i18n (Traditional Chinese)

### Problem

HKUST serves Cantonese and Mandarin speakers. UI should support Traditional Chinese.

### Design

**Library:** `next-intl` (already planned in platform spec)

**Scope:**
- All static UI strings (buttons, labels, headers, navigation, error messages)
- Date/time formatting (locale-aware via `Intl.DateTimeFormat`)
- Number formatting
- NOT course content (that stays in whatever language the instructor uploads)

**Locale files:**
```
frontend/messages/
├── en.json      # English (default)
└── zh-Hant.json # Traditional Chinese
```

**Language detection:**
1. User preference stored in Clerk metadata (if set)
2. Browser `Accept-Language` header
3. Fallback: English

**Switching:** Language toggle in navbar/sidebar. Preference persisted to Clerk user metadata.

### Implementation

1. Wrap app with `NextIntlClientProvider`
2. Replace all hardcoded strings with `t('key')` calls
3. Create message files for both locales
4. Add locale prefix to routes (`/en/dashboard`, `/zh-Hant/dashboard`) or use cookie-based (simpler)
5. RTL not needed (neither English nor Chinese is RTL)

---

## 3. New Dependencies

```
# Backend (add to requirements.txt)
azure-cognitiveservices-speech==1.42.0   # Azure pronunciation assessment
httpx==0.28.1                            # Already present — for iFlytek REST calls

# Frontend (add to package.json)
next-intl                                # i18n framework
```

## 4. Database Migrations

**Migration 1 (Hybrid Search):**
```sql
-- Populate tsvector for existing chunks
UPDATE chunks SET tsvector_content = to_tsvector('english', content)
WHERE tsvector_content IS NULL;

-- GIN index
CREATE INDEX idx_chunks_tsvector ON chunks USING GIN (tsvector_content);

-- Auto-populate trigger
CREATE OR REPLACE FUNCTION chunks_tsvector_trigger() RETURNS trigger AS $$
BEGIN
    NEW.tsvector_content := to_tsvector('english', NEW.content);
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER tsvector_update BEFORE INSERT OR UPDATE OF content
ON chunks FOR EACH ROW EXECUTE FUNCTION chunks_tsvector_trigger();
```

**Migration 2 (Live Quiz):**
```sql
ALTER TABLE live_sessions ADD COLUMN join_code VARCHAR(6);
ALTER TABLE live_sessions ADD COLUMN time_limit_seconds INTEGER DEFAULT 30;
ALTER TABLE live_sessions ADD COLUMN settings JSONB DEFAULT '{}';
CREATE UNIQUE INDEX idx_live_sessions_join_code ON live_sessions (join_code) WHERE status != 'finished';

CREATE TABLE live_answers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES live_sessions(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    question_index INTEGER NOT NULL,
    answer VARCHAR(10) NOT NULL,
    answered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    points_earned INTEGER DEFAULT 0,
    UNIQUE(session_id, user_id, question_index)
);
```

## 5. Testing Strategy

- **Hybrid search**: Integration test with real pgvector DB, verify RRF ranking
- **Gamification**: Unit tests for XP calculation, streak logic, badge rules
- **Pronunciation**: Mock Azure/iFlytek responses, test score normalization
- **Live quiz**: WebSocket integration tests with multiple concurrent clients
- **i18n**: Verify all keys present in both locales, snapshot tests for translated pages
- **Target**: 80%+ coverage on all new services

## 6. Implementation Order

```
Phase 2a (Hybrid Search)     → Low risk, improves existing RAG quality
Phase 2b (Gamification)      → Moderate, models exist, motivates students
Phase 2c (Pronunciation)     → New external deps, needs API keys
Phase 2d (Live Quiz)         → Most complex (WebSocket), build last
Phase 2e (i18n)              → Cross-cutting, apply after all UI is stable
```
