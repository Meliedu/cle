# Meli Schema Upgrade — Course Operating System

> **Status:** Design spec, ready to implement
> **Target stack:** PostgreSQL 16+ with `pgvector`, `pg_trgm`. Existing roles: `meli_app`, `meli_readonly`, `meli_admin`.
> **Migration tool:** Alembic (existing `alembic_version` table)

---

## 0. TL;DR

The current schema has a strong **evidence layer** (what students did) but no **meaning layer** (what they need to learn, when, through which concepts). This upgrade adds the meaning layer on top of the existing evidence layer without disturbing it.

**Core additions:**

- `course_modules`, `class_sessions`, `assignments` — curriculum + calendar + deadlines
- `learning_objectives` — objectives at session/module/course scope
- `concepts` + `concept_prerequisites` — knowledge graph (DAG)
- **8 tagging tables** linking concepts to chunks, questions, flashcards, pronunciation items, pool items, objectives, sessions, assignments
- `concept_mastery` — per-student EMA-based mastery per concept
- `next_actions`, `instructor_alerts` — materialized decision-layer output
- `syllabus_imports`, `student_daily_briefings` — syllabus engine + memory cache

**Modifications to existing tables:** add `session_id` / `module_id` foreign keys to `quizzes`, `flashcard_sets`, `pronunciation_sets`, `documents`.

**Preserved as-is:** `bandit_models`, `scheduler_models`, `revision_pool_items`, `recalibration_*`, `chunks`, all `documents`/`enrollments`/`canvas_*` machinery. The selection/policy layer stays — concept filtering composes on top.

---

## 1. Diagnosis: What the current schema cannot answer

| Product requirement | Answerable today? | Why not |
|---|---|---|
| "This student is weak at *inference*" | ❌ | Only dimensions are `content_type` and `difficulty`. No concept axis. |
| "Generate today's class prep brief" | ❌ | No session entity. `session_summaries.session_date` is post-hoc only. |
| "Who hasn't done this week's reading?" | ❌ | No assignment / reading entity. |
| "Show only quizzes covering *fixed cost*" | ❌ | No question → concept tagging. |
| "Across 5 courses, what should the student do first?" | ❌ | No cross-course priority surface, no deadline-aware ranking. |
| "Which students missed this concept's prerequisites?" | ❌ | No prerequisite graph. |
| "What does today's lecture need to emphasize?" | ❌ | No mapping from cohort weakness → upcoming session. |

The `bandit_models` / `scheduler_models` / `revision_pool_items` / `recalibration_*` machinery is solid as a **policy/selection layer**. The fix is not to replace it — it's to give it a meaning layer to filter on.

---

## 2. Target architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                          DECISION LAYER                              │
│   next_actions   ·   instructor_alerts   ·   daily_briefings         │
│   (materialized; recomputed on triggers, served from cache)          │
└────┬─────────────────┬─────────────────┬─────────────────┬──────────┘
     │                 │                 │                 │
     ▼                 ▼                 ▼                 ▼
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────┐
│CURRICULUM│    │ CONTENT  │    │ EVIDENCE │    │   MASTERY    │
│          │    │          │    │          │    │              │
│ courses  │    │documents │    │ quiz_    │    │  concept_    │
│ modules  │◄───┤ chunks   │    │  attempts│    │   mastery    │
│ sessions │    │ quizzes  │    │ flashcard│    │   (EMA)      │
│objectives│    │flashcards│    │  progress│    │              │
│assignments│   │ pronunc. │    │ revision_│    │  bandit_     │
│          │    │pool_items│    │ attempts │    │   models     │
└──────────┘    └────┬─────┘    │ pronunc_ │    │  scheduler_  │
                     │          │  scores  │    │   models     │
                     ▼          │ live_    │    │              │
              ┌──────────────┐  │ answers  │    └──────┬───────┘
              │   CONCEPTS   │  └────┬─────┘           │
              │              │       │                  │
              │  concepts    │       │                  │
              │  prereqs DAG │       │                  │
              │              │       │                  │
              │  + 8 tagging │◄──────┴──────────────────┘
              │    tables    │   (concepts referenced from
              └──────────────┘    every learnable artifact
                                  and every attempt)
```

Concepts are the **join key** that lets the decision layer reason across content, evidence, and mastery. Without them, every query collapses to per-course aggregates.

---

## 3. New tables — full DDL

All DDL below follows the conventions of the existing schema (UUID PKs with `gen_random_uuid()` default, `timestamptz` timestamps, soft-delete via `deleted_at`, named CHECK constraints, explicit FK ON DELETE behavior, standard permissions block).

### 3.1 Curriculum

#### `course_modules` — weeks / chapters / units (tree)

```sql
CREATE TABLE public.course_modules (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    course_id uuid NOT NULL,
    parent_id uuid NULL,
    name varchar(255) NOT NULL,
    description varchar NULL,
    order_index int4 NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    deleted_at timestamptz NULL,
    CONSTRAINT course_modules_pkey PRIMARY KEY (id),
    CONSTRAINT ck_course_modules_no_self_parent CHECK (id <> parent_id),
    CONSTRAINT course_modules_course_id_fkey
        FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE,
    CONSTRAINT course_modules_parent_id_fkey
        FOREIGN KEY (parent_id) REFERENCES public.course_modules(id) ON DELETE SET NULL
);
CREATE INDEX idx_course_modules_course_order
    ON public.course_modules (course_id, parent_id NULLS FIRST, order_index)
    WHERE deleted_at IS NULL;

ALTER TABLE public.course_modules OWNER TO postgres;
GRANT ALL ON TABLE public.course_modules TO postgres;
GRANT UPDATE, INSERT, SELECT, DELETE ON TABLE public.course_modules TO meli_app;
GRANT SELECT ON TABLE public.course_modules TO meli_readonly;
GRANT ALL ON TABLE public.course_modules TO meli_admin;
```

#### `class_sessions` — calendar anchor for everything

This is the single most important new table. It is what the student calendar opens, what `documents` / `quizzes` / `flashcard_sets` attach to, and what instructor prep briefs hang off.

```sql
CREATE TABLE public.class_sessions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    course_id uuid NOT NULL,
    module_id uuid NULL,
    session_index int4 NOT NULL,           -- 1-based within course
    title varchar(255) NULL,
    scheduled_at timestamptz NOT NULL,
    duration_minutes int4 DEFAULT 60 NOT NULL,
    location varchar(255) NULL,
    status varchar(20) DEFAULT 'planned' NOT NULL,
    pre_class_briefing jsonb NULL,         -- LLM-generated, instructor-editable
    post_class_summary jsonb NULL,         -- generated after session ends
    canvas_event_id varchar(100) NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    deleted_at timestamptz NULL,
    CONSTRAINT class_sessions_pkey PRIMARY KEY (id),
    CONSTRAINT ck_class_sessions_status_valid
        CHECK (status IN ('planned','in_progress','taught','cancelled')),
    CONSTRAINT uq_class_sessions_course_index
        UNIQUE (course_id, session_index),
    CONSTRAINT class_sessions_course_id_fkey
        FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE,
    CONSTRAINT class_sessions_module_id_fkey
        FOREIGN KEY (module_id) REFERENCES public.course_modules(id) ON DELETE SET NULL
);
CREATE INDEX idx_class_sessions_course_scheduled
    ON public.class_sessions (course_id, scheduled_at)
    WHERE deleted_at IS NULL;
CREATE INDEX idx_class_sessions_upcoming
    ON public.class_sessions (scheduled_at)
    WHERE deleted_at IS NULL AND status = 'planned';

ALTER TABLE public.class_sessions OWNER TO postgres;
GRANT ALL ON TABLE public.class_sessions TO postgres;
GRANT UPDATE, INSERT, SELECT, DELETE ON TABLE public.class_sessions TO meli_app;
GRANT SELECT ON TABLE public.class_sessions TO meli_readonly;
GRANT ALL ON TABLE public.class_sessions TO meli_admin;
```

`pre_class_briefing` shape (jsonb):

```json
{
  "topic": "Cost allocation methods",
  "key_concepts": ["uuid1", "uuid2"],
  "warm_up_questions": ["...", "..."],
  "discussion_prompts": ["..."],
  "expected_weak_points": [
    {"concept_id": "uuid1", "cohort_mastery": 0.42, "rationale": "..."}
  ],
  "recap_from_last_session": "...",
  "generated_at": "2026-04-28T09:00:00Z",
  "instructor_edited": false
}
```

#### `learning_objectives` — what the student should be able to do

Polymorphic scope so a single table covers course/module/session objectives. We don't enforce the cross-table FK; the `scope_type` discriminator + application-level validation is sufficient and keeps the table simple.

```sql
CREATE TABLE public.learning_objectives (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    course_id uuid NOT NULL,
    scope_type varchar(20) NOT NULL,
    scope_id uuid NOT NULL,
    statement varchar NOT NULL,
    bloom_level varchar(20) NULL,
    order_index int4 DEFAULT 0 NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    deleted_at timestamptz NULL,
    CONSTRAINT learning_objectives_pkey PRIMARY KEY (id),
    CONSTRAINT ck_learning_objectives_scope_valid
        CHECK (scope_type IN ('course','module','session')),
    CONSTRAINT ck_learning_objectives_bloom_valid
        CHECK (bloom_level IS NULL OR bloom_level IN
            ('remember','understand','apply','analyze','evaluate','create')),
    CONSTRAINT learning_objectives_course_id_fkey
        FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE
);
CREATE INDEX idx_learning_objectives_scope
    ON public.learning_objectives (scope_type, scope_id)
    WHERE deleted_at IS NULL;
CREATE INDEX idx_learning_objectives_course
    ON public.learning_objectives (course_id)
    WHERE deleted_at IS NULL;

ALTER TABLE public.learning_objectives OWNER TO postgres;
GRANT ALL ON TABLE public.learning_objectives TO postgres;
GRANT UPDATE, INSERT, SELECT, DELETE ON TABLE public.learning_objectives TO meli_app;
GRANT SELECT ON TABLE public.learning_objectives TO meli_readonly;
GRANT ALL ON TABLE public.learning_objectives TO meli_admin;
```

#### `assignments` — graded deliverables with deadlines

Distinct from `quizzes` (which are formative practice). An assignment is anything the student must submit by a deadline that contributes to their grade. Quizzes can optionally back an assignment (link via `quiz_id`).

```sql
CREATE TABLE public.assignments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    course_id uuid NOT NULL,
    module_id uuid NULL,
    session_id uuid NULL,
    title varchar(255) NOT NULL,
    description varchar NULL,
    kind varchar(30) NOT NULL,
    due_at timestamptz NOT NULL,
    available_from timestamptz NULL,
    weight numeric(5,2) NULL,            -- % of course grade
    quiz_id uuid NULL,                   -- if backed by a Meli quiz
    canvas_assignment_id varchar(100) NULL,
    is_published bool DEFAULT false NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    deleted_at timestamptz NULL,
    CONSTRAINT assignments_pkey PRIMARY KEY (id),
    CONSTRAINT ck_assignments_kind_valid
        CHECK (kind IN ('essay','project','quiz','reading','presentation',
                        'lab','problem_set','participation','other')),
    CONSTRAINT assignments_course_id_fkey
        FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE,
    CONSTRAINT assignments_module_id_fkey
        FOREIGN KEY (module_id) REFERENCES public.course_modules(id) ON DELETE SET NULL,
    CONSTRAINT assignments_session_id_fkey
        FOREIGN KEY (session_id) REFERENCES public.class_sessions(id) ON DELETE SET NULL,
    CONSTRAINT assignments_quiz_id_fkey
        FOREIGN KEY (quiz_id) REFERENCES public.quizzes(id) ON DELETE SET NULL,
    CONSTRAINT assignments_created_by_fkey
        FOREIGN KEY (created_by) REFERENCES public.users(id)
);
CREATE INDEX idx_assignments_course_due
    ON public.assignments (course_id, due_at)
    WHERE deleted_at IS NULL;
CREATE INDEX idx_assignments_upcoming
    ON public.assignments (due_at)
    WHERE deleted_at IS NULL AND is_published = true;

ALTER TABLE public.assignments OWNER TO postgres;
GRANT ALL ON TABLE public.assignments TO postgres;
GRANT UPDATE, INSERT, SELECT, DELETE ON TABLE public.assignments TO meli_app;
GRANT SELECT ON TABLE public.assignments TO meli_readonly;
GRANT ALL ON TABLE public.assignments TO meli_admin;
```

#### `assignment_submissions` — student × assignment status

```sql
CREATE TABLE public.assignment_submissions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    assignment_id uuid NOT NULL,
    user_id uuid NOT NULL,
    status varchar(20) NOT NULL,
    submitted_at timestamptz NULL,
    score numeric(6,2) NULL,
    feedback varchar NULL,
    canvas_submission_id varchar(100) NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT assignment_submissions_pkey PRIMARY KEY (id),
    CONSTRAINT uq_assignment_submissions_user
        UNIQUE (assignment_id, user_id),
    CONSTRAINT ck_assignment_submissions_status_valid
        CHECK (status IN ('not_started','in_progress','submitted','late','graded','excused')),
    CONSTRAINT assignment_submissions_assignment_id_fkey
        FOREIGN KEY (assignment_id) REFERENCES public.assignments(id) ON DELETE CASCADE,
    CONSTRAINT assignment_submissions_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE
);
CREATE INDEX idx_assignment_submissions_user_status
    ON public.assignment_submissions (user_id, status);

ALTER TABLE public.assignment_submissions OWNER TO postgres;
GRANT ALL ON TABLE public.assignment_submissions TO postgres;
GRANT UPDATE, INSERT, SELECT, DELETE ON TABLE public.assignment_submissions TO meli_app;
GRANT SELECT ON TABLE public.assignment_submissions TO meli_readonly;
GRANT ALL ON TABLE public.assignment_submissions TO meli_admin;
```

### 3.2 Knowledge graph

#### `concepts` — the central join key

```sql
CREATE TABLE public.concepts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    course_id uuid NOT NULL,
    name varchar(255) NOT NULL,
    description varchar NULL,
    canonical_id uuid NULL,            -- self-FK: when set, this is a duplicate of canonical_id
    embedding public.vector(1536) NULL, -- adjust dim to match your embedding model
    extracted_from_chunk_id uuid NULL, -- provenance for LLM-extracted concepts
    instructor_curated bool DEFAULT false NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    deleted_at timestamptz NULL,
    CONSTRAINT concepts_pkey PRIMARY KEY (id),
    CONSTRAINT ck_concepts_no_self_canonical CHECK (id <> canonical_id),
    CONSTRAINT concepts_course_id_fkey
        FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE,
    CONSTRAINT concepts_canonical_id_fkey
        FOREIGN KEY (canonical_id) REFERENCES public.concepts(id) ON DELETE SET NULL,
    CONSTRAINT concepts_extracted_from_chunk_id_fkey
        FOREIGN KEY (extracted_from_chunk_id) REFERENCES public.chunks(id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX uq_concepts_course_lower_name
    ON public.concepts (course_id, lower(name))
    WHERE deleted_at IS NULL AND canonical_id IS NULL;
CREATE INDEX idx_concepts_embedding
    ON public.concepts USING hnsw (embedding vector_cosine_ops)
    WITH (m='16', ef_construction='200');
CREATE INDEX idx_concepts_course
    ON public.concepts (course_id)
    WHERE deleted_at IS NULL;

ALTER TABLE public.concepts OWNER TO postgres;
GRANT ALL ON TABLE public.concepts TO postgres;
GRANT UPDATE, INSERT, SELECT, DELETE ON TABLE public.concepts TO meli_app;
GRANT SELECT ON TABLE public.concepts TO meli_readonly;
GRANT ALL ON TABLE public.concepts TO meli_admin;
```

**Notes on `canonical_id`:** LLM extraction will produce duplicates ("fixed cost", "Fixed Cost", "fixed costs"). Rather than hard-deduping, set `canonical_id` to point duplicates at the canonical concept. Application code resolves through `canonical_id` when reading. This is reversible — you can split a merge later.

#### `concept_prerequisites` — DAG edges

```sql
CREATE TABLE public.concept_prerequisites (
    prereq_concept_id uuid NOT NULL,
    dependent_concept_id uuid NOT NULL,
    strength numeric(3,2) DEFAULT 1.00 NOT NULL,  -- 0..1; soft if low
    instructor_verified bool DEFAULT false NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT concept_prerequisites_pkey
        PRIMARY KEY (prereq_concept_id, dependent_concept_id),
    CONSTRAINT ck_concept_prerequisites_no_self
        CHECK (prereq_concept_id <> dependent_concept_id),
    CONSTRAINT ck_concept_prerequisites_strength_range
        CHECK (strength >= 0 AND strength <= 1),
    CONSTRAINT concept_prerequisites_prereq_fkey
        FOREIGN KEY (prereq_concept_id) REFERENCES public.concepts(id) ON DELETE CASCADE,
    CONSTRAINT concept_prerequisites_dependent_fkey
        FOREIGN KEY (dependent_concept_id) REFERENCES public.concepts(id) ON DELETE CASCADE
);
CREATE INDEX idx_concept_prerequisites_dependent
    ON public.concept_prerequisites (dependent_concept_id);

ALTER TABLE public.concept_prerequisites OWNER TO postgres;
GRANT ALL ON TABLE public.concept_prerequisites TO postgres;
GRANT UPDATE, INSERT, SELECT, DELETE ON TABLE public.concept_prerequisites TO meli_app;
GRANT SELECT ON TABLE public.concept_prerequisites TO meli_readonly;
GRANT ALL ON TABLE public.concept_prerequisites TO meli_admin;
```

**DAG enforcement:** Postgres can't enforce acyclic. Application validates on insert via `WITH RECURSIVE` cycle check. See §7.4.

### 3.3 Concept tagging — 8 join tables

These are the join keys that make decision-layer queries fast. All follow the same shape.

```sql
-- chunks → concepts
CREATE TABLE public.chunk_concepts (
    chunk_id uuid NOT NULL,
    concept_id uuid NOT NULL,
    weight numeric(3,2) DEFAULT 1.00 NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT chunk_concepts_pkey PRIMARY KEY (chunk_id, concept_id),
    CONSTRAINT ck_chunk_concepts_weight_range CHECK (weight >= 0 AND weight <= 1),
    CONSTRAINT chunk_concepts_chunk_id_fkey
        FOREIGN KEY (chunk_id) REFERENCES public.chunks(id) ON DELETE CASCADE,
    CONSTRAINT chunk_concepts_concept_id_fkey
        FOREIGN KEY (concept_id) REFERENCES public.concepts(id) ON DELETE CASCADE
);
CREATE INDEX idx_chunk_concepts_concept ON public.chunk_concepts (concept_id);

-- questions → concepts
CREATE TABLE public.question_concepts (
    question_id uuid NOT NULL,
    concept_id uuid NOT NULL,
    weight numeric(3,2) DEFAULT 1.00 NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT question_concepts_pkey PRIMARY KEY (question_id, concept_id),
    CONSTRAINT ck_question_concepts_weight_range CHECK (weight >= 0 AND weight <= 1),
    CONSTRAINT question_concepts_question_id_fkey
        FOREIGN KEY (question_id) REFERENCES public.questions(id) ON DELETE CASCADE,
    CONSTRAINT question_concepts_concept_id_fkey
        FOREIGN KEY (concept_id) REFERENCES public.concepts(id) ON DELETE CASCADE
);
CREATE INDEX idx_question_concepts_concept ON public.question_concepts (concept_id);

-- flashcard_cards → concepts
CREATE TABLE public.flashcard_card_concepts (
    flashcard_card_id uuid NOT NULL,
    concept_id uuid NOT NULL,
    weight numeric(3,2) DEFAULT 1.00 NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT flashcard_card_concepts_pkey PRIMARY KEY (flashcard_card_id, concept_id),
    CONSTRAINT ck_flashcard_card_concepts_weight_range CHECK (weight >= 0 AND weight <= 1),
    CONSTRAINT flashcard_card_concepts_card_id_fkey
        FOREIGN KEY (flashcard_card_id) REFERENCES public.flashcard_cards(id) ON DELETE CASCADE,
    CONSTRAINT flashcard_card_concepts_concept_id_fkey
        FOREIGN KEY (concept_id) REFERENCES public.concepts(id) ON DELETE CASCADE
);
CREATE INDEX idx_flashcard_card_concepts_concept ON public.flashcard_card_concepts (concept_id);

-- pronunciation_items → concepts
CREATE TABLE public.pronunciation_item_concepts (
    pronunciation_item_id uuid NOT NULL,
    concept_id uuid NOT NULL,
    weight numeric(3,2) DEFAULT 1.00 NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT pronunciation_item_concepts_pkey PRIMARY KEY (pronunciation_item_id, concept_id),
    CONSTRAINT ck_pron_item_concepts_weight_range CHECK (weight >= 0 AND weight <= 1),
    CONSTRAINT pron_item_concepts_item_id_fkey
        FOREIGN KEY (pronunciation_item_id) REFERENCES public.pronunciation_items(id) ON DELETE CASCADE,
    CONSTRAINT pron_item_concepts_concept_id_fkey
        FOREIGN KEY (concept_id) REFERENCES public.concepts(id) ON DELETE CASCADE
);
CREATE INDEX idx_pron_item_concepts_concept ON public.pronunciation_item_concepts (concept_id);

-- revision_pool_items → concepts
CREATE TABLE public.pool_item_concepts (
    pool_item_id uuid NOT NULL,
    concept_id uuid NOT NULL,
    weight numeric(3,2) DEFAULT 1.00 NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT pool_item_concepts_pkey PRIMARY KEY (pool_item_id, concept_id),
    CONSTRAINT ck_pool_item_concepts_weight_range CHECK (weight >= 0 AND weight <= 1),
    CONSTRAINT pool_item_concepts_pool_item_id_fkey
        FOREIGN KEY (pool_item_id) REFERENCES public.revision_pool_items(id) ON DELETE CASCADE,
    CONSTRAINT pool_item_concepts_concept_id_fkey
        FOREIGN KEY (concept_id) REFERENCES public.concepts(id) ON DELETE CASCADE
);
CREATE INDEX idx_pool_item_concepts_concept ON public.pool_item_concepts (concept_id);

-- learning_objectives → concepts
CREATE TABLE public.objective_concepts (
    objective_id uuid NOT NULL,
    concept_id uuid NOT NULL,
    weight numeric(3,2) DEFAULT 1.00 NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT objective_concepts_pkey PRIMARY KEY (objective_id, concept_id),
    CONSTRAINT ck_objective_concepts_weight_range CHECK (weight >= 0 AND weight <= 1),
    CONSTRAINT objective_concepts_objective_id_fkey
        FOREIGN KEY (objective_id) REFERENCES public.learning_objectives(id) ON DELETE CASCADE,
    CONSTRAINT objective_concepts_concept_id_fkey
        FOREIGN KEY (concept_id) REFERENCES public.concepts(id) ON DELETE CASCADE
);
CREATE INDEX idx_objective_concepts_concept ON public.objective_concepts (concept_id);

-- class_sessions → concepts
CREATE TABLE public.session_concepts (
    session_id uuid NOT NULL,
    concept_id uuid NOT NULL,
    role varchar(20) DEFAULT 'covered' NOT NULL,  -- 'introduced' | 'covered' | 'reinforced'
    weight numeric(3,2) DEFAULT 1.00 NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT session_concepts_pkey PRIMARY KEY (session_id, concept_id),
    CONSTRAINT ck_session_concepts_role_valid
        CHECK (role IN ('introduced','covered','reinforced')),
    CONSTRAINT ck_session_concepts_weight_range CHECK (weight >= 0 AND weight <= 1),
    CONSTRAINT session_concepts_session_id_fkey
        FOREIGN KEY (session_id) REFERENCES public.class_sessions(id) ON DELETE CASCADE,
    CONSTRAINT session_concepts_concept_id_fkey
        FOREIGN KEY (concept_id) REFERENCES public.concepts(id) ON DELETE CASCADE
);
CREATE INDEX idx_session_concepts_concept ON public.session_concepts (concept_id);

-- assignments → concepts
CREATE TABLE public.assignment_concepts (
    assignment_id uuid NOT NULL,
    concept_id uuid NOT NULL,
    weight numeric(3,2) DEFAULT 1.00 NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT assignment_concepts_pkey PRIMARY KEY (assignment_id, concept_id),
    CONSTRAINT ck_assignment_concepts_weight_range CHECK (weight >= 0 AND weight <= 1),
    CONSTRAINT assignment_concepts_assignment_id_fkey
        FOREIGN KEY (assignment_id) REFERENCES public.assignments(id) ON DELETE CASCADE,
    CONSTRAINT assignment_concepts_concept_id_fkey
        FOREIGN KEY (concept_id) REFERENCES public.concepts(id) ON DELETE CASCADE
);
CREATE INDEX idx_assignment_concepts_concept ON public.assignment_concepts (concept_id);

-- Apply standard permissions to all 8 tables in one block
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'chunk_concepts','question_concepts','flashcard_card_concepts',
    'pronunciation_item_concepts','pool_item_concepts','objective_concepts',
    'session_concepts','assignment_concepts'
  ] LOOP
    EXECUTE format('ALTER TABLE public.%I OWNER TO postgres', t);
    EXECUTE format('GRANT ALL ON TABLE public.%I TO postgres', t);
    EXECUTE format('GRANT UPDATE, INSERT, SELECT, DELETE ON TABLE public.%I TO meli_app', t);
    EXECUTE format('GRANT SELECT ON TABLE public.%I TO meli_readonly', t);
    EXECUTE format('GRANT ALL ON TABLE public.%I TO meli_admin', t);
  END LOOP;
END $$;
```

### 3.4 Mastery

#### `concept_mastery` — per-student × per-concept EMA

```sql
CREATE TABLE public.concept_mastery (
    user_id uuid NOT NULL,
    concept_id uuid NOT NULL,
    course_id uuid NOT NULL,                              -- denormalized for query speed
    mastery_score numeric(4,3) DEFAULT 0.000 NOT NULL,    -- 0..1, EMA of correctness
    confidence numeric(4,3) DEFAULT 0.000 NOT NULL,       -- 0..1, grows with attempts
    attempt_count int4 DEFAULT 0 NOT NULL,
    correct_count int4 DEFAULT 0 NOT NULL,
    last_attempt_at timestamptz NULL,
    last_correct_at timestamptz NULL,
    last_seen_session_id uuid NULL,                       -- which session most recently covered this
    updated_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT concept_mastery_pkey PRIMARY KEY (user_id, concept_id),
    CONSTRAINT ck_concept_mastery_score_range
        CHECK (mastery_score >= 0 AND mastery_score <= 1),
    CONSTRAINT ck_concept_mastery_confidence_range
        CHECK (confidence >= 0 AND confidence <= 1),
    CONSTRAINT concept_mastery_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE,
    CONSTRAINT concept_mastery_concept_id_fkey
        FOREIGN KEY (concept_id) REFERENCES public.concepts(id) ON DELETE CASCADE,
    CONSTRAINT concept_mastery_course_id_fkey
        FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE,
    CONSTRAINT concept_mastery_last_seen_session_id_fkey
        FOREIGN KEY (last_seen_session_id) REFERENCES public.class_sessions(id) ON DELETE SET NULL
);
CREATE INDEX idx_concept_mastery_user_course
    ON public.concept_mastery (user_id, course_id);
CREATE INDEX idx_concept_mastery_weak
    ON public.concept_mastery (course_id, concept_id, mastery_score)
    WHERE mastery_score < 0.5 AND confidence > 0.3;
CREATE INDEX idx_concept_mastery_stale
    ON public.concept_mastery (user_id, last_attempt_at);

ALTER TABLE public.concept_mastery OWNER TO postgres;
GRANT ALL ON TABLE public.concept_mastery TO postgres;
GRANT UPDATE, INSERT, SELECT, DELETE ON TABLE public.concept_mastery TO meli_app;
GRANT SELECT ON TABLE public.concept_mastery TO meli_readonly;
GRANT ALL ON TABLE public.concept_mastery TO meli_admin;
```

See §7.1 for the EMA update formula.

### 3.5 Decision layer outputs

#### `next_actions` — what each student should do next

This is **cache, not source of truth.** Recompute, don't migrate. The `expires_at` column makes stale rows safe to ignore.

```sql
CREATE TABLE public.next_actions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    course_id uuid NULL,                  -- NULL = cross-course action
    action_type varchar(40) NOT NULL,
    target_kind varchar(40) NULL,
    target_id uuid NULL,
    priority_score numeric(7,3) NOT NULL, -- higher = more urgent
    reason jsonb NOT NULL,
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT next_actions_pkey PRIMARY KEY (id),
    CONSTRAINT ck_next_actions_action_type_valid
        CHECK (action_type IN (
            'review_concept','prep_session','complete_assignment',
            'do_quiz','practice_weakness','catch_up_reading',
            'flashcard_review','pronunciation_practice','watch_recording'
        )),
    CONSTRAINT ck_next_actions_target_kind_valid
        CHECK (target_kind IS NULL OR target_kind IN (
            'concept','class_session','assignment','quiz',
            'flashcard_set','pronunciation_set','document','chunk'
        )),
    CONSTRAINT next_actions_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE,
    CONSTRAINT next_actions_course_id_fkey
        FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE
);
CREATE INDEX idx_next_actions_user_active
    ON public.next_actions (user_id, priority_score DESC)
    WHERE consumed_at IS NULL AND expires_at > now();
CREATE INDEX idx_next_actions_cleanup
    ON public.next_actions (expires_at)
    WHERE consumed_at IS NULL;

ALTER TABLE public.next_actions OWNER TO postgres;
GRANT ALL ON TABLE public.next_actions TO postgres;
GRANT UPDATE, INSERT, SELECT, DELETE ON TABLE public.next_actions TO meli_app;
GRANT SELECT ON TABLE public.next_actions TO meli_readonly;
GRANT ALL ON TABLE public.next_actions TO meli_admin;
```

`reason` jsonb shape:

```json
{
  "factors": [
    {"name": "deadline_proximity", "value": 0.8, "weight": 0.4},
    {"name": "concept_weakness", "value": 0.6, "weight": 0.3},
    {"name": "prereq_for_upcoming_session", "value": 1.0, "weight": 0.3}
  ],
  "explanation": "Quiz on cost allocation due in 18h; you're at 42% mastery on related concepts.",
  "concepts": ["uuid1", "uuid2"],
  "computed_by": "decision_engine_v1",
  "computed_at": "2026-04-28T12:00:00Z"
}
```

#### `instructor_alerts` — risk signals for the instructor

```sql
CREATE TABLE public.instructor_alerts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    course_id uuid NOT NULL,
    instructor_id uuid NOT NULL,
    target_user_id uuid NULL,             -- NULL = course-level alert
    alert_type varchar(40) NOT NULL,
    severity varchar(20) NOT NULL,
    title varchar(255) NOT NULL,
    reason jsonb NOT NULL,
    status varchar(20) DEFAULT 'open' NOT NULL,
    resolved_at timestamptz NULL,
    resolved_by uuid NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT instructor_alerts_pkey PRIMARY KEY (id),
    CONSTRAINT ck_instructor_alerts_severity_valid
        CHECK (severity IN ('info','warning','critical')),
    CONSTRAINT ck_instructor_alerts_status_valid
        CHECK (status IN ('open','dismissed','resolved')),
    CONSTRAINT ck_instructor_alerts_alert_type_valid
        CHECK (alert_type IN (
            'student_disengaging','student_falling_behind',
            'cohort_concept_weakness','prereq_gap_for_upcoming_session',
            'low_quiz_participation','missed_deadline','content_gap'
        )),
    CONSTRAINT instructor_alerts_course_id_fkey
        FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE,
    CONSTRAINT instructor_alerts_instructor_id_fkey
        FOREIGN KEY (instructor_id) REFERENCES public.users(id) ON DELETE CASCADE,
    CONSTRAINT instructor_alerts_target_user_id_fkey
        FOREIGN KEY (target_user_id) REFERENCES public.users(id) ON DELETE CASCADE,
    CONSTRAINT instructor_alerts_resolved_by_fkey
        FOREIGN KEY (resolved_by) REFERENCES public.users(id)
);
CREATE INDEX idx_instructor_alerts_open
    ON public.instructor_alerts (instructor_id, severity, created_at DESC)
    WHERE status = 'open';
CREATE INDEX idx_instructor_alerts_course_open
    ON public.instructor_alerts (course_id, created_at DESC)
    WHERE status = 'open';

ALTER TABLE public.instructor_alerts OWNER TO postgres;
GRANT ALL ON TABLE public.instructor_alerts TO postgres;
GRANT UPDATE, INSERT, SELECT, DELETE ON TABLE public.instructor_alerts TO meli_app;
GRANT SELECT ON TABLE public.instructor_alerts TO meli_readonly;
GRANT ALL ON TABLE public.instructor_alerts TO meli_admin;
```

### 3.6 Syllabus + memory

#### `syllabus_imports` — track parser runs and their outputs

The syllabus engine parses the document into a structured payload, then *applies* it (creates modules / sessions / objectives). This split lets the instructor review and edit the parsed output before commit.

```sql
CREATE TABLE public.syllabus_imports (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    course_id uuid NOT NULL,
    document_id uuid NULL,
    raw_text varchar NOT NULL,
    parsed_payload jsonb NOT NULL,
    status varchar(20) NOT NULL,
    error_message varchar NULL,
    applied_at timestamptz NULL,
    applied_by uuid NULL,
    created_by uuid NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT syllabus_imports_pkey PRIMARY KEY (id),
    CONSTRAINT ck_syllabus_imports_status_valid
        CHECK (status IN ('pending','parsed','applied','failed','superseded')),
    CONSTRAINT syllabus_imports_course_id_fkey
        FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE,
    CONSTRAINT syllabus_imports_document_id_fkey
        FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE SET NULL,
    CONSTRAINT syllabus_imports_created_by_fkey
        FOREIGN KEY (created_by) REFERENCES public.users(id),
    CONSTRAINT syllabus_imports_applied_by_fkey
        FOREIGN KEY (applied_by) REFERENCES public.users(id)
);
CREATE INDEX idx_syllabus_imports_course
    ON public.syllabus_imports (course_id, created_at DESC);

ALTER TABLE public.syllabus_imports OWNER TO postgres;
GRANT ALL ON TABLE public.syllabus_imports TO postgres;
GRANT UPDATE, INSERT, SELECT, DELETE ON TABLE public.syllabus_imports TO meli_app;
GRANT SELECT ON TABLE public.syllabus_imports TO meli_readonly;
GRANT ALL ON TABLE public.syllabus_imports TO meli_admin;
```

`parsed_payload` shape:

```json
{
  "course": {"name": "...", "semester": "...", "language": "..."},
  "modules": [
    {"name": "Week 1: Introduction", "order_index": 1, "sessions": [...]}
  ],
  "sessions": [
    {
      "module_index": 1, "session_index": 1,
      "scheduled_at": "2026-09-01T10:00:00Z",
      "title": "...", "objectives": ["..."], "concepts": ["..."]
    }
  ],
  "assignments": [
    {"title": "...", "kind": "essay", "due_at": "...", "weight": 15.0}
  ],
  "schema_version": "v1"
}
```

#### `student_daily_briefings` — TTL-cached "today" view

This is a cache, recomputed each morning by background job. Don't query it for analytics — it exists so the dashboard load is fast.

```sql
CREATE TABLE public.student_daily_briefings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    briefing_date date NOT NULL,
    content jsonb NOT NULL,
    generated_at timestamptz DEFAULT now() NOT NULL,
    expires_at timestamptz NOT NULL,
    CONSTRAINT student_daily_briefings_pkey PRIMARY KEY (id),
    CONSTRAINT uq_student_daily_briefings_user_date
        UNIQUE (user_id, briefing_date),
    CONSTRAINT student_daily_briefings_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE
);
CREATE INDEX idx_student_daily_briefings_cleanup
    ON public.student_daily_briefings (expires_at);

ALTER TABLE public.student_daily_briefings OWNER TO postgres;
GRANT ALL ON TABLE public.student_daily_briefings TO postgres;
GRANT UPDATE, INSERT, SELECT, DELETE ON TABLE public.student_daily_briefings TO meli_app;
GRANT SELECT ON TABLE public.student_daily_briefings TO meli_readonly;
GRANT ALL ON TABLE public.student_daily_briefings TO meli_admin;
```

---

## 4. Modifications to existing tables

These are additive — they widen existing tables with optional FKs to the new curriculum entities. Backfill is `NULL`-safe; nothing breaks for older rows.

```sql
-- Link content to sessions/modules (all nullable)
ALTER TABLE public.documents
    ADD COLUMN session_id uuid NULL REFERENCES public.class_sessions(id) ON DELETE SET NULL,
    ADD COLUMN module_id uuid NULL REFERENCES public.course_modules(id) ON DELETE SET NULL;
CREATE INDEX idx_documents_session ON public.documents (session_id) WHERE session_id IS NOT NULL;

ALTER TABLE public.quizzes
    ADD COLUMN session_id uuid NULL REFERENCES public.class_sessions(id) ON DELETE SET NULL,
    ADD COLUMN module_id uuid NULL REFERENCES public.course_modules(id) ON DELETE SET NULL;
CREATE INDEX idx_quizzes_session ON public.quizzes (session_id) WHERE session_id IS NOT NULL;

ALTER TABLE public.flashcard_sets
    ADD COLUMN session_id uuid NULL REFERENCES public.class_sessions(id) ON DELETE SET NULL,
    ADD COLUMN module_id uuid NULL REFERENCES public.course_modules(id) ON DELETE SET NULL;

ALTER TABLE public.pronunciation_sets
    ADD COLUMN session_id uuid NULL REFERENCES public.class_sessions(id) ON DELETE SET NULL,
    ADD COLUMN module_id uuid NULL REFERENCES public.course_modules(id) ON DELETE SET NULL;

-- Link revision attempts back to the concept(s) they exercised, denormalized for speed.
-- This is in addition to going through pool_item_concepts.
ALTER TABLE public.revision_attempts
    ADD COLUMN primary_concept_id uuid NULL REFERENCES public.concepts(id) ON DELETE SET NULL;
CREATE INDEX idx_revision_attempts_concept
    ON public.revision_attempts (user_id, primary_concept_id, created_at DESC)
    WHERE primary_concept_id IS NOT NULL;

-- Bind quiz attempts to a session for live-quiz analytics
ALTER TABLE public.quiz_attempts
    ADD COLUMN class_session_id uuid NULL REFERENCES public.class_sessions(id) ON DELETE SET NULL;
```

**Important non-changes:**

- `bandit_models` and `scheduler_models` are **left alone**. They model selection policy, not concept mastery. There's a temptation to merge them — resist for now (see §11).
- `revision_pool_items` keeps its `difficulty` column. The new concept tagging is additive.
- `student_progress` stays as the gamification surface; concept-level mastery lives in `concept_mastery`.

---

## 5. Migration plan

Each phase is a single Alembic revision. Phases must run in order; each is safe to ship independently — earlier features keep working without later phases.

### Phase 1 — Curriculum + calendar (foundation)

`course_modules`, `class_sessions`, `assignments`, `assignment_submissions`, `learning_objectives`, plus `session_id`/`module_id` columns on `documents`/`quizzes`/`flashcard_sets`/`pronunciation_sets`/`quiz_attempts`.

After this phase: instructors can define a course calendar; existing content can be linked to sessions; student calendar UI becomes possible. **Nothing concept-aware yet.**

### Phase 2 — Concepts + tagging

`concepts`, `concept_prerequisites`, all 8 tagging tables. **No mastery yet.**

After this phase: instructors can curate a concept graph; new content gets tagged on creation; existing content gets tagged via backfill (§6). Search/filter UIs by concept become possible.

### Phase 3 — Mastery

`concept_mastery` plus the EMA update service (§7.1).

After this phase: every attempt updates per-concept mastery in real time. Decision queries on weakness become possible.

### Phase 4 — Decision layer

`next_actions`, `instructor_alerts`, plus the background jobs that materialize them (§8).

After this phase: student dashboards show ranked next actions; instructors see alerts.

### Phase 5 — Syllabus engine + memory

`syllabus_imports`, `student_daily_briefings`. The syllabus parser job populates Phase 1 + Phase 2 entities from a single uploaded document.

After this phase: `syllabus.pdf` → full course operating plan in one shot, instructor reviews and applies.

---

## 6. Backfill strategy

After Phase 2 ships, existing courses have content but no concepts. Backfill is a one-time batch job per course.

### 6.1 Concept extraction from chunks

For each course:

1. Sample chunks across all documents (don't re-process every chunk — `n=200` per course is enough to seed).
2. Send chunks in batches to LLM with a structured-output prompt:
   - "Extract 5–15 concepts that this passage teaches. Output JSON array of `{name, description}`."
3. Insert into `concepts` (course-scoped). Generate embeddings.
4. **Dedupe pass:** for each new concept, find nearest neighbor in same course via embedding cosine distance. If `< 0.15` distance and Levenshtein-similar names, set `canonical_id` to point at the existing concept instead of inserting a duplicate.
5. Re-process all chunks to tag against the now-stable concept set (`chunk_concepts`).

Use the existing `tasks` table — `task_type='backfill_concepts'`, payload `{course_id, phase}`.

### 6.2 Cascade tagging

Once `chunk_concepts` is populated, tag downstream artifacts via their `source_chunk_id`:

```sql
-- questions inherit concepts from source chunk (weight discounted)
INSERT INTO public.question_concepts (question_id, concept_id, weight)
SELECT q.id, cc.concept_id, cc.weight * 0.8
FROM public.questions q
JOIN public.chunk_concepts cc ON cc.chunk_id = q.source_chunk_id
WHERE q.source_chunk_id IS NOT NULL
ON CONFLICT DO NOTHING;

-- same pattern for flashcard_cards, pronunciation_items, revision_pool_items
```

For artifacts without a `source_chunk_id`, run the LLM tagger on the artifact text directly.

### 6.3 Session linking

For existing `quizzes`/`flashcard_sets` with no session, leave `session_id` NULL. New ones link explicitly. Optionally, instructor UI offers "link to session" as a one-click action based on creation date proximity.

### 6.4 Mastery seeding

After Phase 3 ships, replay the last 90 days of `quiz_attempts`, `flashcard_progress`, `revision_attempts`, `pronunciation_scores` through the EMA update logic. Older history is ignored — confidence stays low until the student re-engages.

---

## 7. Decision layer mechanics

This is where the design earns its keep. The decision layer is **not a new ML model.** It is a set of materialized rank queries over the four foundation layers.

### 7.1 Concept mastery EMA

After every attempt that ties to a concept, update `concept_mastery`:

```
new_score = α * outcome + (1 − α) * old_score
```

with:

- `outcome ∈ [0, 1]` — quiz correctness (0/1), flashcard grade (mapped: again=0, hard=0.4, good=0.8, easy=1.0), pronunciation score / 100, revision attempt score
- `α = max(0.1, 0.5 / (1 + 0.1 * attempt_count))` — large at first, decays as evidence accumulates
- `confidence = 1 − exp(−attempt_count / 5)` — saturates around 8–10 attempts

For multi-concept artifacts, distribute the outcome by tag weight. Implement as an UPSERT in a Python service called from the attempt handlers; resist putting it in a DB trigger — too much business logic to debug.

### 7.2 Student `next_actions` scoring

For each (user, course) pair, score candidate actions and keep the top N. Inputs:

- `M_c` = mastery for concept c
- `D_a` = days until assignment a's deadline (clamped to ≥ 0)
- `S_s` = days until session s starts (clamped to ≥ 0)
- `P_s` = "prerequisite pressure" for session s — sum `weight × (1 − M_c)` over its concepts

Action types and rough scoring (tune empirically):

| Action | Score formula |
|---|---|
| `complete_assignment` | `5.0 × weight × (1 / (1 + D_a))` if not_started/in_progress |
| `prep_session` | `3.0 × P_s × (1 / (1 + S_s))` |
| `practice_weakness` | `2.0 × (1 − M_c) × confidence_c × recency_factor` for weakest concepts |
| `flashcard_review` | `1.5 × cards_due_count` |
| `catch_up_reading` | `1.0 × (days_overdue + 1)` for unlinked reading content past its session |

Recompute triggers:

- Student logs in (lazy — only if cache > 30 min old)
- New attempt recorded (just for affected concepts)
- New deadline enters 24h window (cron)
- New session starts in 24h (cron)

Write top 10 actions per (user, course) to `next_actions` with `expires_at = now() + 1 hour`. Prune expired rows nightly.

### 7.3 Instructor `instructor_alerts` triggers

Alerts fire from periodic jobs, not transactionally. Each alert is idempotent on `(course_id, alert_type, target_user_id, COALESCE(date_bucket, ''))` — if the underlying signal persists, don't duplicate.

| Alert type | Condition |
|---|---|
| `student_disengaging` | No quiz/flashcard/revision activity in 7 days during active term, prior baseline existed |
| `student_falling_behind` | Mastery percentile dropped > 20 points relative to cohort over 14 days |
| `cohort_concept_weakness` | ≥ 40% of enrolled students have `mastery < 0.5, confidence > 0.3` for a concept in current/upcoming session |
| `prereq_gap_for_upcoming_session` | Session in next 48h, ≥ 30% of cohort fails on a prereq concept |
| `low_quiz_participation` | Live session ended, < 60% participation |
| `missed_deadline` | Assignment due_at past, no submission |
| `content_gap` | Concept tagged on session/objective but no quiz/flashcard/chunk covers it |

### 7.4 DAG cycle check for prerequisites

Before inserting a `concept_prerequisites` edge, check that the new edge wouldn't create a cycle:

```sql
WITH RECURSIVE reachable AS (
  SELECT dependent_concept_id AS node
  FROM public.concept_prerequisites
  WHERE prereq_concept_id = :new_dependent
  UNION
  SELECT cp.dependent_concept_id
  FROM public.concept_prerequisites cp
  JOIN reachable r ON cp.prereq_concept_id = r.node
)
SELECT 1 FROM reachable WHERE node = :new_prereq LIMIT 1;
```

If any row, the edge would create a cycle — reject.

### 7.5 Effective concept (resolving canonical)

Always resolve through `canonical_id` when reading. A view simplifies this:

```sql
CREATE VIEW public.concept_effective AS
SELECT
  c.id AS source_id,
  COALESCE(c.canonical_id, c.id) AS effective_id,
  COALESCE(canon.name, c.name) AS effective_name
FROM public.concepts c
LEFT JOIN public.concepts canon ON canon.id = c.canonical_id
WHERE c.deleted_at IS NULL;
```

### 7.6 Reference query — student's weak concepts in a course

```sql
SELECT c.id, c.name, m.mastery_score, m.confidence, m.attempt_count
FROM public.concept_mastery m
JOIN public.concepts c ON c.id = m.concept_id
WHERE m.user_id = :user_id
  AND m.course_id = :course_id
  AND m.mastery_score < 0.5
  AND m.confidence > 0.3
  AND c.deleted_at IS NULL
ORDER BY m.mastery_score ASC, m.confidence DESC
LIMIT 20;
```

### 7.7 Reference query — cohort weakness for an upcoming session

Used by the prep-brief generator and `cohort_concept_weakness` alert.

```sql
SELECT
  c.id AS concept_id,
  c.name,
  AVG(m.mastery_score) AS avg_mastery,
  COUNT(*) FILTER (WHERE m.mastery_score < 0.5 AND m.confidence > 0.3) AS weak_students,
  COUNT(*) AS total_students_with_evidence
FROM public.session_concepts sc
JOIN public.concepts c ON c.id = sc.concept_id
JOIN public.enrollments e ON e.course_id = c.course_id AND e.role = 'student'
LEFT JOIN public.concept_mastery m ON m.user_id = e.user_id AND m.concept_id = c.id
WHERE sc.session_id = :session_id
GROUP BY c.id, c.name
ORDER BY avg_mastery ASC NULLS FIRST;
```

---

## 8. Background jobs

Add to the existing `tasks` table (`task_type` column). All idempotent.

| `task_type` | Trigger | Action |
|---|---|---|
| `parse_syllabus` | User uploads syllabus | LLM call → writes `syllabus_imports.parsed_payload` |
| `apply_syllabus_import` | Instructor clicks Apply | Creates modules/sessions/objectives/assignments transactionally |
| `extract_concepts_for_course` | Course onboarded; manual re-run | §6.1 backfill |
| `tag_artifact_concepts` | New chunk/question/card created | LLM tag → join table insert |
| `recompute_mastery` | Attempt recorded | EMA update for affected concepts |
| `materialize_next_actions` | Login (lazy), event triggers | §7.2 |
| `evaluate_instructor_alerts` | Hourly cron | §7.3 |
| `generate_session_briefing` | 24h before session | LLM call using session concepts + cohort mastery |
| `generate_daily_briefing` | 6am local time | Per-student `student_daily_briefings` row |
| `cleanup_expired_cache` | Nightly | Delete expired `next_actions`, `student_daily_briefings`, `oauth_consumed_nonces` |

The existing `idx_tasks_poll` index already supports a polling worker.

---

## 9. API surface implications

Not part of this README's scope to fully spec, but the schema implies these new endpoints:

- `POST /courses/{id}/syllabus/import` → creates `syllabus_imports`, kicks off `parse_syllabus`
- `POST /courses/{id}/syllabus/imports/{id}/apply` → applies parsed payload
- `GET /courses/{id}/calendar` → sessions + assignments by date
- `GET /courses/{id}/sessions/{id}/briefing` → instructor prep brief
- `GET /courses/{id}/concepts` + `GET /courses/{id}/concepts/graph` → concept editor
- `GET /students/{id}/today` → cross-course `next_actions` + briefing
- `GET /courses/{id}/cohort/concept_health` → matrix view for instructor
- `GET /instructors/{id}/alerts?status=open` → alert center
- `POST /instructors/{id}/alerts/{id}/dismiss` / `resolve`

The student dashboard reads `next_actions` directly. The instructor dashboard reads `instructor_alerts` directly. Neither computes ranking in the request path.

---

## 10. What we explicitly chose NOT to build

These came up; saying no on purpose.

**No per-concept bandit.** Concept-grain bandits would never escape cold start. Bandit stays at the (user, course, content_type) grain it already has. Concept selection composes on top by filtering the pool.

**No DB triggers for mastery EMA.** Trigger logic is hard to debug when the formula evolves. Keep it in the application service.

**No giant `briefing` blob table for memory.** `student_daily_briefings` is a TTL cache, not a memory store. The four foundation layers are the source of truth; LLM renders briefings on demand and caches the output for the day.

**No merging of `bandit_models` + `scheduler_models`.** They're already shipped and working. A unification refactor (`policy_models`) is reasonable later but adds risk without product value right now.

**No collaboration / group entities.** "Group 3 free-rider risk" from the vision needs a `groups` + `group_memberships` + `group_contributions` cluster. Out of scope for this upgrade — defer to a later phase once the foundation is real.

**No cross-course concept linking.** A "fixed cost" concept in Managerial Accounting and another in Finance are kept separate by `course_id`. Cross-course concept ontology is interesting but the curation cost outweighs the benefit at current scale.

**No vector index on tagging tables.** Concepts have embeddings (for dedup); chunk → concept matching uses LLM tagging at write time, not vector search at read time. Cheaper at query time, easier to reason about.

---

## 11. Open questions / future phases

- **Concept hierarchy.** Currently concepts are flat per course. A `concept_parent_id` (separate from prerequisite — taxonomy, not dependency) might help instructor UX. Defer until concept count per course exceeds ~100.
- **Group / collaboration entities** (see §10).
- **Multi-modal evidence weighting.** Right now an EMA update from a flashcard "good" press counts the same as a hard quiz answer. Adding per-source weight is straightforward but needs product input.
- **Policy unification** (`bandit_models` + `scheduler_models` → `policy_models`).
- **Cross-course concept ontology** (see §10) — only worth it once you have many courses with explicit overlap.
- **Forgetting model.** `concept_mastery` doesn't decay over time today. Add a nightly forgetting pass (`mastery_score *= exp(−days_since_last_attempt / τ)`) once you have data on real retention curves.

---

## 12. Implementation checklist

- [ ] Phase 1 Alembic revision: curriculum + calendar tables, ALTER existing tables
- [ ] Phase 1 API: course calendar CRUD, session prep brief shell (LLM call stubbed)
- [ ] Phase 2 Alembic revision: concepts + 8 tagging tables
- [ ] Phase 2 jobs: `extract_concepts_for_course`, `tag_artifact_concepts`
- [ ] Phase 2 backfill: run §6 on every existing course
- [ ] Phase 2 instructor UI: concept editor with prereq graph
- [ ] Phase 3 Alembic revision: `concept_mastery` + indexes
- [ ] Phase 3 service: EMA update wired into all attempt handlers
- [ ] Phase 3 backfill: replay 90-day attempt history
- [ ] Phase 4 Alembic revision: `next_actions`, `instructor_alerts`
- [ ] Phase 4 jobs: scoring, alert evaluation
- [ ] Phase 4 dashboards: student "today", instructor alert center
- [ ] Phase 5 Alembic revision: `syllabus_imports`, `student_daily_briefings`
- [ ] Phase 5 parser + applier
- [ ] Phase 5 daily briefing generator

Each phase ships independently. After Phase 1 the product already feels different. After Phase 4 it is the system the vision describes.
