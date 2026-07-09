import type { QuizResponse } from "@/hooks/use-quizzes";

/**
 * The two teacher assessment surfaces built on the shared quiz engine (P5
 * F2/F3). Practice and graded quizzes reuse the same list / builder / results
 * chrome; this config carries the per-surface differences (i18n namespace,
 * route base, whether the score-policy gate applies) so the shared components
 * stay generic. Distinct from `purpose` (`after_class|live`) — both surfaces
 * author `after_class` quizzes and branch only on `assessment_purpose`.
 */
export type AssessmentPurpose = "practice" | "graded";

/** i18n namespaces owned by F2/F3 respectively. */
export type AssessmentNamespace = "teacher.practice" | "teacher.quiz";

export interface AssessmentConfig {
  readonly purpose: AssessmentPurpose;
  /** `true` for graded quizzes — the score-policy panel + publish gate apply. */
  readonly graded: boolean;
  /** next-intl namespace for this surface's copy. */
  readonly ns: AssessmentNamespace;
  /**
   * Route segment under the teacher course workspace (`practice` | `quiz`).
   * A plain string (not a function) so the config stays fully serializable and
   * can be passed from a Server Component page into the client list/builder —
   * build the path with `assessmentBase(config, courseId)`.
   */
  readonly segment: "practice" | "quiz";
}

export const PRACTICE_CONFIG: AssessmentConfig = {
  purpose: "practice",
  graded: false,
  ns: "teacher.practice",
  segment: "practice",
};

export const QUIZ_CONFIG: AssessmentConfig = {
  purpose: "graded",
  graded: true,
  ns: "teacher.quiz",
  segment: "quiz",
};

/** Path base for an assessment surface under the teacher course workspace. */
export function assessmentBase(
  config: AssessmentConfig,
  courseId: string
): string {
  return `/teacher/courses/${courseId}/${config.segment}`;
}

/**
 * Filter a course's quiz list down to one assessment surface. The list hook
 * (`useQuizzes`) queries by `purpose`; `assessment_purpose` is a per-row field,
 * so the split is applied client-side. `after_class` quizzes authored before P5
 * backfill to `practice`, so they surface under the practice tab by default.
 */
export function filterByPurpose(
  quizzes: readonly QuizResponse[] | undefined,
  purpose: AssessmentPurpose
): readonly QuizResponse[] {
  if (!quizzes) return [];
  return quizzes.filter((q) => q.assessment_purpose === purpose);
}
