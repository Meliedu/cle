"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/hooks/use-auth";
import { useAuthedQuery } from "@/hooks/use-authed-query";
import { usePollWindow } from "@/hooks/use-setup";
import { apiFetch, type ApiEnvelope } from "@/lib/api";

/**
 * TanStack hooks over the checkpoints router (backend Task 9). Checkpoints are
 * DRAFT-only in P1 (Decision 3): the teacher reviews generated draft cards,
 * lightly edits a review-point prompt, or removes a card with a reason. Query
 * keys are namespaced under `["checkpoints", courseId]` (list) and
 * `["checkpoint", checkpointId]` (detail with cards).
 */

// ----- types (mirror backend `app/schemas/checkpoint.py`) -----

export type CheckpointStatus =
  | "draft"
  | "teacher_editing"
  | "approved"
  | "scheduled"
  | "published"
  | "closed"
  | "archived";

export type CardKind = "review_point" | "final_comments";

export type RemovedReason = "not_needed" | "duplicate" | "not_covered" | "other";

/** Mirrors `CheckpointResponse`. */
export interface Checkpoint {
  readonly id: string;
  readonly course_id: string;
  readonly meeting_id: string | null;
  readonly kind: string;
  readonly status: CheckpointStatus;
  readonly title: string;
  readonly qr_enabled: boolean;
  readonly generation_meta: Record<string, unknown> | null;
  readonly created_at: string;
  readonly updated_at: string;
}

/** Mirrors `CheckpointCardResponse`. */
export interface CheckpointCard {
  readonly id: string;
  readonly checkpoint_id: string;
  readonly position: number;
  readonly kind: CardKind;
  readonly prompt: string;
  readonly document_id: string | null;
  readonly chunk_id: string | null;
  readonly objective_id: string | null;
  readonly removed: boolean;
  readonly removed_reason: RemovedReason | null;
  readonly removed_note: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

/** Mirrors `CheckpointWithCardsResponse`. */
export interface CheckpointWithCards extends Checkpoint {
  readonly cards: readonly CheckpointCard[];
}

export const checkpointKeys = {
  list: (courseId: string) => ["checkpoints", courseId] as const,
  detail: (checkpointId: string) => ["checkpoint", checkpointId] as const,
};

const LIST_POLL_INTERVAL_MS = 3000;

// ----- queries -----

/**
 * GET `/courses/{id}/checkpoints` — every draft checkpoint for the course. When
 * `poll` is set, refetches every few seconds until at least one checkpoint
 * appears, so the async `generate_checkpoints` job's output shows up without a
 * manual refresh.
 */
export function useCheckpoints(
  courseId: string,
  options: { poll?: boolean; pollKey?: number } = {}
) {
  const { poll = false, pollKey = 0 } = options;
  const { expired, windowRef } = usePollWindow(poll, pollKey);
  const query = useAuthedQuery<readonly Checkpoint[]>({
    queryKey: checkpointKeys.list(courseId),
    path: `/courses/${courseId}/checkpoints`,
    enabled: Boolean(courseId),
    refetchInterval: (q) => {
      if (!poll) return false;
      if ((q.state.data?.length ?? 0) > 0) return false;
      if (!windowRef.current) return false;
      return LIST_POLL_INTERVAL_MS;
    },
  });
  const timedOut = poll && (query.data?.length ?? 0) === 0 && expired;
  return { ...query, timedOut };
}

/** GET `/checkpoints/{id}` — a single checkpoint with its ordered cards. */
export function useCheckpoint(checkpointId: string | null) {
  return useAuthedQuery<CheckpointWithCards>({
    queryKey: checkpointKeys.detail(checkpointId ?? ""),
    path: `/checkpoints/${checkpointId}`,
    enabled: Boolean(checkpointId),
  });
}

// ----- mutations -----

interface UpdateCardInput {
  readonly cardId: string;
  readonly prompt?: string;
  readonly removed?: boolean;
  readonly removedReason?: RemovedReason;
  readonly removedNote?: string | null;
}

/**
 * PATCH `/checkpoints/{id}/cards/{cardId}` — edit a review-point prompt or
 * soft-remove a card with a categorized reason. The backend enforces
 * `FINAL_CARD_FIXED` (final card is never removable) and `REVIEW_REQUIRED`
 * (only draft checkpoints are editable); callers surface those typed codes.
 * Invalidates both the checkpoint detail and the course list on success.
 */
export function useUpdateCheckpointCard(courseId: string, checkpointId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation<CheckpointCard, Error, UpdateCardInput>({
    mutationFn: async ({ cardId, prompt, removed, removedReason, removedNote }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const body: Record<string, unknown> = {};
      if (prompt !== undefined) body.prompt = prompt;
      if (removed !== undefined) body.removed = removed;
      if (removedReason !== undefined) body.removed_reason = removedReason;
      if (removedNote !== undefined) body.removed_note = removedNote;
      const res = await apiFetch<ApiEnvelope<CheckpointCard>>(
        `/checkpoints/${checkpointId}/cards/${cardId}`,
        { method: "PATCH", token, body: JSON.stringify(body) }
      );
      return res.data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: checkpointKeys.detail(checkpointId),
      });
      void queryClient.invalidateQueries({
        queryKey: checkpointKeys.list(courseId),
      });
    },
  });
}
