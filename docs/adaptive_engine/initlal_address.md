**The functional side is already quite solid.** The problem is that it's still stuck at the **"feature-rich AI learning tool"** stage, and there's still one missing layer between where we are and where we want to be: a **"curriculum-centered adaptive learning engine."** That missing layer is:

- curriculum structure
- concept / objective mapping
- concept-level student mastery
- next-best-action decision logic

Looking at the current README and DDL, the **content infrastructure** — document upload, parsing, chunking, embedding, retrieval, quiz/flashcard generation — is already strong. The **student evidence infrastructure** — quiz attempts, flashcard progress, revision attempts, bandit models, pronunciation scores — is also fairly substantial. But there is no schema that expresses "what concept does this question assess," "which concepts is this student weak in," or "so what should we give them next."

So what we need to do is not rebuild from scratch, but **upgrade by adding an education engine layer on top of the existing product.**

---

# The Upgrade Direction, Explained in Six Questions

## 1) What — What needs to be upgraded?

The upgrade target is not the quiz/flashcard/revision features themselves, but the **Curriculum Engine + Concept Mapping + Student Mastery Layer + Decision Layer** that sits on top of them.

Looking at the current DDL, `course` holds operational metadata like `settings`, `language`, `semester`, and `enroll_code`. Documents and chunks serve as the RAG storage structure. Quiz, flashcard, and revision are well-separated as learning activity structures. But there is no table that stores "which learning objective this question assesses" or "whether this student is weak on concept A and strong on concept B." This means the current system is an **adaptive toolset**, but not yet a **curriculum-centered learning engine**.

### Final Assessment

**The answer is not a rebuild, but a layered upgrade.**

---

## 2) Why — Why that approach?

The content and student evidence layers are already strong enough.

- `chunks` has embeddings, `tsvector_content`, HNSW, GIN, and triggers, making the RAG/search infrastructure highly mature
- `quiz_attempts` stores answers, scores, correct counts, and timestamps
- `flashcard_progress` stores SM-2/FSRS state
- `revision_attempts`, `bandit_models`, and `recalibration_stats/models` handle difficulty adaptation and recalibration

So the problem is not a lack of features — it's a **lack of pedagogical abstraction.**

In the current state, a judgment like "give this student a medium-difficulty question" is possible, but a judgment like "this student has low inference mastery, so they should review supporting detail inference before argument structure" is structurally impossible.

---

## 3) Who — Who are the core users of this upgrade?

There are two.

**First, instructors / the center:**
- Need to be able to understand why the AI made a given recommendation (decision engine)
- Want to see student status against course objectives
- Want to see content coverage gaps (the curriculum engine covers this too)

**Second, students:**
- Not just solving lots of problems, but understanding:
  - "Where am I currently weak?"
  - "Why should I be looking at this material next?"

So this upgrade is partly a student UX improvement, but more fundamentally, it's about **turning the system into something explainable to instructors.**

---

## 4) When — In what order should this happen?

The order must be as follows:

### Phase 1
**Add the curriculum spine**
- `course_modules`
- `learning_objectives`
- `concepts`
- `concept_prerequisites`
- `objective_concepts`

### Phase 2
**Connect existing content to concepts**
- `content_concepts`
- Targets: `chunks`, `questions`, `flashcard_cards`, `revision_pool_items`

### Phase 3
**Add the student mastery layer**
- `student_concept_mastery`
- `student_concept_evidence`

### Phase 4
**Decision engine MVP**
- Next-best-action recommendations based on prerequisite completion + low mastery + recency
- Existing `bandit_models` retained as the final difficulty selector

### Phase 5
**Instructor-facing dashboard**
- Concept mastery heatmap
- Objective coverage
- Recommendation rationale

This order matters because building mastery without a concept spine leaves it floating in the air, and building a decision engine without mastery just produces a rule-based recommender.

---

## 5) Where — What exactly needs to change?

Not everything — precisely three areas:

### A. DB Schema
The biggest current gap is the complete absence of concept/objective at the schema level. The starting point for the upgrade is adding to the DDL.

### B. Backend Orchestration
The current structure is API/service-oriented by feature. An engine layer needs to be added on top:
- curriculum service
- mastery update service
- recommendation service

### C. Instructor-Facing UI
Before the student UI, the instructor interface needs to surface:
- concept map
- student mastery
- content alignment
- next recommendation rationale

---

## 6) How — How should it be implemented?

The core principles are:

### Principle 1: Preserve Existing Tables as Much as Possible
The existing infrastructure is well-built and should not be discarded. These all become **evidence sources for the new semantic layer:**
- `chunks`
- `questions`
- `quiz_attempts`
- `flashcard_progress`
- `revision_attempts`
- `bandit_models`

### Principle 2: New Additions Should Be Relationship Tables
Recommended new tables:
- `course_modules`
- `learning_objectives`
- `concepts`
- `concept_prerequisites`
- `objective_concepts`
- `content_concepts`
- `student_concept_mastery`
- `student_concept_evidence`
- `learning_recommendations`

### Principle 3: Reposition Bandit as a Sub-Engine, Not the Core Engine
`bandit_models` is well-suited as a per-user/per-course/per-content-type difficulty selector, and should remain in that role. But it now needs to sit below a higher-level decision layer that determines which concept to address. The hierarchy should be:
- **Top level:** Which concept to target
- **Mid level:** Which content to deliver
- **Bottom level:** Whether to deliver it as easy/medium/hard

### Principle 4: Treat Quiz/Flashcard/Revision as a Shared Evidence System
Currently they look like separate features. After the upgrade, all three should feed into student mastery as evidence sources:
- Quiz accuracy rate → concept evidence
- Flashcard recall → retention evidence
- Pronunciation → speaking concept evidence
- Revision score → adaptive evidence

---

## Final Conclusion

In one sentence:

**Meli's content engine and student evidence engine are already strong, so the next step is to add a curriculum engine and concept-based mastery layer, elevating the bandit-centered difficulty adaptation system into a curriculum-centered learning engine.**

In short:
- **The current direction is right**
- **But the current system's central axis leans too heavily on difficulty adaptation**
- **So the next upgrade is to introduce concept/objective/prerequisite/mastery at the DB level**

**Why We Need to Go Adaptive**

The reason we need to go adaptive is not because it sounds educationally sophisticated — it's because it makes for a **stronger product from a business standpoint.** Meli is already a fairly complete learning platform: document upload, RAG-based content processing, AI quiz generation, flashcards, live quizzes, pronunciation assessment, and an analytics dashboard. Based on the README, the current product is structured to convert static course materials into interactive study tools, offering students adaptive difficulty revision, spaced repetition flashcards, pronunciation grading, and live quizzes, while giving instructors analytics and Canvas integration. The DB already has tables like `chunks`, `quizzes`, `questions`, `flashcard_progress`, `revision_attempts`, `bandit_models`, `student_progress`, and `canvas_integrations`, providing a solid foundation for content processing and student activity data accumulation. In other words, we are not a team lacking features — we are at the stage where we need to tie those many features together into a higher-order learning engine.

The problem is that in its current state, the product is still likely to be read as **"a feature-rich AI study tool."** The market already has plenty of tools that summarize PDFs, generate questions, create flashcards, and answer like a chatbot. These features are genuinely convenient for users, but from an investor's perspective, the reaction tends to be: "Nice AI study tool. But couldn't another team build something similar?" In fact, the core value proposition in the current README starts from generating quizzes, flashcards, and summaries from course materials. That's a good starting point, but on its own it lacks long-term differentiation and is vulnerable to pricing pressure. Ultimately, relying on generative features alone weakens the product moat and risks the product being perceived as a convenience tool rather than an institution-grade platform.

This is exactly where adaptive becomes critical. Going adaptive doesn't mean "delivering questions in a slightly different way." It means becoming a **system that accumulates per-student learning data and uses that data to design different learning experiences going forward.** Even now, according to the README, revision mode uses a contextual bandit to build a state vector from recent attempt history, select difficulty accordingly, and update its policy based on the outcome as a reward signal. Flashcards also adjust review timing per student. So the seeds of adaptivity already exist in the product. But the current adaptation is centered on difficulty adjustment and review timing. What we want to do in the next stage is elevate this into a **curriculum-centered adaptive engine** — one that determines not just what a student got wrong, but which concepts they haven't yet understood, which prerequisite concepts are missing, and therefore what content to present next, at what difficulty, and in what order.

The first reason adaptive matters from an investor's perspective is **replication difficulty.** A quiz generator or summarizer is relatively easy to imitate on the surface. An adaptive learning engine is a different story. Once you add per-student state storage, learning history accumulation, difficulty recalibration, review timing logic, recommendation logic, and eventually concept-level mastery tracking, the surface UI may look similar, but the actual engine performance cannot be easily replicated. The current DB already has tables like `bandit_models`, `recalibration_models`, `recalibration_stats`, `flashcard_progress`, and `scheduler_models`, reflecting an intent to adjust the system based on student responses and item difficulty. Add concept mastery and a recommendation layer on top of that, and what competitors can copy is the "features" — but the learning data we've accumulated and the personalization policies we've developed become very difficult to replicate. VCs look for exactly this kind of moat.

The second reason is the **data flywheel.** A pure generative tool accumulates limited data no matter how much it's used. You might log how many times a user clicked "summarize," but there isn't enough structured learning data accumulating to progressively improve the product. In an adaptive system, on the other hand, data continuously builds up: at what difficulty level does each student start breaking down, what question types do they make repeated mistakes on, which content formats yield better learning outcomes, and which review timings actually improve retention. Looking at the current structure alone, `quiz_attempts`, `revision_attempts`, `flashcard_progress`, `pronunciation_scores`, and `student_progress` all maintain per-student histories. Data is already accumulating — and once concept-level mapping is added, this data stops being a simple log and becomes a **learner intelligence asset.** For investors, this kind of structure is far more attractive than a plain SaaS product, because it looks like a **compounding business** where the product gets better and the data asset grows alongside it.

The third reason is the **institutional sales narrative.** Schools and centers don't allocate large budgets just because "AI auto-generates questions." They can see that as something partially substitutable with ChatGPT or other tools. But once an adaptive layer is in place, the sales argument changes entirely. The system is no longer just a convenience feature — it becomes learning operations infrastructure that tracks each student's weak areas, connects course materials to performance, surfaces class-wide learning gaps for instructors, identifies at-risk students early, and adjusts the priority of review and practice. The current product already has an instructor analytics API and Canvas integration, so strengthening the adaptive layer would allow us to position Meli as a "system of insight and intervention for classroom operations." That is a significantly stronger pitch in institutional sales.

The fourth reason is **contract size and pricing structure.** Staying positioned as an AI study tool naturally drives prices down. Users tend to think of it as "a tool that generates a few questions," and the sales target tends to stay at the level of individual students or individual instructors. But once positioned as an adaptive learning engine, the pricing logic shifts from usage fees to learning outcomes, performance visibility, retention improvement, instructor support, and curriculum alignment. The unit of sale also moves up from individual students to courses, departments, language centers, and universities. Meli already has an enrollment-scoped structure, course analytics, Canvas integration, and live session management, so adding the adaptive layer would naturally enable upselling as an institution-grade product — which is critical for growing ARPU and moving toward annual contract structures.

The fifth reason is the **expansion story.** A simple quiz generator or AI tutor can look impressive in a demo but has a weak long-term expansion narrative. An adaptive engine, by contrast, creates a structure that can scale in stages. It can start with language learning self-study optimization, then expand to teacher copilot for remediation, then to course-level mastery analytics, then to department-level learning intelligence. The README and DDL already have separate layers for content ingestion, revision, pronunciation, gamification, instructor analytics, and Canvas sync. The foundation for expansion is in place. The only missing piece is the concept/objective/mastery/recommendation layer that binds all of these into a single learning intelligence system. The adaptive direction is therefore not feature expansion — it is **platformification.**

---

To summarize: **staying as a bundle of AI study features means being too easily replicated, failing to become an institution-budget product, and being unable to convert accumulated data into a moat. Going adaptive means per-student learning data compounds alongside product performance, gives instructors and institutions a real reason to pay, and positions us long-term as a learning infrastructure company.** That is why going adaptive is not a feature choice — it is a strategic business choice.