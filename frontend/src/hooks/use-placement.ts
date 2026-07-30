"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/hooks/use-auth";
import { useAuthedQuery } from "@/hooks/use-authed-query";
import { ApiError, apiFetch, type ApiEnvelope } from "@/lib/api";

/**
 * TanStack hooks over the placement router.
 *
 * The types mirror the backend schemas exactly, and that mirroring is load
 * bearing: `PlacementItem` has no field that could hold a key, an answer text
 * or a reference band, so a component cannot render one even by accident. The
 * restricted shapes live in the review types, which only the instructor
 * surfaces import.
 */

// ---------------------------------------------------------------------------
// Student types (safe surface only)
// ---------------------------------------------------------------------------

export type PlacementSection = "listening" | "language_use" | "reading";

export interface PlacementOption {
  readonly letter: string;
  readonly text: string;
}

/** Mirrors backend `PlacementItemOut`. Deliberately has no restricted field. */
export interface PlacementItem {
  readonly id: string;
  readonly question_number: number;
  readonly section: PlacementSection;
  readonly response_format: string;
  readonly option_letters: readonly string[];
  readonly expected_seconds: number;
  readonly audio_playback: number | null;
  readonly passage: string | null;
  readonly stem: string | null;
  readonly prompt: string | null;
  readonly options: readonly PlacementOption[];
}

export interface PlacementIntro {
  /** False when no version is published or the window is shut. */
  readonly available: boolean;
  readonly unavailable_reason: "not_published" | "window_closed" | null;
  readonly version_code: string | null;
  readonly duration_minutes: number;
  readonly section_counts: Readonly<Record<string, number>>;
  readonly total_items: number;
  readonly max_attempts: number;
  readonly attempts_used: number;
  readonly attempts_remaining: number;
  readonly purpose: string;
  readonly privacy: string;
  readonly window_opens_at: string | null;
  readonly window_closes_at: string | null;
  readonly comparability_note: string;
}

export interface PlacementAttempt {
  readonly id: string;
  readonly state: string;
  readonly attempt_number: number;
  readonly form_code: string;
  /** False until CLE approves recorded audio; listening is proctor-read. */
  readonly audio_available: boolean;
  readonly started_at: string | null;
  readonly expires_at: string | null;
  readonly submitted_at: string | null;
  readonly seconds_remaining: number | null;
  readonly answered_count: number;
  readonly total_items: number;
}

export interface PlacementAttemptDetail extends PlacementAttempt {
  readonly items: readonly PlacementItem[];
  readonly saved_responses: Readonly<Record<string, string | null>>;
}

export interface PlacementResult {
  readonly attempt_id: string;
  readonly state: string;
  readonly released: boolean;
  readonly submitted_at: string | null;
  readonly recommended_course: string | null;
  readonly claim_limit: string;
}

// ---------------------------------------------------------------------------
// Review types (restricted — instructor surfaces only)
// ---------------------------------------------------------------------------

export interface PlacementQueueItem {
  readonly attempt_id: string;
  readonly student_name: string | null;
  readonly student_email: string | null;
  readonly attempt_number: number;
  readonly form_code: string;
  readonly state: string;
  readonly confidence: string | null;
  readonly provisional_course: string | null;
  readonly highest_sustained_band: number | null;
  readonly review_flags: readonly string[];
  readonly submitted_at: string | null;
}

export interface PlacementQueue {
  readonly needs_review: number;
  readonly ready_to_approve: number;
  readonly blocked: number;
  readonly items: readonly PlacementQueueItem[];
}

export interface PlacementTeacherFlag {
  readonly code: string;
  readonly detail: string;
  readonly source?: string;
}

export interface PlacementReviewResponse {
  readonly question_number: number;
  readonly section: string;
  readonly response_format: string;
  readonly legacy_band: number;
  readonly item_id: string;
  readonly correct_answer: string;
  readonly answer_text: string | null;
  readonly rationale: string | null;
  readonly teacher_flags: readonly PlacementTeacherFlag[];
  readonly response: string | null;
  readonly is_correct: boolean | null;
  readonly change_count: number;
  readonly time_spent_ms: number | null;
  readonly audio_play_count: number;
}

export interface PlacementPriorAttempt {
  readonly attempt_id: string;
  readonly attempt_number: number;
  readonly state: string;
  readonly raw_score: number | null;
  readonly highest_sustained_band: number | null;
  readonly provisional_course: string | null;
  readonly confidence: string | null;
  readonly submitted_at: string | null;
}

export interface PlacementDecisionRecord {
  readonly action: string;
  readonly system_recommendation: string | null;
  readonly final_course: string | null;
  readonly reason_code: string | null;
  readonly reason_text: string | null;
  readonly created_at: string | null;
}

export interface PlacementEvidence {
  readonly attempt_id: string;
  readonly student_name: string | null;
  readonly student_email: string | null;
  readonly state: string;
  readonly form_code: string;
  readonly raw_score: number | null;
  readonly answered_count: number | null;
  readonly band_scores: Readonly<Record<string, number>> | null;
  readonly skill_scores: Readonly<
    Record<string, { correct: number; total: number }>
  > | null;
  readonly highest_sustained_band: number | null;
  readonly provisional_course: string | null;
  readonly lower_band_break: boolean | null;
  readonly clear_next_band_boundary: boolean | null;
  readonly confidence: string | null;
  readonly review_flags: readonly string[];
  readonly duration_seconds: number | null;
  readonly declared_band: number | null;
  readonly interruptions: readonly Record<string, unknown>[];
  readonly key_version: string | null;
  readonly rule_version: string | null;
  readonly responses: readonly PlacementReviewResponse[];
  readonly prior_attempts: readonly PlacementPriorAttempt[];
  readonly reviews: readonly PlacementDecisionRecord[];
  readonly evidence_hash: string;
}

export interface PlacementPreflightFinding {
  readonly code: string;
  readonly severity: string;
  readonly detail: string;
  readonly form_code: string | null;
  readonly question_number: number | null;
  readonly external_item_id: string | null;
}

export interface PlacementPreflight {
  readonly version_code: string;
  readonly status: string;
  readonly can_publish: boolean;
  readonly blocking_count: number;
  readonly findings: readonly PlacementPreflightFinding[];
}

export interface PlacementVersion {
  readonly id: string;
  readonly version_code: string;
  readonly status: string;
  readonly scoring_rule_version: string;
  readonly key_version: string;
  readonly max_attempts: number;
  readonly duration_minutes: number;
  readonly window_opens_at: string | null;
  readonly window_closes_at: string | null;
  readonly published_at: string | null;
  readonly form_count: number;
  readonly item_count: number;
}

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const placementKeys = {
  intro: () => ["placement-intro"] as const,
  attempts: () => ["placement-attempts"] as const,
  attempt: (id: string) => ["placement-attempt", id] as const,
  result: (id: string) => ["placement-result", id] as const,
  queue: () => ["placement-review-queue"] as const,
  evidence: (id: string) => ["placement-evidence", id] as const,
  versions: () => ["placement-versions"] as const,
  preflight: (id: string) => ["placement-preflight", id] as const,
};

/** Typed placement error codes the UI branches on. */
export type PlacementErrorCode =
  | "NO_PUBLISHED_VERSION"
  | "WINDOW_CLOSED"
  | "ATTEMPTS_EXHAUSTED"
  | "NO_ELIGIBLE_FORM"
  | "ATTEMPT_EXPIRED"
  | "ATTEMPT_NOT_EDITABLE"
  | "ATTEMPT_NOT_SUBMITTABLE"
  | "RELEASE_NOT_APPROVED"
  | "EVIDENCE_STALE"
  | "PREFLIGHT_FAILED";

const PLACEMENT_ERROR_CODES: readonly PlacementErrorCode[] = [
  "NO_PUBLISHED_VERSION",
  "WINDOW_CLOSED",
  "ATTEMPTS_EXHAUSTED",
  "NO_ELIGIBLE_FORM",
  "ATTEMPT_EXPIRED",
  "ATTEMPT_NOT_EDITABLE",
  "ATTEMPT_NOT_SUBMITTABLE",
  "RELEASE_NOT_APPROVED",
  "EVIDENCE_STALE",
  "PREFLIGHT_FAILED",
];

export function placementErrorCode(error: unknown): PlacementErrorCode | null {
  if (
    error instanceof ApiError &&
    error.code !== undefined &&
    (PLACEMENT_ERROR_CODES as readonly string[]).includes(error.code)
  ) {
    return error.code as PlacementErrorCode;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Student queries
// ---------------------------------------------------------------------------

export function usePlacementIntro() {
  return useAuthedQuery<PlacementIntro>({
    queryKey: placementKeys.intro(),
    path: "/placement",
    // A closed or unpublished test is a legitimate answer, not a transient
    // failure, so retrying would only delay the explanation the learner needs.
    retry: false,
  });
}

export function usePlacementAttempt(attemptId: string | null) {
  return useAuthedQuery<PlacementAttemptDetail>({
    queryKey: placementKeys.attempt(attemptId ?? ""),
    path: `/placement/attempts/${attemptId}`,
    enabled: Boolean(attemptId),
  });
}

export function usePlacementResult(attemptId: string | null) {
  return useAuthedQuery<PlacementResult>({
    queryKey: placementKeys.result(attemptId ?? ""),
    path: `/placement/attempts/${attemptId}/result`,
    enabled: Boolean(attemptId),
    // A result appears when CLE releases it, which the learner cannot trigger.
    // Polling is how the pending screen becomes the released screen without a
    // manual reload.
    refetchInterval: 30_000,
  });
}

export function useMyPlacementAttempts() {
  return useAuthedQuery<readonly PlacementAttempt[]>({
    queryKey: placementKeys.attempts(),
    path: "/placement/attempts",
    retry: false,
  });
}

// ---------------------------------------------------------------------------
// Student mutations
// ---------------------------------------------------------------------------

function useAuthedMutation() {
  const { getToken } = useAuth();
  return async function call<T>(path: string, init: RequestInit): Promise<T> {
    const token = await getToken({ template: "backend" });
    if (!token) throw new Error("Not authenticated");
    const response = await apiFetch<ApiEnvelope<T>>(path, { ...init, token });
    return response.data;
  };
}

export function useStartPlacementAttempt() {
  const call = useAuthedMutation();
  const queryClient = useQueryClient();
  return useMutation<
    PlacementAttempt,
    Error,
    { declared_band?: number | null } | void
  >({
    mutationFn: (input) =>
      call<PlacementAttempt>("/placement/attempts", {
        method: "POST",
        body: JSON.stringify(input ?? {}),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: placementKeys.intro() });
      queryClient.invalidateQueries({ queryKey: placementKeys.attempts() });
    },
  });
}

export type PlacementStep =
  | "confirm-eligibility"
  | "acknowledge-instructions"
  | "begin";

export function useAdvancePlacementAttempt(attemptId: string) {
  const call = useAuthedMutation();
  const queryClient = useQueryClient();
  return useMutation<PlacementAttempt, Error, PlacementStep>({
    mutationFn: (step) =>
      call<PlacementAttempt>(`/placement/attempts/${attemptId}/${step}`, {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: placementKeys.attempt(attemptId),
      });
    },
  });
}

export interface SaveResponseInput {
  readonly item_id: string;
  readonly response: string | null;
  readonly time_spent_ms?: number;
  readonly audio_play_count?: number;
}

export function useSavePlacementResponse(attemptId: string) {
  const call = useAuthedMutation();
  return useMutation<
    { item_id: string; response: string | null; change_count: number },
    Error,
    SaveResponseInput
  >({
    mutationFn: (input) =>
      call(`/placement/attempts/${attemptId}/responses`, {
        method: "PUT",
        body: JSON.stringify(input),
      }),
    // No cache invalidation: the answer sheet is client state during the
    // sitting, and refetching 30 items after every keystroke-equivalent would
    // fight the learner's own input.
  });
}

export function useReportInterruption(attemptId: string) {
  const call = useAuthedMutation();
  return useMutation<PlacementAttempt, Error, { kind: string; detail?: string }>(
    {
      mutationFn: (input) =>
        call<PlacementAttempt>(`/placement/attempts/${attemptId}/interruptions`, {
          method: "POST",
          body: JSON.stringify(input),
        }),
    }
  );
}

export function useSubmitPlacementAttempt(attemptId: string) {
  const call = useAuthedMutation();
  const queryClient = useQueryClient();
  return useMutation<PlacementResult, Error, void>({
    mutationFn: () =>
      call<PlacementResult>(`/placement/attempts/${attemptId}/submit`, {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: placementKeys.attempt(attemptId),
      });
      queryClient.invalidateQueries({ queryKey: placementKeys.attempts() });
    },
  });
}

// ---------------------------------------------------------------------------
// Review (instructor)
// ---------------------------------------------------------------------------

export function usePlacementQueue() {
  return useAuthedQuery<PlacementQueue>({
    queryKey: placementKeys.queue(),
    path: "/placement/review/queue",
  });
}

export function usePlacementEvidence(attemptId: string | null) {
  return useAuthedQuery<PlacementEvidence>({
    queryKey: placementKeys.evidence(attemptId ?? ""),
    path: `/placement/review/attempts/${attemptId}`,
    enabled: Boolean(attemptId),
  });
}

export interface PlacementDecisionInput {
  readonly action:
    | "approve"
    | "override"
    | "request_advising"
    | "invalidate"
    | "release";
  readonly final_course?: string | null;
  readonly reason_code?: string | null;
  readonly reason_text?: string | null;
  /** Echoed back so the server can refuse a decision made on stale evidence. */
  readonly evidence_hash?: string;
}

export function useRecordPlacementDecision(attemptId: string) {
  const call = useAuthedMutation();
  const queryClient = useQueryClient();
  return useMutation<
    { attempt_id: string; state: string; action: string; final_course: string | null },
    Error,
    PlacementDecisionInput
  >({
    mutationFn: (input) =>
      call(`/placement/review/attempts/${attemptId}/decision`, {
        method: "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: placementKeys.queue() });
      queryClient.invalidateQueries({
        queryKey: placementKeys.evidence(attemptId),
      });
    },
  });
}

export function usePlacementVersions() {
  return useAuthedQuery<readonly PlacementVersion[]>({
    queryKey: placementKeys.versions(),
    path: "/placement/versions",
  });
}

export function usePlacementPreflight(versionId: string | null) {
  return useAuthedQuery<PlacementPreflight>({
    queryKey: placementKeys.preflight(versionId ?? ""),
    path: `/placement/versions/${versionId}/preflight`,
    enabled: Boolean(versionId),
  });
}

export function usePublishPlacementVersion() {
  const call = useAuthedMutation();
  const queryClient = useQueryClient();
  return useMutation<PlacementVersion, Error, string>({
    mutationFn: (versionId) =>
      call<PlacementVersion>(`/placement/versions/${versionId}/publish`, {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: placementKeys.versions() });
    },
  });
}
