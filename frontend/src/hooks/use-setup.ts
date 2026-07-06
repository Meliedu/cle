"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/hooks/use-auth";
import { useAuthedQuery } from "@/hooks/use-authed-query";
import { ApiError, apiFetch, type ApiEnvelope } from "@/lib/api";

/**
 * TanStack hooks over the course-setup routers (backend Tasks 8/9/10):
 * `setup.py` state + analyze/publish/reopen, checkpoint generation, and the
 * score-category list. Query keys are namespaced under `["setup", courseId]`
 * so invalidating that prefix refreshes every derived slice.
 */

// ----- step keys (mirror backend `SETUP_STEP_KEYS`, in wizard order) -----

/**
 * Ordered setup-step keys, mirroring `app/services/setup.py::SETUP_STEP_KEYS`.
 * The wizard renders the rail in exactly this order; each key maps to a
 * `teacher.setup.steps.*` label and a per-step done flag in `SetupState.steps`.
 */
export const SETUP_STEP_KEYS = [
  "basics",
  "syllabus",
  "materials",
  "schedule",
  "analyzer_review",
  "ilo_map",
  "checkpoints",
  "score_policy",
  "class_code",
] as const;

export type SetupStepKey = (typeof SETUP_STEP_KEYS)[number];

// ----- types (mirror backend schemas) -----

export type SetupStatus = "draft" | "in_review" | "published";
export type ContextStatus = "draft" | "approved";

/** Mirrors `SetupStateResponse` (`app/schemas/setup.py`). */
export interface SetupState {
  readonly setup_status: SetupStatus;
  readonly context_status: ContextStatus;
  /** Per-step done flags keyed by the backend `SETUP_STEP_KEYS`. */
  readonly steps: Readonly<Record<string, boolean>>;
  /** Step keys still incomplete; publish is gated until this is empty. */
  readonly missing: readonly string[];
}

export interface MissingSource {
  readonly kind: string;
  readonly id: string;
  readonly label: string;
}

/** Result payload produced by the `analyze_course_setup` job. */
export interface SetupAnalysisResult {
  readonly course_id: string;
  readonly counts: {
    readonly documents: number;
    readonly meetings: number;
    readonly objectives: number;
  };
  readonly missing_sources: readonly MissingSource[];
  readonly has_missing_sources: boolean;
}

/** Mirrors `SetupAnalysisResponse` (`app/schemas/setup.py`). */
export interface SetupAnalysis {
  readonly ready: boolean;
  readonly analysis: SetupAnalysisResult | null;
}

/** Mirrors `ScoreCategoryResponse` (`app/schemas/score.py`). */
export interface ScoreCategory {
  readonly id: string;
  readonly course_id: string;
  readonly name: string;
  /** `Decimal` serialized by FastAPI's json encoder → number. */
  readonly weight: number | null;
  readonly points_pool: number | null;
  readonly sort: number;
  readonly created_at: string;
  readonly updated_at: string;
}

// ----- typed gate errors -----

/**
 * The typed error codes the setup/checkpoint routers raise (spec §3.4). The UI
 * switches on these to render the right blocked/review state instead of a
 * generic toast.
 */
export type SetupErrorCode =
  | "SETUP_INCOMPLETE"
  | "SETUP_NOT_OPEN"
  | "UNKNOWN_STEP"
  | "FINAL_CARD_FIXED"
  | "REVIEW_REQUIRED"
  | "REMOVE_REASON_REQUIRED";

const SETUP_ERROR_CODES: readonly SetupErrorCode[] = [
  "SETUP_INCOMPLETE",
  "SETUP_NOT_OPEN",
  "UNKNOWN_STEP",
  "FINAL_CARD_FIXED",
  "REVIEW_REQUIRED",
  "REMOVE_REASON_REQUIRED",
];

/**
 * Narrow an unknown mutation/query error to a known setup gate code, or `null`
 * when it is not one (network error, auth error, unknown code).
 */
export function setupErrorCode(error: unknown): SetupErrorCode | null {
  if (
    error instanceof ApiError &&
    error.code !== undefined &&
    (SETUP_ERROR_CODES as readonly string[]).includes(error.code)
  ) {
    return error.code as SetupErrorCode;
  }
  return null;
}

// ----- query keys -----

export const setupKeys = {
  state: (courseId: string) => ["setup", courseId] as const,
  analysis: (courseId: string) => ["setup", courseId, "analysis"] as const,
  scoreCategories: (courseId: string) =>
    ["setup", courseId, "score-categories"] as const,
};

const ANALYSIS_POLL_INTERVAL_MS = 3000;

// ----- queries -----

/** GET `/courses/{id}/setup` — the wizard's checklist + gate state. */
export function useSetupState(courseId: string) {
  return useAuthedQuery<SetupState>({
    queryKey: setupKeys.state(courseId),
    path: `/courses/${courseId}/setup`,
    enabled: Boolean(courseId),
  });
}

/**
 * GET `/courses/{id}/setup/analysis` — the latest analyze-job result. When
 * `poll` is set, refetches every few seconds until `ready` flips true,
 * mirroring the generation-job polling pattern.
 */
export function useSetupAnalysis(
  courseId: string,
  options: { poll?: boolean } = {}
) {
  const { poll = false } = options;
  return useAuthedQuery<SetupAnalysis>({
    queryKey: setupKeys.analysis(courseId),
    path: `/courses/${courseId}/setup/analysis`,
    enabled: Boolean(courseId),
    refetchInterval: (query) => {
      if (!poll) return false;
      return query.state.data?.ready ? false : ANALYSIS_POLL_INTERVAL_MS;
    },
  });
}

/** GET `/courses/{id}/score-categories` — the score-policy step's categories. */
export function useScoreCategories(courseId: string) {
  return useAuthedQuery<readonly ScoreCategory[]>({
    queryKey: setupKeys.scoreCategories(courseId),
    path: `/courses/${courseId}/score-categories`,
    enabled: Boolean(courseId),
  });
}

// ----- mutations -----

interface StepUpdate {
  readonly step: string;
  readonly done: boolean;
}

interface StepMutationContext {
  readonly previous: SetupState | undefined;
}

/**
 * PATCH `/courses/{id}/setup` — toggle a checklist step. Applies an optimistic
 * update to the cached `SetupState` (mirroring `useUpdateNotificationPrefs`),
 * rolls back on error, reconciles with the server response, and revalidates.
 */
export function useSetStep(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation<SetupState, Error, StepUpdate, StepMutationContext>({
    mutationFn: async ({ step, done }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<SetupState>>(
        `/courses/${courseId}/setup`,
        { method: "PATCH", token, body: JSON.stringify({ step, done }) }
      );
      return response.data;
    },
    onMutate: async ({ step, done }) => {
      const key = setupKeys.state(courseId);
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<SetupState>(key);
      if (previous) {
        const steps = { ...previous.steps, [step]: done };
        const missing = Object.keys(steps).filter((k) => !steps[k]);
        queryClient.setQueryData<SetupState>(key, {
          ...previous,
          steps,
          missing,
        });
      }
      return { previous };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(setupKeys.state(courseId), context.previous);
      }
    },
    onSuccess: (data) => {
      queryClient.setQueryData(setupKeys.state(courseId), data);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: setupKeys.state(courseId) });
    },
  });
}

/** POST `/courses/{id}/setup/analyze` — enqueue the analyze job (202). */
export function useAnalyzeSetup(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation<void, Error, void>({
    mutationFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await apiFetch<ApiEnvelope<null>>(
        `/courses/${courseId}/setup/analyze`,
        { method: "POST", token }
      );
    },
    onSuccess: () => {
      // A fresh job is running — invalidate so polling picks up the new result.
      queryClient.invalidateQueries({ queryKey: setupKeys.analysis(courseId) });
    },
  });
}

/** POST `/courses/{id}/setup/publish` — flips the course-open gate (Decision 1). */
export function usePublishSetup(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation<SetupState, Error, void>({
    mutationFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<SetupState>>(
        `/courses/${courseId}/setup/publish`,
        { method: "POST", token }
      );
      return response.data;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(setupKeys.state(courseId), data);
      queryClient.invalidateQueries({ queryKey: setupKeys.state(courseId) });
    },
  });
}

/** POST `/courses/{id}/setup/reopen` — rolls setup back without locking students out. */
export function useReopenSetup(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation<SetupState, Error, void>({
    mutationFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<SetupState>>(
        `/courses/${courseId}/setup/reopen`,
        { method: "POST", token }
      );
      return response.data;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(setupKeys.state(courseId), data);
      queryClient.invalidateQueries({ queryKey: setupKeys.state(courseId) });
    },
  });
}

interface GenerateCheckpointsInput {
  readonly meetingId?: string;
  readonly reviewCardCount?: number;
}

/** POST `/courses/{id}/checkpoints/generate` — enqueue grounded generation (202). */
export function useGenerateCheckpoints(courseId: string) {
  const { getToken } = useAuth();

  return useMutation<void, Error, GenerateCheckpointsInput | void>({
    mutationFn: async (input) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const body: Record<string, unknown> = {};
      if (input && input.meetingId) body.meeting_id = input.meetingId;
      if (input && input.reviewCardCount !== undefined) {
        body.review_card_count = input.reviewCardCount;
      }
      await apiFetch<ApiEnvelope<null>>(
        `/courses/${courseId}/checkpoints/generate`,
        { method: "POST", token, body: JSON.stringify(body) }
      );
    },
  });
}
