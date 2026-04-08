# CLE Phase 1c — Frontend + Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the frontend to real backend APIs (replacing all sample data), build Quiz and Flashcard UIs, add summary generation, and deploy to Railway + Vercel.

**Architecture:** Next.js 16 App Router with TanStack Query for data fetching, Clerk for auth (token passed to all API calls), shadcn/ui + Tailwind CSS for UI. All data flows through `apiFetch` wrapper → FastAPI backend.

**Tech Stack:** Next.js 16, React 19, TypeScript, TanStack Query v5, Clerk, shadcn/ui, Tailwind CSS, Playwright.

---

## File Structure

### New Pages (`frontend/src/app/`)

```
app/dashboard/
├── courses/[courseId]/
│   ├── quizzes/
│   │   ├── page.tsx                  # Quiz list (redirect, uses tab)
│   │   └── [quizId]/
│   │       ├── page.tsx              # Take quiz / view quiz detail
│   │       └── results/page.tsx      # Quiz attempt results
│   └── flashcards/
│       └── [setId]/page.tsx          # Study flashcard set
```

### New Components (`frontend/src/components/`)

```
components/
├── quiz/
│   ├── quiz-list.tsx                 # Quiz cards with status badges
│   ├── quiz-player.tsx              # Take a quiz (question by question)
│   ├── quiz-results.tsx             # Score + per-question review
│   └── generate-quiz-dialog.tsx     # Instructor: generate quiz from RAG
├── flashcard/
│   ├── flashcard-list.tsx           # Flashcard set cards
│   ├── flashcard-player.tsx         # Study mode with flip + SM-2 buttons
│   └── generate-flashcards-dialog.tsx # Generate flashcards from RAG
├── summary/
│   └── generate-summary-dialog.tsx  # Generate + display AI summary
└── course/
    └── course-data-provider.tsx     # Shared hooks for course data
```

### New Hooks (`frontend/src/hooks/`)

```
hooks/
├── use-course.ts                    # Fetch course detail
├── use-documents.ts                 # Fetch documents for a course
├── use-quizzes.ts                   # Fetch quizzes for a course
├── use-flashcard-sets.ts            # Fetch flashcard sets
└── use-api-token.ts                 # Get Clerk auth token for API calls
```

### Modified Files

```
app/dashboard/courses/[courseId]/page.tsx  # Replace sample data with real API
components/documents/upload-zone.tsx       # Add polling for status updates
lib/api.ts                                 # Add typed API response helpers
```

---

## Task 1: API Hooks Foundation

Create reusable hooks for auth token and API data fetching.

**Files:**
- Create: `frontend/src/hooks/use-api-token.ts`
- Create: `frontend/src/hooks/use-course.ts`
- Create: `frontend/src/hooks/use-documents.ts`
- Create: `frontend/src/hooks/use-quizzes.ts`
- Create: `frontend/src/hooks/use-flashcard-sets.ts`

- [ ] **Step 1: Create use-api-token.ts**

```typescript
// frontend/src/hooks/use-api-token.ts
"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback } from "react";

export function useApiToken() {
  const { getToken } = useAuth();

  const fetchToken = useCallback(async () => {
    const token = await getToken();
    if (!token) throw new Error("Not authenticated");
    return token;
  }, [getToken]);

  return { getToken: fetchToken };
}
```

- [ ] **Step 2: Create use-course.ts**

```typescript
// frontend/src/hooks/use-course.ts
"use client";

import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@clerk/nextjs";
import { apiFetch } from "@/lib/api";

interface CourseResponse {
  id: string;
  name: string;
  code: string | null;
  description: string | null;
  language: string;
  semester: string | null;
  instructor_id: string;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

interface ApiResponse<T> {
  success: boolean;
  data: T;
}

export function useCourse(courseId: string) {
  const { getToken } = useAuth();

  return useQuery({
    queryKey: ["course", courseId],
    queryFn: async () => {
      const token = await getToken();
      const res = await apiFetch<ApiResponse<CourseResponse>>(
        `/courses/${courseId}`,
        { token: token ?? undefined }
      );
      return res.data;
    },
  });
}

export function useCourses() {
  const { getToken } = useAuth();

  return useQuery({
    queryKey: ["courses"],
    queryFn: async () => {
      const token = await getToken();
      const res = await apiFetch<ApiResponse<CourseResponse[]>>("/courses", {
        token: token ?? undefined,
      });
      return res.data;
    },
  });
}
```

- [ ] **Step 3: Create use-documents.ts**

```typescript
// frontend/src/hooks/use-documents.ts
"use client";

import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@clerk/nextjs";
import { apiFetch } from "@/lib/api";

interface DocumentResponse {
  id: string;
  course_id: string;
  uploaded_by: string;
  filename: string;
  file_type: string;
  file_size: number | null;
  status: "pending" | "processing" | "ready" | "failed";
  page_count: number | null;
  word_count: number | null;
  created_at: string;
  updated_at: string;
}

interface ApiResponse<T> {
  success: boolean;
  data: T;
}

export function useDocuments(courseId: string) {
  const { getToken } = useAuth();

  return useQuery({
    queryKey: ["documents", courseId],
    queryFn: async () => {
      const token = await getToken();
      const res = await apiFetch<ApiResponse<DocumentResponse[]>>(
        `/courses/${courseId}/documents`,
        { token: token ?? undefined }
      );
      return res.data;
    },
    // Poll every 10s if any document is still processing
    refetchInterval: (query) => {
      const docs = query.state.data;
      if (docs?.some((d) => d.status === "pending" || d.status === "processing")) {
        return 10_000;
      }
      return false;
    },
  });
}
```

- [ ] **Step 4: Create use-quizzes.ts**

```typescript
// frontend/src/hooks/use-quizzes.ts
"use client";

import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@clerk/nextjs";
import { apiFetch } from "@/lib/api";

interface QuizResponse {
  id: string;
  course_id: string;
  title: string;
  description: string | null;
  quiz_type: string;
  is_published: boolean;
  question_count: number;
  created_at: string;
}

interface QuestionResponse {
  id: string;
  question_index: number;
  type: string;
  question_text: string;
  options: Record<string, string> | null;
  explanation: string | null;
}

interface QuizDetailResponse {
  id: string;
  course_id: string;
  title: string;
  description: string | null;
  quiz_type: string;
  is_published: boolean;
  questions: QuestionResponse[];
  created_at: string;
}

interface ApiResponse<T> {
  success: boolean;
  data: T;
}

export function useQuizzes(courseId: string) {
  const { getToken } = useAuth();

  return useQuery({
    queryKey: ["quizzes", courseId],
    queryFn: async () => {
      const token = await getToken();
      const res = await apiFetch<ApiResponse<QuizResponse[]>>(
        `/courses/${courseId}/quizzes`,
        { token: token ?? undefined }
      );
      return res.data;
    },
  });
}

export function useQuiz(quizId: string) {
  const { getToken } = useAuth();

  return useQuery({
    queryKey: ["quiz", quizId],
    queryFn: async () => {
      const token = await getToken();
      const res = await apiFetch<ApiResponse<QuizDetailResponse>>(
        `/quizzes/${quizId}`,
        { token: token ?? undefined }
      );
      return res.data;
    },
  });
}

export type { QuizResponse, QuizDetailResponse, QuestionResponse };
```

- [ ] **Step 5: Create use-flashcard-sets.ts**

```typescript
// frontend/src/hooks/use-flashcard-sets.ts
"use client";

import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@clerk/nextjs";
import { apiFetch } from "@/lib/api";

interface FlashcardSetResponse {
  id: string;
  course_id: string;
  title: string;
  card_count: number;
  created_at: string;
}

interface FlashcardCardResponse {
  id: string;
  card_index: number;
  front: string;
  back: string;
  created_at: string;
}

interface FlashcardSetDetailResponse {
  id: string;
  course_id: string;
  title: string;
  cards: FlashcardCardResponse[];
  created_at: string;
}

interface ApiResponse<T> {
  success: boolean;
  data: T;
}

export function useFlashcardSets(courseId: string) {
  const { getToken } = useAuth();

  return useQuery({
    queryKey: ["flashcard-sets", courseId],
    queryFn: async () => {
      const token = await getToken();
      const res = await apiFetch<ApiResponse<FlashcardSetResponse[]>>(
        `/courses/${courseId}/flashcard-sets`,
        { token: token ?? undefined }
      );
      return res.data;
    },
  });
}

export function useFlashcardSet(setId: string) {
  const { getToken } = useAuth();

  return useQuery({
    queryKey: ["flashcard-set", setId],
    queryFn: async () => {
      const token = await getToken();
      const res = await apiFetch<ApiResponse<FlashcardSetDetailResponse>>(
        `/flashcard-sets/${setId}`,
        { token: token ?? undefined }
      );
      return res.data;
    },
  });
}

export type { FlashcardSetResponse, FlashcardSetDetailResponse, FlashcardCardResponse };
```

- [ ] **Step 6: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit --pretty false
```

Expected: No errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/hooks/
git commit -m "feat: add TanStack Query hooks for course, documents, quizzes, and flashcards"
```

---

## Task 2: Wire Course Detail Page to Real API

Replace all sample/hardcoded data in the course detail page with real API calls.

**Files:**
- Modify: `frontend/src/app/dashboard/courses/[courseId]/page.tsx`

- [ ] **Step 1: Read the current course detail page**

Read `frontend/src/app/dashboard/courses/[courseId]/page.tsx` fully.

- [ ] **Step 2: Replace sample data with real API hooks**

Rewrite the page to:
1. Use `useCourse(courseId)` for course data
2. Use `useDocuments(courseId)` for the materials list
3. Use `useQuizzes(courseId)` for the quizzes tab
4. Use `useFlashcardSets(courseId)` for flashcard sets
5. Use `useUser()` from Clerk to determine if instructor
6. Show loading skeletons while data loads
7. Show error states when API calls fail
8. Remove all `sampleCourse` and `sampleDocuments` constants
9. Format file sizes from bytes (e.g., `file_size` → "2.4 MB")
10. Format dates from ISO strings using relative time (e.g., "2 days ago")

Keep the existing UI structure (tabs: Overview, Materials, Quizzes, Students) and design tokens. Just swap the data source.

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit --pretty false
```

- [ ] **Step 4: Verify page loads in browser**

Open `http://localhost:3000/dashboard/courses/{courseId}` — should show real data or proper empty states.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/dashboard/courses/
git commit -m "feat: wire course detail page to real backend API"
```

---

## Task 3: Quiz UI — Generate, List, Take, Results

**Files:**
- Create: `frontend/src/components/quiz/generate-quiz-dialog.tsx`
- Create: `frontend/src/components/quiz/quiz-list.tsx`
- Create: `frontend/src/components/quiz/quiz-player.tsx`
- Create: `frontend/src/components/quiz/quiz-results.tsx`
- Create: `frontend/src/app/dashboard/courses/[courseId]/quizzes/[quizId]/page.tsx`

- [ ] **Step 1: Create generate-quiz-dialog.tsx**

Dialog component for instructors to generate a quiz from course materials via RAG:
- Form fields: title (required), number of questions (slider/select 1-30, default 5)
- On submit: `POST /api/rag/generate-quiz` with `{ course_id, title, num_questions }`
- Show loading spinner during generation (can take 5-15s)
- On success: invalidate quizzes query, close dialog, show success toast or redirect
- On error: show error message in dialog
- Uses `useAuth()` for token and `useQueryClient()` for cache invalidation

- [ ] **Step 2: Create quiz-list.tsx**

Reusable component that renders a list of quizzes:
- Props: `courseId: string`, `isInstructor: boolean`
- Shows quiz cards with: title, question count, published badge, created date
- Instructor sees: "Generate Quiz" button (opens dialog), publish/unpublish toggle, delete button
- Student sees: only published quizzes, "Take Quiz" link
- Empty state: "No quizzes yet" with generate CTA for instructors
- Uses `useQuizzes(courseId)` hook

- [ ] **Step 3: Create quiz-player.tsx**

Full-screen quiz taking experience:
- Props: `quizId: string`
- Fetches quiz detail via `useQuiz(quizId)`
- Shows one question at a time with progress indicator (1/5)
- Multiple choice: 4 option buttons (A-D), selected state highlighted
- Navigation: Previous / Next buttons, or click question index dots
- Submit button appears after all questions answered
- On submit: `POST /api/quizzes/{quizId}/attempt` with `{ answers: { questionId: "A" } }`
- After submit: redirect to results page

- [ ] **Step 4: Create quiz-results.tsx**

Score and review component:
- Props: attempt response data
- Score display: big percentage + correct/total count
- Per-question review: question text, selected answer (red if wrong, green if right), correct answer, explanation
- "Back to Course" link

- [ ] **Step 5: Create quiz page at `courses/[courseId]/quizzes/[quizId]/page.tsx`**

```tsx
"use client";

import { use } from "react";
import { QuizPlayer } from "@/components/quiz/quiz-player";

interface QuizPageProps {
  params: Promise<{ courseId: string; quizId: string }>;
}

export default function QuizPage({ params }: QuizPageProps) {
  const { courseId, quizId } = use(params);
  return <QuizPlayer quizId={quizId} courseId={courseId} />;
}
```

- [ ] **Step 6: Wire quiz list into course detail page**

Update the Quizzes tab in `courses/[courseId]/page.tsx` to render `<QuizList courseId={courseId} isInstructor={isInstructor} />` instead of the placeholder.

- [ ] **Step 7: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit --pretty false
```

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/quiz/ frontend/src/app/dashboard/courses/
git commit -m "feat: add quiz generation, listing, player, and results UI"
```

---

## Task 4: Flashcard UI — Generate, List, Study

**Files:**
- Create: `frontend/src/components/flashcard/generate-flashcards-dialog.tsx`
- Create: `frontend/src/components/flashcard/flashcard-list.tsx`
- Create: `frontend/src/components/flashcard/flashcard-player.tsx`
- Create: `frontend/src/app/dashboard/courses/[courseId]/flashcards/[setId]/page.tsx`

- [ ] **Step 1: Create generate-flashcards-dialog.tsx**

Dialog for generating flashcards:
- Form: title (required), number of cards (1-50, default 10)
- On submit: `POST /api/rag/generate-flashcards` with `{ course_id, title, num_cards }`
- Loading state during generation
- On success: invalidate flashcard-sets query, close dialog

- [ ] **Step 2: Create flashcard-list.tsx**

List of flashcard sets:
- Props: `courseId: string`
- Cards showing: title, card count, created date
- "Generate Flashcards" button (opens dialog)
- "Study" link on each set → navigates to flashcard player
- Empty state: "No flashcard sets yet"

- [ ] **Step 3: Create flashcard-player.tsx**

Interactive study mode:
- Props: `setId: string`
- Fetches set detail via `useFlashcardSet(setId)`
- Shows one card at a time with flip animation (CSS transform rotateY)
- Front side: question/term. Click/tap to flip.
- Back side: answer/definition
- SM-2 rating buttons after viewing back: "Again" (0), "Hard" (2), "Good" (4), "Easy" (5)
- On rating: `PUT /api/flashcard-sets/{setId}/progress` with `{ card_id, quality }`
- Progress bar showing cards completed / total
- After all cards: summary (cards studied, next review date)
- "Back to Course" link

- [ ] **Step 4: Create flashcard study page**

```tsx
"use client";

import { use } from "react";
import { FlashcardPlayer } from "@/components/flashcard/flashcard-player";

interface FlashcardPageProps {
  params: Promise<{ courseId: string; setId: string }>;
}

export default function FlashcardPage({ params }: FlashcardPageProps) {
  const { courseId, setId } = use(params);
  return <FlashcardPlayer setId={setId} courseId={courseId} />;
}
```

- [ ] **Step 5: Add flashcard tab or section to course detail page**

Add flashcard list to the course page — either as a new tab or within the existing Quizzes tab renamed to "Practice".

- [ ] **Step 6: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit --pretty false
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/flashcard/ frontend/src/app/dashboard/courses/
git commit -m "feat: add flashcard generation, listing, and study mode with flip animation"
```

---

## Task 5: Summary Generation UI

**Files:**
- Create: `frontend/src/components/summary/generate-summary-dialog.tsx`

- [ ] **Step 1: Create generate-summary-dialog.tsx**

Dialog/panel for generating and viewing AI summaries:
- "Generate Summary" button in the course Overview tab
- On click: `POST /api/rag/generate-summary` with `{ course_id }`
- Show loading state with progress message ("Analyzing course materials...")
- Display generated summary in markdown format (use a simple markdown renderer or just render as formatted text with `whitespace-pre-wrap`)
- Allow re-generation
- Summary is not persisted — generated on demand each time

- [ ] **Step 2: Wire into course detail page**

Add the "Generate Summary" button to the Overview tab, below the course description card.

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit --pretty false
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/summary/ frontend/src/app/dashboard/courses/
git commit -m "feat: add AI summary generation UI for course materials"
```

---

## Task 6: Wire Dashboard + Course List to Real API

Replace sample data in dashboard home and course list pages.

**Files:**
- Modify: `frontend/src/app/dashboard/page.tsx`
- Modify: `frontend/src/app/dashboard/courses/page.tsx`

- [ ] **Step 1: Update dashboard home page**

Read `frontend/src/app/dashboard/page.tsx`. Replace hardcoded stats and course previews with:
- `useCourses()` hook for real course data
- Show actual course count, document counts aggregated from API
- Course preview cards link to real course detail pages
- Loading skeletons while fetching
- Empty state when no courses exist

- [ ] **Step 2: Update course list page**

Read `frontend/src/app/dashboard/courses/page.tsx`. Replace sample data with:
- `useCourses()` hook
- Real search/filter over actual course names
- Course cards with real data (name, code, language, semester)
- Create Course dialog already wired (from Phase 1a fix)

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit --pretty false
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/dashboard/
git commit -m "feat: wire dashboard and course list to real backend API"
```

---

## Task 7: Document Status Polling

Add real-time status updates for documents being processed.

**Files:**
- Modify: `frontend/src/app/dashboard/courses/[courseId]/page.tsx`

- [ ] **Step 1: Add polling to materials tab**

The `useDocuments` hook already has `refetchInterval` that polls every 10s when documents are pending/processing. Verify that:
1. After uploading a file, the document list refreshes and shows "Pending" badge
2. As the worker processes it, status changes to "Processing" then "Ready"
3. Polling stops automatically once all documents are ready
4. Failed documents show a red "Failed" badge

- [ ] **Step 2: Add upload success callback**

After a successful upload in `UploadZone`, invalidate the documents query:
```typescript
queryClient.invalidateQueries({ queryKey: ["documents", courseId] });
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/
git commit -m "feat: add document status polling and upload refresh"
```

---

## Task 8: Sidebar Navigation Updates

Update the sidebar to link to real pages.

**Files:**
- Modify: `frontend/src/components/layout/sidebar.tsx`

- [ ] **Step 1: Update sidebar links**

Read the current sidebar. Ensure navigation items link to actual routes:
- Dashboard → `/dashboard`
- Courses → `/dashboard/courses`
- Individual course → `/dashboard/courses/{courseId}`

The sidebar should highlight the active route based on the current pathname.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/layout/
git commit -m "fix: update sidebar navigation to use real routes"
```

---

## Task 9: Deploy Configuration

**Files:**
- Create: `frontend/.env.production.example`
- Modify: `backend/railway.toml` (if needed)
- Modify: `frontend/next.config.ts` (if needed)

- [ ] **Step 1: Create frontend production env example**

```env
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_...
CLERK_SECRET_KEY=sk_live_...
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_API_URL=https://your-backend.railway.app/api
```

- [ ] **Step 2: Verify backend Dockerfile builds**

```bash
cd backend && docker build -t cle-backend .
```

- [ ] **Step 3: Verify frontend builds for production**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: Document deploy steps**

Create brief deploy notes (not a full README — just enough to deploy):
- Railway: connect repo, set env vars, select backend/ as root, Dockerfile build
- Vercel: connect repo, set env vars, select frontend/ as root, Next.js framework preset

- [ ] **Step 5: Commit**

```bash
git add frontend/.env.production.example backend/
git commit -m "chore: add production deploy configuration"
```

---

## Task 10: Integration Verification

Full end-to-end check that everything works together.

**Files:** None (verification only)

- [ ] **Step 1: Verify both servers running**

```bash
# Backend on :8000, Frontend on :3000
curl -s http://localhost:8000/health
curl -s http://localhost:3000 -o /dev/null -w "%{http_code}"
```

- [ ] **Step 2: Walk through complete user flow**

1. Open `http://localhost:3000` → landing page renders
2. Sign in → redirected to dashboard
3. Dashboard shows real course data (or empty state)
4. Create a course → appears in list
5. Navigate to course detail → Overview tab shows real data
6. Upload a document → shows in Materials tab with "Pending" status
7. (If worker + R2 configured) Status changes to "Ready"
8. Generate Quiz → quiz appears in Quizzes tab
9. Take Quiz → see results with scores
10. Generate Flashcards → set appears
11. Study Flashcards → flip cards, rate them
12. Generate Summary → see AI-generated summary

- [ ] **Step 3: Run TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 4: Run all backend tests**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/ -v
```

- [ ] **Step 5: Commit any final fixes**

```bash
git add -A && git commit -m "fix: Phase 1c integration fixes"
```

---

## Summary

| Task | Component | Files | Description |
|------|-----------|-------|-------------|
| 1 | API Hooks | 5 hooks | TanStack Query hooks for all data |
| 2 | Course Detail | 1 page | Wire to real API, remove sample data |
| 3 | Quiz UI | 5 files | Generate, list, take, results |
| 4 | Flashcard UI | 4 files | Generate, list, study with flip + SM-2 |
| 5 | Summary UI | 1 component | Generate AI summaries on demand |
| 6 | Dashboard + List | 2 pages | Wire to real API |
| 7 | Status Polling | 1 page | Document processing status updates |
| 8 | Sidebar | 1 component | Fix navigation links |
| 9 | Deploy Config | 2-3 files | Production env + build verification |
| 10 | Integration | — | Full E2E verification |

**Total: 10 tasks, ~20 files created/modified.**
