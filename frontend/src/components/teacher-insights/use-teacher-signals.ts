"use client";

import { useAuthedQuery } from "@/hooks/use-authed-query";

/**
 * Teacher-owned list of signals (learning notes) for a course, RESHAPED from
 * `GET /courses/{id}/learning-notes` (`api/review.py::list_learning_notes`).
 *
 * This lives inside the teacher-insights surface (not `hooks/`) because it is
 * the ONE read the course-insights view needs that the pure-read insights
 * router does not expose: the individual signal ids that open the T077 signal
 * detail drawer (`useSignal(note.id)`). `useCourseInsights` returns only
 * aggregate counts, and `InstructorAlertResponse` does not surface a
 * `linked_note_id`, so the reviewable-signal list is sourced here. Owner-scoped
 * on the backend (`get_owned_course`); archived notes are excluded by default.
 */

/** One signal row — a subset of `LearningNoteResponse` the drawer opens over. */
export interface TeacherSignal {
  readonly id: string;
  readonly course_id: string;
  /** `null` = a whole-class (cohort) signal; otherwise a single student. */
  readonly user_id: string | null;
  readonly evidence_category: string | null;
  readonly observed_signal: string;
  readonly draft_interpretation: string | null;
  readonly review_status: string;
  readonly outcome_status: string | null;
  readonly report_eligibility: boolean;
  readonly created_at: string;
  readonly updated_at: string;
}

export const teacherSignalKeys = {
  list: (courseId: string) => ["insights", "teacher-signals", courseId] as const,
};

/**
 * GET `/courses/{id}/learning-notes` — the owned course's live signals, newest
 * first (archived excluded). Enabled once a `courseId` is present.
 */
export function useCourseSignals(courseId: string) {
  return useAuthedQuery<readonly TeacherSignal[]>({
    queryKey: teacherSignalKeys.list(courseId),
    path: `/courses/${courseId}/learning-notes`,
    enabled: Boolean(courseId),
  });
}
