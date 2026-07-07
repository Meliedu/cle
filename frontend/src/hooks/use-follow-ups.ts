"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/hooks/use-auth";
import { useAuthedQuery } from "@/hooks/use-authed-query";
import { apiFetch, type ApiEnvelope } from "@/lib/api";

/**
 * TanStack hooks over the student follow-up surface (backend `api/review.py`,
 * P6 B3). A reviewed `learning_note` may spawn a `FollowUpAction` the student
 * works through: list the active ones, open one for its reviewed detail, and
 * mark it viewed. Mirrors the `use-work-items.ts` shape — a query-key factory,
 * `useAuthedQuery` for reads, `authedWrite` for the one mutation.
 *
 * The follow-up→checklist spine seam (B1) and its completion sync (B2) are
 * server-side; this hook file only reads the student-facing follow-up rows.
 */

// ----- types (mirror backend `app/schemas/evidence.py`) -----

/** Mirrors the `follow_up_actions.assignment_status` CHECK. */
export type AssignmentStatus =
  | "suggested"
  | "assigned"
  | "viewed"
  | "completed"
  | "checked"
  | "closed"
  | "carried_forward";

/** Mirrors the `outcome_checks.status` CHECK (the "did it move" state). */
export type OutcomeStatus =
  | "pending"
  | "completed"
  | "improved"
  | "persistent"
  | "resolved"
  | "needs_review"
  | "carried_forward";

/**
 * Mirrors `FollowUpActionResponse` — a follow-up summary row (the list item and
 * the mark-viewed echo). No linked-note content here; that lands on the detail.
 */
export interface FollowUpAction {
  readonly id: string;
  readonly learning_note_id: string | null;
  readonly course_id: string;
  readonly user_id: string;
  readonly action_type: string;
  readonly target_kind: string | null;
  readonly target_id: string | null;
  readonly assignment_status: AssignmentStatus;
  readonly due_at: string | null;
  readonly assigned_by: string | null;
  readonly created_at: string;
}

/**
 * Mirrors `FollowUpRevisitLink` — the route into the P3 checkpoint revisit flow
 * for a `checkpoint`-targeted follow-up (a link only, no new revisit engine).
 */
export interface FollowUpRevisitLink {
  readonly checkpoint_id: string;
  readonly revisit_path: string;
}

/**
 * Mirrors `FollowUpDetailResponse` — the follow-up merged with its linked note's
 * **reviewed** fields ONLY. `waiting_for_review=true` is the designed
 * waiting-for-instructor-feedback state: a `suggested` follow-up (or one whose
 * note is not yet reviewed) carries no `observed_signal`/`draft_interpretation`/
 * `limitation_note` (Core §0.2 / Decision 6).
 */
export interface FollowUpDetail {
  readonly id: string;
  readonly course_id: string;
  readonly learning_note_id: string | null;
  readonly action_type: string;
  readonly target_kind: string | null;
  readonly target_id: string | null;
  readonly assignment_status: AssignmentStatus;
  readonly due_at: string | null;
  readonly created_at: string;
  readonly waiting_for_review: boolean;
  readonly observed_signal?: string | null;
  readonly draft_interpretation?: string | null;
  readonly limitation_note?: string | null;
  readonly outcome_status?: OutcomeStatus | null;
  readonly revisit: FollowUpRevisitLink | null;
}

export const followUpKeys = {
  list: (courseId: string) => ["follow-ups", courseId] as const,
  detail: (followUpId: string) => ["follow-up", followUpId] as const,
};

// ----- shared mutation body -----

/**
 * JSON POST that unwraps the standard envelope. Fetches a fresh backend JWT,
 * throws on a missing token, and returns `data`. Mirrors
 * `use-work-items.ts::authedWrite`.
 */
async function authedWrite<T>(
  getToken: (opts: { template: string }) => Promise<string | null>,
  path: string,
  method: "POST",
  body?: unknown
): Promise<T> {
  const token = await getToken({ template: "backend" });
  if (!token) throw new Error("Not authenticated");
  const res = await apiFetch<ApiEnvelope<T>>(path, {
    method,
    token,
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
  return res.data;
}

// ----- student reads -----

/**
 * GET `/users/me/courses/{id}/follow-ups` — the caller's active follow-ups
 * (`assigned`/`viewed`) in a course, newest first. Enrollment-scoped.
 */
export function useMyFollowUps(courseId: string) {
  return useAuthedQuery<readonly FollowUpAction[]>({
    queryKey: followUpKeys.list(courseId),
    path: `/users/me/courses/${courseId}/follow-ups`,
    enabled: Boolean(courseId),
  });
}

/**
 * GET `/users/me/follow-ups/{id}` — one follow-up's detail merged with its
 * linked note's reviewed fields (owner-scoped; 404 for another student's row).
 */
export function useFollowUpDetail(followUpId: string | null) {
  return useAuthedQuery<FollowUpDetail>({
    queryKey: followUpKeys.detail(followUpId ?? ""),
    path: `/users/me/follow-ups/${followUpId}`,
    enabled: Boolean(followUpId),
  });
}

// ----- mutation -----

/**
 * POST `/follow-ups/{id}/viewed` — mark a follow-up viewed (`assigned` →
 * `viewed`). Invalidates the follow-up detail + the course list so the status
 * chip refreshes without a manual refetch.
 */
export function useMarkFollowUpViewed() {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation<FollowUpAction, Error, string>({
    mutationFn: (followUpId) =>
      authedWrite<FollowUpAction>(
        getToken,
        `/follow-ups/${followUpId}/viewed`,
        "POST"
      ),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({
        queryKey: followUpKeys.detail(data.id),
      });
      void queryClient.invalidateQueries({
        queryKey: followUpKeys.list(data.course_id),
      });
    },
  });
}
