"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/hooks/use-auth";
import { useAuthedQuery } from "@/hooks/use-authed-query";
import { apiFetch, type ApiEnvelope } from "@/lib/api";

/**
 * TanStack hooks over the P7 course-memory router (`app/api/memory.py`, backend
 * B8–B9). Course memory reshapes `course_record_items` (reviewed instructor
 * summaries) and lets the owner decide each one (`keep|revise|reject|
 * carry_forward`). Carry-forward items feed the NEXT term's setup — course-bound
 * only, never cross-course student profiling (spec §5.6): no student `user_id`
 * ever crosses terms, only the instructor-authored summaries. Owner-scoped
 * throughout (`/courses/{id}/memory`, `/memory/{id}`). Mirrors the
 * `use-work-items.ts` shape — a query-key factory, `useAuthedQuery` for reads,
 * `authedWrite` for mutations that invalidate the course memory reads.
 */

// ----- types (mirror backend `app/schemas/memory.py`) -----

/** Which summary the record item centres on (derived from populated JSONBs). */
export type MemoryKind = "outcome" | "action" | "relationship" | "general";

/** Mirrors the `course_record_items.decision` CHECK (B8). `null` = undecided. */
export type MemoryDecision = "keep" | "revise" | "reject" | "carry_forward";

/** Mirrors `MemoryItemResponse` — one course-record item (reshaped). */
export interface MemoryItemResponse {
  readonly id: string;
  readonly course_id: string;
  readonly learning_note_id: string | null;
  readonly kind: MemoryKind;
  readonly relationship_summary: Record<string, unknown> | null;
  readonly action_summary: Record<string, unknown> | null;
  readonly outcome_summary: Record<string, unknown> | null;
  readonly instructor_comment: string | null;
  readonly carry_forward: boolean;
  readonly decision: MemoryDecision | null;
  readonly decided_by: string | null;
  readonly decided_at: string | null;
  readonly report_history: readonly Record<string, unknown>[];
  readonly created_at: string;
}

/**
 * A next-term suggestion — a `carry_forward` item from a prior-term course of
 * the SAME code lineage + instructor, tagged with its source course (no student
 * identity crosses terms).
 */
export interface NextTermSuggestion extends MemoryItemResponse {
  readonly source_course_id: string;
  readonly source_course_code: string;
  readonly source_course_name: string;
}

/** Counts-by-decision for the teacher memory summary (T036). */
export interface MemoryDecisionCounts {
  readonly keep: number;
  readonly revise: number;
  readonly reject: number;
  readonly carry_forward: number;
  readonly undecided: number;
}

/** Mirrors the memory summary (`GET /courses/{id}/memory/summary`). */
export interface MemorySummary {
  readonly total: number;
  readonly counts: MemoryDecisionCounts;
  readonly carry_forward_roster: readonly MemoryItemResponse[];
}

/** Result of `POST /courses/{id}/setup/import-memory`. */
export interface ImportMemoryResult {
  readonly imported_count: number;
  readonly imported_item_ids: readonly string[];
}

export const memoryKeys = {
  list: (courseId: string) => ["memory", "list", courseId] as const,
  detail: (itemId: string) => ["memory", "detail", itemId] as const,
  nextTerm: (courseId: string) =>
    ["memory", "next-term", courseId] as const,
  summary: (courseId: string) => ["memory", "summary", courseId] as const,
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

// ----- teacher reads (owner-scoped) -----

/**
 * GET `/courses/{id}/memory` — the course's record items, `created_at DESC`
 * (backend B8). Owner-scoped; 404 on a non-owner course.
 */
export function useMemory(courseId: string) {
  return useAuthedQuery<readonly MemoryItemResponse[]>({
    queryKey: memoryKeys.list(courseId),
    path: `/courses/${courseId}/memory`,
    enabled: Boolean(courseId),
  });
}

/**
 * GET `/memory/{id}` — one record-item detail. The backend re-derives the
 * course and re-applies the owner guard (404 on mismatch).
 */
export function useMemoryItem(itemId: string | null) {
  return useAuthedQuery<MemoryItemResponse>({
    queryKey: memoryKeys.detail(itemId ?? ""),
    path: `/memory/${itemId}`,
    enabled: Boolean(itemId),
  });
}

/**
 * GET `/courses/{id}/memory/next-term-suggestions` — `carry_forward` items from
 * the same course-code lineage + instructor, each tagged with its source course
 * (backend B9). Feeds the prior-term memory import picker.
 */
export function useNextTermSuggestions(courseId: string) {
  return useAuthedQuery<readonly NextTermSuggestion[]>({
    queryKey: memoryKeys.nextTerm(courseId),
    path: `/courses/${courseId}/memory/next-term-suggestions`,
    enabled: Boolean(courseId),
  });
}

/**
 * GET `/courses/{id}/memory/summary` — counts-by-decision + the carry-forward
 * roster for the teacher overview (T036).
 */
export function useMemorySummary(courseId: string) {
  return useAuthedQuery<MemorySummary>({
    queryKey: memoryKeys.summary(courseId),
    path: `/courses/${courseId}/memory/summary`,
    enabled: Boolean(courseId),
  });
}

// ----- teacher mutations -----

/** Invalidate every read that surfaces a course's memory after a decision/import. */
function invalidateMemory(
  queryClient: ReturnType<typeof useQueryClient>,
  courseId: string,
  itemId?: string
): void {
  void queryClient.invalidateQueries({ queryKey: memoryKeys.list(courseId) });
  void queryClient.invalidateQueries({
    queryKey: memoryKeys.summary(courseId),
  });
  void queryClient.invalidateQueries({
    queryKey: memoryKeys.nextTerm(courseId),
  });
  if (itemId) {
    void queryClient.invalidateQueries({
      queryKey: memoryKeys.detail(itemId),
    });
  }
}

/** Variables for a `POST /memory/{id}/decide`. */
export interface DecideMemoryInput {
  readonly itemId: string;
  readonly decision: MemoryDecision;
}

/**
 * POST `/memory/{id}/decide` — record a `keep|revise|reject|carry_forward`
 * decision (syncs the `carry_forward` bool, writes an `audit_events` row, and a
 * `review_action` when the item is note-linked). 422 on an invalid decision.
 */
export function useDecideMemory(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation<MemoryItemResponse, Error, DecideMemoryInput>({
    mutationFn: ({ itemId, decision }) =>
      authedWrite<MemoryItemResponse>(
        getToken,
        `/memory/${itemId}/decide`,
        "POST",
        { decision }
      ),
    onSuccess: (item) => invalidateMemory(queryClient, courseId, item.id),
  });
}

/** Variables for a `POST /courses/{id}/setup/import-memory`. */
export interface ImportMemoryInput {
  readonly item_ids: readonly string[];
}

/**
 * POST `/courses/{id}/setup/import-memory` — thread accepted `carry_forward`
 * items' summaries into this course's checkpoint-generation grounding. Refuses
 * an undecided/`reject` item with 409 `MEMORY_UNDECIDED`.
 */
export function useImportMemory(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation<ImportMemoryResult, Error, ImportMemoryInput>({
    mutationFn: (body) =>
      authedWrite<ImportMemoryResult>(
        getToken,
        `/courses/${courseId}/setup/import-memory`,
        "POST",
        body
      ),
    onSuccess: () => invalidateMemory(queryClient, courseId),
  });
}
