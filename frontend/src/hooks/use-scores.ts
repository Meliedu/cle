"use client";

import { useMutation } from "@tanstack/react-query";

import { useAuth } from "@/hooks/use-auth";
import { useAuthedQuery } from "@/hooks/use-authed-query";
import { API_URL, ApiError } from "@/lib/api";

/**
 * TanStack hooks over the scores router (backend B11). The teacher read
 * (`useCourseScores`) returns every active student's per-category / per-artifact
 * rollup; the student read (`useMyScores`) returns only the caller's own record
 * (S059); `useGradeExport` streams the audited CSV and triggers a browser
 * download. Query keys: `["scores", courseId]` (teacher), `["my-scores",
 * courseId]` (student).
 */

// ----- types (mirror backend `app/schemas/score.py` / `services/scores.py`) -----

/** One graded artifact contributing to a category rollup. */
export interface ScoreArtifact {
  readonly kind: "quiz" | "activity";
  readonly artifact_id: string;
  readonly title: string;
  readonly category_id: string | null;
  readonly points: number | null;
  readonly score_pct: number | null;
  readonly earned_points: number | null;
  readonly submitted: boolean;
}

/** A per-category rollup within a student's score record. */
export interface ScoreCategoryRollup {
  readonly category_id: string;
  readonly category_name: string;
  readonly weight: number;
  readonly points_pool: number | null;
  readonly earned_points: number | null;
  readonly possible_points: number | null;
  readonly artifacts: readonly ScoreArtifact[];
}

/** Mirrors `StudentScoreRecord` — one student's full per-category rollup. */
export interface StudentScoreRecord {
  readonly user_id: string;
  readonly full_name: string | null;
  readonly email: string;
  readonly categories: readonly ScoreCategoryRollup[];
}

export const scoreKeys = {
  course: (courseId: string) => ["scores", courseId] as const,
  mine: (courseId: string) => ["my-scores", courseId] as const,
};

// ----- queries -----

/**
 * GET `/courses/{id}/scores` — every active student's per-category / per-artifact
 * rollup (owner-guarded; a student caller 403s).
 */
export function useCourseScores(courseId: string) {
  return useAuthedQuery<readonly StudentScoreRecord[]>({
    queryKey: scoreKeys.course(courseId),
    path: `/courses/${courseId}/scores`,
    enabled: Boolean(courseId),
  });
}

/**
 * GET `/users/me/courses/{id}/scores` — the caller's own score record, or
 * `null` when the caller has no graded artifacts yet (S059). Enrollment-scoped.
 */
export function useMyScores(courseId: string) {
  return useAuthedQuery<StudentScoreRecord | null>({
    queryKey: scoreKeys.mine(courseId),
    path: `/users/me/courses/${courseId}/scores`,
    enabled: Boolean(courseId),
  });
}

// ----- audited CSV export -----

/**
 * GET `/courses/{id}/grade-export.csv` — streams the CSV attachment (every
 * export is audited server-side, backend B11) and triggers a browser download.
 * A raw `fetch` is used (not `apiFetch`) because the response is `text/csv`, not
 * the JSON envelope. Owner-guarded. Runs only on the client (on click).
 */
export function useGradeExport(courseId: string) {
  const { getToken } = useAuth();
  return useMutation<void, Error, void>({
    mutationFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");

      const res = await fetch(
        `${API_URL}/courses/${courseId}/grade-export.csv`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!res.ok) {
        throw new ApiError(res.status, `Grade export failed (HTTP ${res.status}).`);
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `grade-export-${courseId}.csv`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    },
  });
}
