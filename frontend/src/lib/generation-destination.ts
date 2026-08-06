import type { GenerationJob } from "@/hooks/use-generation-jobs";

/**
 * Where a finished generation job's "Open" action should land.
 *
 * Both the toast (`use-generation-jobs.tsx`) and the dock row
 * (`generation-dock.tsx`) used to build this href themselves, and both pointed
 * into the deprecated `/dashboard/*` tree, so a teacher who generated a quiz
 * from `/teacher/courses/{id}/practice` was dropped into a different shell with
 * no role lane and no way back through the current navigation. The two copies
 * had also drifted: the dock had no `generate_pronunciation` case at all, so
 * that row simply wasn't a link while the toast for the same job did navigate.
 *
 * Generation is instructor-only, so every destination is in the teacher lane.
 *
 * Quizzes: `run_generate_quiz` never sets `assessment_purpose`, so a generated
 * quiz always takes the column's `practice` server default, hence the
 * `practice/{id}` builder route rather than `quiz/{id}` (which is the graded
 * surface).
 */
export function generationDestination(job: GenerationJob): string | null {
  if (!job.result) return null;

  // encodeURIComponent each id segment so a stray path or query character in an
  // id can never break out of the intended route.
  const courseId = encodeURIComponent(job.courseId);
  const root = `/teacher/courses/${courseId}`;

  if (job.kind === "generate_quiz" && job.result.quiz_id) {
    return `${root}/practice/${encodeURIComponent(job.result.quiz_id)}`;
  }
  if (job.kind === "generate_flashcards" && job.result.flashcard_set_id) {
    // The current tree has no flashcard-set detail route; Activities is the
    // surface that lists them. Landing on the list beats landing on a 404.
    return `${root}/activities`;
  }
  if (job.kind === "generate_pronunciation" && job.result.pronunciation_set_id) {
    // Likewise no pronunciation-set detail route in the current tree.
    return `${root}/activities`;
  }
  if (job.kind === "generate_summary") {
    return `${root}/materials`;
  }
  return null;
}
