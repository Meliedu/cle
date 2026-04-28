# Adaptive Learning Engine

> Curriculum-centered adaptive layer on top of the existing content + evidence engine. Adds concept-level mastery, prerequisite-aware decisions, and instructor visibility — without disturbing the bandit / FSRS / recalibration machinery underneath.

## Context

Meli today is a feature-rich AI study tool: documents → chunks → embeddings → quiz/flashcard/summary/pronunciation generation, plus a contextual bandit for difficulty selection and FSRS-5 for flashcard scheduling. The selection/policy layer works well.

What's missing is a **meaning layer** that lets the system reason about *concepts*, not just attempts. Today the system can say "this student got 60% of medium questions right." It cannot say "this student is weak at *inference*" or "this student should review *fixed cost behaviour* before the next session because it's a prerequisite."

This spec adds that meaning layer in three phases. Phase 1 ships a curriculum spine + calendar that's a real product win on its own, even before any concept work. Phases 2 and 3 layer concept-aware mastery and decisions on top.

This spec was validated against the 2025–2026 educational data mining literature (see [validation summary](#references)) and revised on five non-trivial points: mastery model (Beta-Binomial over EMA), forgetting decay (day-1, not deferred), recommendation grounding (KST "outer fringe" predicate), outcome telemetry (A/B-toggleable from day 1), and prior-art audit (ALOSI/Open edX as reference).

### Prior art

| System | Approach | Lesson taken |
|---|---|---|
| ALEKS (McGraw Hill) | Knowledge Space Theory: knowledge state = solvable items; "outer fringe" = ready-to-learn | Use outer-fringe predicate as the candidate filter for `next_actions`, not just hand-tuned coefficients |
| ALOSI / Open edX | Real-time mastery update on every problem-checking event; manual instructor tagging of items to objectives | Confirms our architecture; their schema is XBlock-coupled so we use as reference only |
| Duolingo HLR | `p = 2^(−Δ/h)`; per-item half-life updated each attempt | Apply to `concept_mastery` decay from Phase 3, not "later" |
| DAS3H (Choffin et al., EDM 2019) | Multi-skill items + forgetting in one factorisation-machine model | Inform per-concept decay τ tuning; consider as future replacement for Beta-Binomial when we have data |
| PDT (Probabilistic DT) | Beta posterior per skill; analytic uncertainty quantification | Adopt for `concept_mastery`; gives mean + variance + cold-start handling |
| Lan & Baraniuk 2016 | Contextual bandits filtered by content features | Confirms our bandit-stays-below-concept-filter pattern |

References at end of doc.

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Engine layering | Concept layer composes *above* existing bandit/FSRS, never replaces | Bandit and FSRS work; concept filtering produces the candidate set, bandit picks difficulty within it |
| Mastery model | **Beta-Binomial posterior per (user, concept)**, not EMA | EMA is not a published mastery method; Beta gives mean + variance + cold-start for the same complexity |
| Forgetting | **HLR-style decay applied nightly from Phase 2.2** (when mastery first ships) | Duolingo +9.5% retention, ~50% error reduction in production; without it every cohort signal under-fires by week 4 |
| `next_actions` candidate filter | **KST "outer fringe" predicate** (prereqs satisfied + this concept not yet mastered) is first-class; coefficients only break ties | Theoretically grounded, instructor-explainable ("you're ready for X because Y is mastered") |
| Concept extraction | LLM proposes → cluster + canonicalise → instructor curates per cluster (~30 min/course) | 2025 consensus is collaborative human-AI; pure LLM extraction produces unstable join keys |
| Outcome telemetry | Every served `next_action` logs served/clicked/outcome; per-cohort engine on/off toggle | Built-in A/B that proves moat narrative; toggleable per course or globally |
| Tagging tables | **One polymorphic `concept_tags(target_kind, target_id, concept_id, weight)`** | One migration + one write path instead of 8; partial indexes per kind keep it fast |
| Calendar entity name | `course_meetings`, NOT `class_sessions` | Avoids collision with existing `LiveSession` model |
| Phase 1 ship | Curriculum spine + calendar standalone (no concepts yet) | Real product win on day one; validates calendar UX before harder layer |
| Syllabus parser | Deferred entirely | Underspecified; calendar UI is the actual product |
| `assignment_submissions` | Deferred | Canvas already has them; revisit when grading sync becomes a need |
| Cross-course concept ontology | Deferred | Curation cost > benefit at current scale |
| Per-concept bandit | Not built | Concept-grain bandits never escape cold start |
| Mastery via DB triggers | Not used | Application service is debuggable; trigger logic isn't |

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                       DECISION LAYER (Phase 3)                     │
│   next_actions   ·   instructor_alerts   ·   action_outcomes       │
│   Engine on/off toggle per course (A/B for efficacy proof)         │
└──┬───────────────┬────────────────┬───────────────┬───────────────┘
   │               │                │               │
   ▼               ▼                ▼               ▼
┌──────────┐ ┌──────────┐    ┌──────────┐    ┌──────────────┐
│CURRICULUM│ │ CONTENT  │    │ EVIDENCE │    │   MASTERY    │
│ (Phase 1)│ │(existing)│    │(existing)│    │  (Phase 2)   │
│          │ │          │    │          │    │              │
│ courses  │ │documents │    │ quiz_    │    │  concept_    │
│ modules  │ │ chunks   │    │  attempts│    │   mastery    │
│ meetings │ │ quizzes  │    │ flashcard│    │ (Beta-Binom) │
│objectives│ │flashcards│    │  progress│    │  + nightly   │
│assignments│ │ pronunc. │    │ revision_│    │  HLR decay   │
│          │ │pool_items│    │ attempts │    │              │
└──────────┘ └────┬─────┘    │ pronunc_ │    │ ─────────── │
                  │          │  scores  │    │  bandit_    │
                  ▼          └────┬─────┘    │   models    │
           ┌──────────────┐       │          │  scheduler_ │
           │   CONCEPTS   │       │          │   models    │
           │  (Phase 2)   │       │          │ (existing,  │
           │              │       │          │  unchanged) │
           │  concepts    │       │          │             │
           │  prereqs DAG │       │          └──────┬──────┘
           │              │◄──────┴─────────────────┘
           │ concept_tags │   (single polymorphic table — joins
           │ (polymorphic)│    chunks, questions, flashcards,
           └──────────────┘    pronunciation, pool, objectives,
                               meetings, assignments)
```

The four foundation layers (curriculum / content / evidence / mastery) are sources of truth. The decision layer is **materialised cache** — recompute, don't migrate.

---

## Phase 1 — Curriculum spine + calendar

Ships standalone. Even with zero concept work, instructors get a real course operating plan and students get a calendar.

### `course_modules` — weeks / chapters / units (tree)

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
```

### `course_meetings` — calendar anchor (named to avoid collision with `LiveSession`)

```sql
CREATE TABLE public.course_meetings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    course_id uuid NOT NULL,
    module_id uuid NULL,
    meeting_index int4 NOT NULL,           -- 1-based within course
    title varchar(255) NULL,
    scheduled_at timestamptz NOT NULL,
    duration_minutes int4 DEFAULT 60 NOT NULL,
    location varchar(255) NULL,
    status varchar(20) DEFAULT 'planned' NOT NULL,
    pre_meeting_briefing jsonb NULL,       -- LLM-generated, instructor-editable; populated in Phase 3
    post_meeting_summary jsonb NULL,       -- generated after meeting ends
    canvas_event_id varchar(100) NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    deleted_at timestamptz NULL,
    CONSTRAINT course_meetings_pkey PRIMARY KEY (id),
    CONSTRAINT ck_course_meetings_status_valid
        CHECK (status IN ('planned','in_progress','taught','cancelled')),
    CONSTRAINT uq_course_meetings_course_index
        UNIQUE (course_id, meeting_index),
    CONSTRAINT course_meetings_course_id_fkey
        FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE,
    CONSTRAINT course_meetings_module_id_fkey
        FOREIGN KEY (module_id) REFERENCES public.course_modules(id) ON DELETE SET NULL
);
CREATE INDEX idx_course_meetings_course_scheduled
    ON public.course_meetings (course_id, scheduled_at)
    WHERE deleted_at IS NULL;
CREATE INDEX idx_course_meetings_upcoming
    ON public.course_meetings (scheduled_at)
    WHERE deleted_at IS NULL AND status = 'planned';
```

### `learning_objectives` — what the student should be able to do

Three nullable scope FKs (`course_id` always present + optionally `module_id` or `meeting_id`) instead of polymorphic `scope_type` — gives PG-enforced referential integrity.

```sql
CREATE TABLE public.learning_objectives (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    course_id uuid NOT NULL,
    module_id uuid NULL,
    meeting_id uuid NULL,
    statement varchar NOT NULL,
    bloom_level varchar(20) NULL,
    order_index int4 DEFAULT 0 NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    deleted_at timestamptz NULL,
    CONSTRAINT learning_objectives_pkey PRIMARY KEY (id),
    CONSTRAINT ck_learning_objectives_scope_exclusive
        CHECK (NOT (module_id IS NOT NULL AND meeting_id IS NOT NULL)),
    CONSTRAINT ck_learning_objectives_bloom_valid
        CHECK (bloom_level IS NULL OR bloom_level IN
            ('remember','understand','apply','analyze','evaluate','create')),
    CONSTRAINT learning_objectives_course_id_fkey
        FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE,
    CONSTRAINT learning_objectives_module_id_fkey
        FOREIGN KEY (module_id) REFERENCES public.course_modules(id) ON DELETE CASCADE,
    CONSTRAINT learning_objectives_meeting_id_fkey
        FOREIGN KEY (meeting_id) REFERENCES public.course_meetings(id) ON DELETE CASCADE
);
CREATE INDEX idx_learning_objectives_course
    ON public.learning_objectives (course_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_learning_objectives_module
    ON public.learning_objectives (module_id) WHERE module_id IS NOT NULL AND deleted_at IS NULL;
CREATE INDEX idx_learning_objectives_meeting
    ON public.learning_objectives (meeting_id) WHERE meeting_id IS NOT NULL AND deleted_at IS NULL;
```

### `assignments` — graded deliverables with deadlines

```sql
CREATE TABLE public.assignments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    course_id uuid NOT NULL,
    module_id uuid NULL,
    meeting_id uuid NULL,
    title varchar(255) NOT NULL,
    description varchar NULL,
    kind varchar(30) NOT NULL,
    due_at timestamptz NOT NULL,
    available_from timestamptz NULL,
    weight numeric(5,2) NULL,
    quiz_id uuid NULL,
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
    CONSTRAINT assignments_meeting_id_fkey
        FOREIGN KEY (meeting_id) REFERENCES public.course_meetings(id) ON DELETE SET NULL,
    CONSTRAINT assignments_quiz_id_fkey
        FOREIGN KEY (quiz_id) REFERENCES public.quizzes(id) ON DELETE SET NULL,
    CONSTRAINT assignments_created_by_fkey
        FOREIGN KEY (created_by) REFERENCES public.users(id)
);
CREATE INDEX idx_assignments_course_due
    ON public.assignments (course_id, due_at) WHERE deleted_at IS NULL;
CREATE INDEX idx_assignments_upcoming
    ON public.assignments (due_at) WHERE deleted_at IS NULL AND is_published = true;
```

`assignment_submissions` is **deferred** — Canvas owns submission state for now. Revisit when we need grading sync.

### Modifications to existing tables (Phase 1)

```sql
ALTER TABLE public.documents
    ADD COLUMN meeting_id uuid NULL REFERENCES public.course_meetings(id) ON DELETE SET NULL,
    ADD COLUMN module_id uuid NULL REFERENCES public.course_modules(id) ON DELETE SET NULL;
CREATE INDEX idx_documents_meeting ON public.documents (meeting_id) WHERE meeting_id IS NOT NULL;

ALTER TABLE public.quizzes
    ADD COLUMN meeting_id uuid NULL REFERENCES public.course_meetings(id) ON DELETE SET NULL,
    ADD COLUMN module_id uuid NULL REFERENCES public.course_modules(id) ON DELETE SET NULL;
CREATE INDEX idx_quizzes_meeting ON public.quizzes (meeting_id) WHERE meeting_id IS NOT NULL;

ALTER TABLE public.flashcard_sets
    ADD COLUMN meeting_id uuid NULL REFERENCES public.course_meetings(id) ON DELETE SET NULL,
    ADD COLUMN module_id uuid NULL REFERENCES public.course_modules(id) ON DELETE SET NULL;

ALTER TABLE public.pronunciation_sets
    ADD COLUMN meeting_id uuid NULL REFERENCES public.course_meetings(id) ON DELETE SET NULL,
    ADD COLUMN module_id uuid NULL REFERENCES public.course_modules(id) ON DELETE SET NULL;
```

All additive, all NULL-safe. No backfill required.

### Phase 1 ship criteria

- Instructor can create modules, meetings, objectives, assignments
- Existing content can be linked to a meeting (UI affordance)
- Student calendar view: meetings + assignment deadlines, by week
- Canvas event sync (best-effort, optional) populates `canvas_event_id`

**No concept-aware behaviour anywhere yet.** Phase 1 ships, gets used, and we measure whether the calendar UX works before continuing.

---

## Phase 2 — Concepts + mastery

### `concepts`

```sql
CREATE TABLE public.concepts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    course_id uuid NOT NULL,
    name varchar(255) NOT NULL,
    description varchar NULL,
    canonical_id uuid NULL,
    embedding public.vector(3072) NULL,    -- matches text-embedding-3-large native dim
    extracted_from_chunk_id uuid NULL,
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
    ON public.concepts (course_id) WHERE deleted_at IS NULL;
```

Embedding dim is **3072**, matching the production embedder (`openai/text-embedding-3-large`). If we later switch to a smaller model, migrate then.

`canonical_id` enables soft-merge: duplicates point at the canonical record. Resolve through `canonical_id` on read (helper view in §Decision queries).

### `concept_prerequisites` — DAG edges

```sql
CREATE TABLE public.concept_prerequisites (
    prereq_concept_id uuid NOT NULL,
    dependent_concept_id uuid NOT NULL,
    strength numeric(3,2) DEFAULT 1.00 NOT NULL,
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
```

**Cycle prevention** is application-side via `WITH RECURSIVE` cycle check on insert (see §Decision queries).

### `concept_tags` — single polymorphic tagging table

Replaces the 8-table approach. One write path, one migration, partial indexes per `target_kind` keep it fast.

```sql
CREATE TABLE public.concept_tags (
    concept_id uuid NOT NULL,
    target_kind varchar(30) NOT NULL,
    target_id uuid NOT NULL,
    weight numeric(3,2) DEFAULT 1.00 NOT NULL,
    role varchar(20) NULL,                 -- 'introduced'|'covered'|'reinforced' for meetings; null otherwise
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT concept_tags_pkey PRIMARY KEY (concept_id, target_kind, target_id),
    CONSTRAINT ck_concept_tags_target_kind_valid
        CHECK (target_kind IN (
            'chunk','question','flashcard_card','pronunciation_item',
            'pool_item','objective','meeting','assignment'
        )),
    CONSTRAINT ck_concept_tags_weight_range CHECK (weight >= 0 AND weight <= 1),
    CONSTRAINT ck_concept_tags_role_for_meeting
        CHECK (role IS NULL OR (target_kind = 'meeting' AND
                                role IN ('introduced','covered','reinforced'))),
    CONSTRAINT concept_tags_concept_id_fkey
        FOREIGN KEY (concept_id) REFERENCES public.concepts(id) ON DELETE CASCADE
);
-- Concept-driven queries (most common): "what tags this concept?"
CREATE INDEX idx_concept_tags_concept
    ON public.concept_tags (concept_id, target_kind);
-- Per-kind reverse lookup, partial for selectivity
CREATE INDEX idx_concept_tags_questions
    ON public.concept_tags (target_id) WHERE target_kind = 'question';
CREATE INDEX idx_concept_tags_chunks
    ON public.concept_tags (target_id) WHERE target_kind = 'chunk';
CREATE INDEX idx_concept_tags_pool_items
    ON public.concept_tags (target_id) WHERE target_kind = 'pool_item';
CREATE INDEX idx_concept_tags_meetings
    ON public.concept_tags (target_id) WHERE target_kind = 'meeting';
-- Add additional partial indexes per kind as query patterns demand
```

`target_id` is intentionally not a typed FK because it points at different tables. Application enforces that the row exists; periodic integrity check job catches drift.

### `concept_mastery` — Beta-Binomial posterior per (user, concept)

We replace EMA with a Beta-Binomial: each (user, concept) maintains pseudo-counts `α` (successes + prior) and `β` (failures + prior). Mastery is `α / (α + β)`; uncertainty is the Beta variance.

```sql
CREATE TABLE public.concept_mastery (
    user_id uuid NOT NULL,
    concept_id uuid NOT NULL,
    course_id uuid NOT NULL,
    alpha numeric(8,3) DEFAULT 1.000 NOT NULL,    -- prior 1.0; updates on each attempt
    beta numeric(8,3) DEFAULT 1.000 NOT NULL,     -- prior 1.0; uniform Beta(1,1)
    mastery_score numeric(4,3) GENERATED ALWAYS AS (alpha / (alpha + beta)) STORED,
    confidence numeric(4,3) NOT NULL DEFAULT 0.000,  -- recomputed on update; see §Mastery math
    attempt_count int4 DEFAULT 0 NOT NULL,
    last_attempt_at timestamptz NULL,
    last_correct_at timestamptz NULL,
    last_decay_at timestamptz DEFAULT now() NOT NULL, -- when nightly decay last touched this row
    last_seen_meeting_id uuid NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT concept_mastery_pkey PRIMARY KEY (user_id, concept_id),
    CONSTRAINT ck_concept_mastery_alpha_pos CHECK (alpha > 0),
    CONSTRAINT ck_concept_mastery_beta_pos CHECK (beta > 0),
    CONSTRAINT ck_concept_mastery_confidence_range CHECK (confidence >= 0 AND confidence <= 1),
    CONSTRAINT concept_mastery_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE,
    CONSTRAINT concept_mastery_concept_id_fkey
        FOREIGN KEY (concept_id) REFERENCES public.concepts(id) ON DELETE CASCADE,
    CONSTRAINT concept_mastery_course_id_fkey
        FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE,
    CONSTRAINT concept_mastery_last_seen_meeting_id_fkey
        FOREIGN KEY (last_seen_meeting_id) REFERENCES public.course_meetings(id) ON DELETE SET NULL
);
CREATE INDEX idx_concept_mastery_user_course
    ON public.concept_mastery (user_id, course_id);
CREATE INDEX idx_concept_mastery_weak
    ON public.concept_mastery (course_id, concept_id, mastery_score)
    WHERE mastery_score < 0.5 AND confidence > 0.3;
CREATE INDEX idx_concept_mastery_decay_due
    ON public.concept_mastery (last_decay_at);
```

### Mastery math

**Update rule (per attempt that ties to one or more concepts):**

For each tagged concept with weight `w`:
- `outcome ∈ [0, 1]` derived from the artifact:
  - quiz: `1.0` if correct, `0.0` if not
  - flashcard: again=0.0, hard=0.4, good=0.8, easy=1.0
  - pronunciation: `overall_score / 100`
  - revision: attempt `score` (already in [0, 1])
- `α ← α + w · outcome`
- `β ← β + w · (1 − outcome)`
- `attempt_count ← attempt_count + 1`
- `confidence` recomputed (see below)

**Confidence formula:**

```
confidence = 1 − sqrt(Var[Beta(α, β)])
           = 1 − sqrt(α·β / ((α+β)² · (α+β+1)))
```

Variance shrinks as α + β grow; confidence saturates near 1 with enough evidence. With Beta(1,1) prior, after 1 attempt confidence is ~0.4 — much more conservative than the EMA-based version.

**Alert thresholds:** raise from spec's `confidence > 0.3` to `confidence ≥ 0.5 AND attempt_count ≥ 5` to prevent two-attempt false positives.

### Forgetting decay (HLR-style, day-1)

Nightly cron walks rows in `concept_mastery` where `last_decay_at < now() - interval '1 day'` and applies:

```
days_since = (now() - last_attempt_at).days
half_life  = τ   -- per-concept default; learnable per (user, concept) later
decay      = 2^(−days_since / half_life)

# Apply decay by shrinking pseudo-counts toward prior
α' = max(1.0, prior + (α − prior) · decay)
β' = max(1.0, prior + (β − prior) · decay)
```

`τ` defaults to 14 days per concept; tuned per cohort over time. This produces the right behaviour: a student who hasn't touched a concept in 30 days drifts back toward `α=β=1` (unknown), exactly what an instructor would expect.

The decay job also recomputes `confidence` and bumps `last_decay_at`. Idempotent — running it multiple times in one day is a no-op.

### Concept extraction + curation (collaborative human-AI)

Pure LLM extraction produces unstable join keys. We use a 3-step process per course:

1. **Extract candidates.** Sample ~200 chunks across all course documents. Send batches to LLM with structured-output prompt: "extract 5–15 concepts that this passage teaches. Output JSON array of `{name, description, evidence_chunk_id}`."
2. **Cluster + canonicalise.** Embed all candidates; cluster by cosine distance < 0.15 + LLM dedup pass on cluster names. Each cluster yields one *canonical candidate concept* with example chunks.
3. **Instructor curates per cluster.** UI shows ~30–60 clusters with example chunks and proposed name. Instructor: approve / rename / merge / split / reject. Instructor can also draw prerequisite edges between approved concepts. Approved concepts get `instructor_curated = true`.

After curation, a separate job tags artifacts (`chunk_concepts`, `question_concepts`, etc. via `concept_tags`):
- For artifacts with `source_chunk_id`, inherit chunk's concept tags at weight × 0.7 (questions/cards typically assess a subset of what the chunk teaches).
- For artifacts without `source_chunk_id`, run LLM tagger directly.

Cost cap: enforce per-course token budget for extraction. Re-tagging only triggers when concepts change.

---

## Phase 3 — Decision layer + outcome telemetry

### `next_actions` — materialised cache, not source of truth

```sql
CREATE TABLE public.next_actions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    course_id uuid NULL,
    action_type varchar(40) NOT NULL,
    target_kind varchar(40) NULL,
    target_id uuid NULL,
    priority_score numeric(7,3) NOT NULL,
    candidate_source varchar(20) NOT NULL, -- 'outer_fringe' | 'deadline' | 'review' | 'fallback'
    reason jsonb NOT NULL,
    expires_at timestamptz NOT NULL,
    served_at timestamptz NULL,
    clicked_at timestamptz NULL,
    consumed_at timestamptz NULL,
    engine_variant varchar(20) NOT NULL DEFAULT 'on',  -- 'on' | 'off' | experiment label
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT next_actions_pkey PRIMARY KEY (id),
    CONSTRAINT ck_next_actions_action_type_valid
        CHECK (action_type IN (
            'review_concept','prep_meeting','complete_assignment',
            'do_quiz','practice_weakness','catch_up_reading',
            'flashcard_review','pronunciation_practice','watch_recording'
        )),
    CONSTRAINT ck_next_actions_target_kind_valid
        CHECK (target_kind IS NULL OR target_kind IN (
            'concept','course_meeting','assignment','quiz',
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
    ON public.next_actions (expires_at) WHERE consumed_at IS NULL;
```

`engine_variant` records what produced this row — enables retroactive A/B analysis. `served_at` and `clicked_at` are the telemetry hooks.

### KST "outer fringe" — the candidate filter

Before scoring, the decision engine filters concepts that are **ready to learn**:

```sql
-- Outer fringe: concepts whose every prerequisite is mastered
-- (mastery >= 0.7 AND confidence >= 0.5) but the concept itself is not.
WITH user_state AS (
    SELECT concept_id, mastery_score, confidence
    FROM public.concept_mastery
    WHERE user_id = :user_id AND course_id = :course_id
)
SELECT c.id AS concept_id, c.name
FROM public.concepts c
LEFT JOIN user_state s ON s.concept_id = c.id
WHERE c.course_id = :course_id
  AND c.deleted_at IS NULL
  AND c.canonical_id IS NULL
  -- Self not yet mastered
  AND COALESCE(s.mastery_score, 0) < 0.7
  -- All prereqs mastered (or no prereqs)
  AND NOT EXISTS (
      SELECT 1 FROM public.concept_prerequisites p
      LEFT JOIN user_state ps ON ps.concept_id = p.prereq_concept_id
      WHERE p.dependent_concept_id = c.id
        AND p.strength >= 0.5
        AND (
            COALESCE(ps.mastery_score, 0) < 0.7
            OR COALESCE(ps.confidence, 0) < 0.5
        )
  );
```

The `next_actions` engine selects from this set first. Only after the outer fringe is exhausted does it fall back to "weakest concept regardless of prereqs" or pure deadline pressure.

### Scoring (tie-breaker only — outer fringe is the primary filter)

For each candidate (concept, action_type) pair:

| Action | Score formula |
|---|---|
| `prep_meeting` | `3.0 × P_m × (1 / (1 + S_m))` where `P_m = Σ weight × (1 − mastery_c)` over upcoming meeting's concepts, `S_m` = days until meeting |
| `complete_assignment` | `5.0 × assignment.weight × (1 / (1 + D_a))` where `D_a` = days until due |
| `practice_weakness` | `2.0 × (1 − mastery_c) × confidence_c × recency_factor` |
| `flashcard_review` | `1.5 × cards_due_count` |
| `catch_up_reading` | `1.0 × (days_overdue + 1)` for unlinked reading past its meeting |

Coefficients are *initial values, calibrated by outcome telemetry*. Phase 3 ships with these as defaults and a job that re-tunes them quarterly using the `served → clicked → outcome` log.

**Recompute triggers** (write top 10 per (user, course) with `expires_at = now() + 1 hour`):
- Student logs in (lazy — only if cache > 30 min old)
- New attempt recorded (just affected concepts)
- New deadline enters 24h window (cron)
- New meeting starts in 24h (cron)

### `instructor_alerts`

```sql
CREATE TABLE public.instructor_alerts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    course_id uuid NOT NULL,
    instructor_id uuid NOT NULL,
    target_user_id uuid NULL,
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
            'cohort_concept_weakness','prereq_gap_for_upcoming_meeting',
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
```

Hourly cron evaluates conditions; idempotent on `(course_id, alert_type, target_user_id)`.

### `action_outcomes` — efficacy telemetry

Every time a student does (or doesn't do) something the engine recommended, we record it. This is the data that proves moat.

```sql
CREATE TABLE public.action_outcomes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    next_action_id uuid NULL,              -- nullable: outcome can be observational
    user_id uuid NOT NULL,
    course_id uuid NULL,
    action_type varchar(40) NOT NULL,
    target_kind varchar(40) NULL,
    target_id uuid NULL,
    engine_variant varchar(20) NOT NULL,   -- 'on'|'off'|<experiment label>
    served_at timestamptz NOT NULL,
    clicked bool DEFAULT false NOT NULL,
    completed bool DEFAULT false NOT NULL,
    outcome_score numeric(4,3) NULL,       -- 0..1; e.g. quiz score, mastery delta, recall lift
    outcome_metric varchar(40) NULL,       -- 'mastery_delta'|'quiz_score'|'recall'|'completion'
    observed_at timestamptz NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT action_outcomes_pkey PRIMARY KEY (id),
    CONSTRAINT action_outcomes_next_action_id_fkey
        FOREIGN KEY (next_action_id) REFERENCES public.next_actions(id) ON DELETE SET NULL,
    CONSTRAINT action_outcomes_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE,
    CONSTRAINT action_outcomes_course_id_fkey
        FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE
);
CREATE INDEX idx_action_outcomes_variant_served
    ON public.action_outcomes (engine_variant, served_at);
CREATE INDEX idx_action_outcomes_user
    ON public.action_outcomes (user_id, served_at DESC);
```

### Engine on/off toggle

A simple per-course flag plus per-user override (for explicit A/B):

```sql
ALTER TABLE public.courses
    ADD COLUMN adaptive_engine_mode varchar(20) DEFAULT 'on' NOT NULL;
ALTER TABLE public.courses
    ADD CONSTRAINT ck_courses_engine_mode_valid
        CHECK (adaptive_engine_mode IN ('on','off','random_50'));

-- Per-user override for instructor-driven experiments (NULL = inherit from course)
CREATE TABLE public.engine_overrides (
    user_id uuid NOT NULL,
    course_id uuid NOT NULL,
    mode varchar(20) NOT NULL,
    set_by uuid NOT NULL,
    set_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT engine_overrides_pkey PRIMARY KEY (user_id, course_id),
    CONSTRAINT ck_engine_overrides_mode_valid CHECK (mode IN ('on','off')),
    CONSTRAINT engine_overrides_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE,
    CONSTRAINT engine_overrides_course_id_fkey
        FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE,
    CONSTRAINT engine_overrides_set_by_fkey
        FOREIGN KEY (set_by) REFERENCES public.users(id)
);
```

Mode resolution: `engine_overrides` > `courses.adaptive_engine_mode`. `random_50` mode hashes `(user_id, course_id)` to deterministically assign each student to `on` or `off` — gives a stable A/B split.

When mode is `off`, the system shows no `next_actions` to the student (or shows a fallback "what's due" list with `engine_variant = 'off'` recorded). Either way, `action_outcomes` rows are still written so we can compare cohorts.

---

## Bandit & FSRS — explicitly unchanged

`bandit_models`, `scheduler_models`, `recalibration_models`, `recalibration_stats` are **not modified**. They model selection policy at the (user, course, content_type, item) grain. The new concept layer filters the candidate pool *before* the bandit picks difficulty — composes cleanly. Resist the temptation to merge.

`revision_attempts` gets one denormalised column for query speed:

```sql
ALTER TABLE public.revision_attempts
    ADD COLUMN primary_concept_id uuid NULL REFERENCES public.concepts(id) ON DELETE SET NULL;
CREATE INDEX idx_revision_attempts_concept
    ON public.revision_attempts (user_id, primary_concept_id, created_at DESC)
    WHERE primary_concept_id IS NOT NULL;
```

---

## Migration plan

| Phase | Alembic revisions | Ships independently | New tables |
|---|---|---|---|
| **1: Curriculum + calendar** | 1 revision | ✅ — instructor calendar UI is the product win | `course_modules`, `course_meetings`, `learning_objectives`, `assignments` + ALTERs to `documents`/`quizzes`/`flashcard_sets`/`pronunciation_sets` |
| **2: Concepts + mastery** | 2 revisions (concepts → mastery) | Pause point: validate concept curation UX before Phase 3 | `concepts`, `concept_prerequisites`, `concept_tags`, `concept_mastery` + ALTER `revision_attempts`, ALTER `courses` |
| **3: Decision + telemetry** | 1 revision | ✅ — produces real `next_actions` and outcome data | `next_actions`, `instructor_alerts`, `action_outcomes`, `engine_overrides` |

Defer to future:
- Syllabus parser (Phase 5 in original spec)
- Daily briefing cache (`student_daily_briefings`)
- `assignment_submissions`
- Cross-course concept linking
- Per-user-per-concept learnable τ (decay half-life)

## Backfill (Phase 2 only)

After Phase 2 ships:
1. Run concept extraction + curation per course (instructor task, ~30 min). Course is "concept-ready" when instructor approves the curated set.
2. Cascade-tag artifacts via `source_chunk_id` inheritance + LLM tagger for orphans. Use `tasks` queue.
3. Replay last 90 days of `quiz_attempts`, `flashcard_progress`, `revision_attempts`, `pronunciation_scores` through Beta-Binomial update. Older history ignored. Confidence stays low until the student re-engages.

Pre-Phase-2 courses keep working — they just don't have concept-aware features. Concept-ready courses opt into Phase 3 when ready.

---

## Background jobs

| `task_type` | Trigger | Action |
|---|---|---|
| `extract_concept_candidates` | Course onboarding; manual re-run | LLM extraction → cluster → propose to instructor |
| `tag_artifact_concepts` | New chunk/question/card created | Inherit from source_chunk or LLM tag → `concept_tags` insert |
| `update_concept_mastery` | Attempt recorded | Beta-Binomial update for affected (user, concept) |
| `decay_concept_mastery` | Nightly cron | HLR decay across stale rows |
| `materialize_next_actions` | Login (lazy); event triggers | Outer-fringe filter → score → top 10 |
| `evaluate_instructor_alerts` | Hourly cron | Alert conditions over cohort |
| `tune_action_coefficients` | Quarterly cron | Re-tune scoring coefficients from `action_outcomes` log |
| `generate_meeting_briefing` | 24h before meeting | LLM call: meeting concepts + cohort mastery → `pre_meeting_briefing` |

Existing `tasks` table polling worker (`worker.py:196`, uses `FOR UPDATE SKIP LOCKED`) handles all of these.

---

## Decision queries (reference)

### Outer-fringe candidate set
See SQL above under [KST "outer fringe"](#kst-outer-fringe--the-candidate-filter).

### Cycle prevention before inserting prerequisite edge
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

### Effective concept (resolve through `canonical_id`)
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

### Cohort weakness for upcoming meeting
```sql
SELECT
  c.id AS concept_id,
  c.name,
  AVG(m.mastery_score) AS avg_mastery,
  COUNT(*) FILTER (WHERE m.mastery_score < 0.5 AND m.confidence >= 0.5) AS weak_students,
  COUNT(*) AS total_students_with_evidence
FROM public.concept_tags ct
JOIN public.concepts c ON c.id = ct.concept_id
JOIN public.enrollments e ON e.course_id = c.course_id AND e.role = 'student'
LEFT JOIN public.concept_mastery m ON m.user_id = e.user_id AND m.concept_id = c.id
WHERE ct.target_kind = 'meeting' AND ct.target_id = :meeting_id
GROUP BY c.id, c.name
ORDER BY avg_mastery ASC NULLS FIRST;
```

### Efficacy comparison (engine on vs off)
```sql
-- Mean outcome by engine_variant for a course over the last 30 days
SELECT engine_variant,
       COUNT(*) AS served,
       AVG(CASE WHEN clicked THEN 1.0 ELSE 0.0 END) AS click_rate,
       AVG(outcome_score) FILTER (WHERE outcome_score IS NOT NULL) AS mean_outcome
FROM public.action_outcomes
WHERE course_id = :course_id
  AND served_at >= now() - interval '30 days'
GROUP BY engine_variant;
```

---

## What we explicitly chose NOT to build

- **Per-concept bandits** — never escape cold start. Bandit stays at (user, course, content_type).
- **DB-trigger mastery updates** — debug nightmare. Application service.
- **8 separate tagging tables** — replaced by polymorphic `concept_tags`.
- **Bandit + scheduler unification** — both work; refactor adds risk without product value.
- **Cross-course concepts** — curation cost > benefit at current scale.
- **Group / collaboration entities** — out of scope; needs `groups`/`group_memberships` cluster.
- **Vector index on tagging tables** — concept embeddings exist for dedup; tagging uses LLM at write time, not vector search at read time.
- **Per-objective polymorphic scope_type** — replaced with three explicit nullable FKs + CHECK constraint.
- **Syllabus parser** — calendar UI is the actual product; parser was always the weakest link.
- **Daily briefing cache** — TTL cache only worth it once Phase 3 dashboards prove load-heavy.
- **`assignment_submissions`** — Canvas owns submission state.

---

## Open questions / future phases

- **Per-(user, concept) learnable τ.** Default τ = 14 days; tune per cohort once we have data on real retention.
- **DAS3H replacement for Beta-Binomial.** Once we have ≥ 6 months of attempt history per cohort, benchmark DAS3H against current Beta-Binomial + decay. May produce material lift on multi-skill items.
- **Coefficient calibration cadence.** Currently quarterly; may need monthly once volume grows.
- **Concept hierarchy (taxonomy, not dependency).** Add `concept_parent_id` if concept counts per course exceed ~100.
- **Cross-course concept ontology.** Worth revisiting once we have ≥ 50 courses with explicit overlap.
- **Forgetting curve learnability.** Replace global τ with `τ(user, concept) = f(prior attempts, item difficulty)` once the simple decay proves valuable.

---

## References

Validated against:

- [A Survey of Knowledge Tracing: Models, Variants, and Applications (arxiv 2105.15106)](https://arxiv.org/html/2105.15106v4)
- [Knowledge Tracing: A Survey (ACM Computing Surveys 2023)](https://dl.acm.org/doi/full/10.1145/3569576)
- [DAS3H: Modeling Student Learning and Forgetting (Choffin et al., EDM 2019)](https://arxiv.org/abs/1905.06873)
- [DAS3H reference implementation (GitHub)](https://github.com/BenoitChoffin/das3h)
- [A Trainable Spaced Repetition Model for Language Learning (Settles & Meeder, ACL 2016)](https://research.duolingo.com/papers/settles.acl16.pdf)
- [Duolingo half-life regression code](https://github.com/duolingo/halflife-regression)
- [A Contextual Bandits Framework for Personalized Learning Action Selection (Lan & Baraniuk, EDM 2016)](https://people.umass.edu/~andrewlan/papers/16edm-bandits.pdf)
- [Research Behind ALEKS — Knowledge Space Theory](https://www.aleks.com/about_aleks/knowledge_space_theory)
- [A practical perspective on knowledge space theory: ALEKS and its data](https://www.sciencedirect.com/science/article/abs/pii/S0022249621000134)
- [Adaptive Learning Tools and Engines — Open edX wiki (ALOSI)](https://openedx.atlassian.net/wiki/spaces/AC/pages/575799401/Adaptive+Learning+Tools+and+Engines)
- [Core Concept Identification in Educational Resources via Knowledge Graphs and LLMs (Springer 2024)](https://link.springer.com/article/10.1007/s42979-024-03341-y)
- [Leveraging LLMs for Automated Extraction and Structuring of Educational Concepts (MDPI 2025)](https://www.mdpi.com/2504-4990/7/3/103)

Existing Meli specs this builds on:

- [docs/superpowers/specs/2026-04-08-cle-difficulty-adapter.md](2026-04-08-cle-difficulty-adapter.md) — contextual bandit
- [docs/superpowers/specs/2026-04-11-difficulty-recalibration.md](2026-04-11-difficulty-recalibration.md) — recalibration
- [docs/superpowers/specs/2026-04-11-neural-spaced-repetition-design.md](2026-04-11-neural-spaced-repetition-design.md) — FSRS-5

---

## Implementation checklist

- [ ] Phase 1 Alembic revision: curriculum + calendar tables, ALTER existing content tables
- [ ] Phase 1 backend: CRUD APIs for modules / meetings / objectives / assignments
- [ ] Phase 1 frontend: instructor calendar editor, student calendar view
- [ ] Phase 1 ship + soak (≥ 2 weeks of real instructor use before Phase 2)
- [ ] Phase 2.1 Alembic revision: `concepts`, `concept_prerequisites`, `concept_tags`
- [ ] Phase 2.1 backend: extraction job, clustering, instructor curation API
- [ ] Phase 2.1 frontend: concept curation UI (cluster review)
- [ ] Phase 2.1 backfill: cascade-tag artifacts per course on instructor approval
- [ ] Phase 2.2 Alembic revision: `concept_mastery`, ALTER `revision_attempts`, ALTER `courses`
- [ ] Phase 2.2 service: Beta-Binomial update wired into all attempt handlers
- [ ] Phase 2.2 cron: nightly HLR decay job
- [ ] Phase 2.2 backfill: replay 90-day attempt history through Beta-Binomial
- [ ] Phase 2.2 ship + measure curation effort, mastery distribution sanity
- [ ] Phase 3 Alembic revision: `next_actions`, `instructor_alerts`, `action_outcomes`, `engine_overrides`
- [ ] Phase 3 backend: outer-fringe filter, scoring engine, alert evaluator, telemetry recorder
- [ ] Phase 3 frontend: student "today" / "next actions" view, instructor alert center, engine on/off toggle
- [ ] Phase 3 cron: coefficient retuning job (quarterly initially)
- [ ] Phase 3 ship with `random_50` enabled on at least one course for real A/B data

After Phase 3, we have efficacy telemetry — the data that proves moat to investors and to HKUST.
