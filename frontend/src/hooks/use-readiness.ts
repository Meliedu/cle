"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/hooks/use-auth";
import { useAuthedQuery } from "@/hooks/use-authed-query";
import { ApiError, apiFetch, type ApiEnvelope } from "@/lib/api";

/**
 * TanStack hooks over the readiness router (P2 Task 4): code-gated course
 * preview, the per-course readiness summary, and phase submission. The funnel
 * passes the same `code` it resolved at S003 as a query param — readiness is
 * pre-enrollment, so the backend authorizes on a valid code (or an existing
 * enrollment) rather than requiring the student to have joined.
 */

export type ReadinessPreviewDepth = "short" | "deep";

/** Mirrors backend `CoursePreviewOut` (`app/schemas/readiness.py`). */
export interface CoursePreview {
  readonly id: string;
  readonly name: string;
  readonly code: string | null;
  readonly language: string;
  readonly description: string | null;
  readonly is_open: boolean;
  readonly join_mode: string;
  readonly depth: string;
  readonly detail: Record<string, unknown> | null;
}

/** Mirrors backend `ReadinessResponseOut`. */
export interface ReadinessResponseOut {
  readonly phase: string;
  readonly status: string;
  readonly answers: Record<string, unknown>;
  readonly result: Record<string, unknown>;
}

/** Mirrors backend `ReadinessSummaryOut`. */
export interface ReadinessSummary {
  readonly completed_phases: readonly string[];
  readonly recommendation: Record<string, unknown> | null;
  readonly answers: Record<string, unknown>;
}

export const readinessKeys = {
  preview: (courseId: string, depth: ReadinessPreviewDepth) =>
    ["readiness-preview", courseId, depth] as const,
  summary: (courseId: string) => ["readiness-summary", courseId] as const,
};

// ----- typed readiness errors -----

/** The readiness router's typed error codes (mapped to 422 structured detail). */
export type ReadinessErrorCode = "UNKNOWN_PHASE";

const READINESS_ERROR_CODES: readonly ReadinessErrorCode[] = ["UNKNOWN_PHASE"];

/** Narrow an unknown error to a known readiness code, or `null` otherwise. */
export function readinessErrorCode(error: unknown): ReadinessErrorCode | null {
  if (
    error instanceof ApiError &&
    error.code !== undefined &&
    (READINESS_ERROR_CODES as readonly string[]).includes(error.code)
  ) {
    return error.code as ReadinessErrorCode;
  }
  return null;
}

// ----- queries -----

/**
 * GET `/courses/{id}/preview?code=&depth=` — the code-gated course preview
 * (S005 short / S010 deep). Disabled until both a course id and a code are
 * present so it never fires before S003 resolves.
 */
export function useCoursePreview(
  courseId: string,
  code: string,
  depth: ReadinessPreviewDepth = "short"
) {
  return useAuthedQuery<CoursePreview>({
    queryKey: readinessKeys.preview(courseId, depth),
    path: `/courses/${courseId}/preview?code=${encodeURIComponent(code)}&depth=${depth}`,
    enabled: Boolean(courseId) && Boolean(code),
  });
}

/** GET `/courses/{id}/readiness/summary?code=` — completed phases + recommendation. */
export function useReadinessSummary(courseId: string, code: string) {
  return useAuthedQuery<ReadinessSummary>({
    queryKey: readinessKeys.summary(courseId),
    path: `/courses/${courseId}/readiness/summary?code=${encodeURIComponent(code)}`,
    enabled: Boolean(courseId) && Boolean(code),
  });
}

// ----- mutations -----

interface SubmitPhaseInput {
  readonly phase: string;
  readonly answers: Record<string, unknown>;
}

/**
 * POST `/courses/{id}/readiness/{phase}?code=` — persist a survey/ready-check
 * phase (upserts server-side). Invalidates the readiness summary so completed
 * phases and any computed recommendation refresh.
 */
export function useSubmitPhase(courseId: string, code: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation<ReadinessResponseOut, Error, SubmitPhaseInput>({
    mutationFn: async ({ phase, answers }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<ReadinessResponseOut>>(
        `/courses/${courseId}/readiness/${phase}?code=${encodeURIComponent(code)}`,
        { method: "POST", token, body: JSON.stringify({ answers }) }
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: readinessKeys.summary(courseId),
      });
    },
  });
}
