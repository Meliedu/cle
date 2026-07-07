"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/hooks/use-auth";
import { useAuthedQuery } from "@/hooks/use-authed-query";
import { apiFetch, type ApiEnvelope } from "@/lib/api";

/**
 * TanStack hooks over the checklist / work-item spine (P4 backend B6). The
 * spine is the single source of truth for "what a student must do next": the
 * student read (`useChecklist`/`useNextAction`) merges course work_items with
 * the caller's own `work_item_progress`; the teacher manager
 * (`useWorkItems` + add/update/remove) authors course-scoped work_items with no
 * per-student progress. Mirrors the `use-checkpoints.ts` shape — query-key
 * factory, `useAuthedQuery` for reads, `authedWrite` for mutations.
 */

// ----- types (mirror backend `app/schemas/work_item.py`) -----

/** Mirrors the `work_items.source_kind` CHECK (spec §4.6). */
export type WorkItemSourceKind =
  | "checkpoint"
  | "practice"
  | "quiz"
  | "activity"
  | "material"
  | "follow_up"
  | "report";

/** Mirrors the `work_item_progress.status` CHECK (spec §4.6). */
export type WorkItemStatus =
  | "pending"
  | "in_progress"
  | "submitted"
  | "late"
  | "missed"
  | "completed"
  | "follow_up_assigned";

/**
 * Mirrors `ChecklistItem` — a course work_item merged with the caller's own
 * derived `work_item_progress.status` (the student-facing spine read).
 */
export interface ChecklistItem {
  readonly id: string;
  readonly course_id: string;
  readonly source_kind: WorkItemSourceKind;
  readonly source_id: string | null;
  readonly title: string;
  readonly required: boolean;
  readonly score_bearing: boolean;
  readonly due_at: string | null;
  readonly close_at: string | null;
  readonly visible_from: string | null;
  readonly status: WorkItemStatus;
}

/**
 * Mirrors `WorkItemResponse` — the teacher-authored course work_item with no
 * per-student progress overlay.
 */
export interface WorkItemResponse {
  readonly id: string;
  readonly course_id: string;
  readonly source_kind: WorkItemSourceKind;
  readonly source_id: string | null;
  readonly title: string;
  readonly required: boolean;
  readonly score_bearing: boolean;
  readonly due_at: string | null;
  readonly close_at: string | null;
  readonly visible_from: string | null;
  readonly created_by: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export const workItemKeys = {
  checklist: (courseId: string) => ["checklist", courseId] as const,
  nextAction: (courseId: string) => ["next-action", courseId] as const,
  workItems: (courseId: string) => ["work-items", courseId] as const,
};

// ----- shared mutation body -----

/**
 * JSON POST/PATCH/DELETE that unwraps the standard envelope. Fetches a fresh
 * backend JWT, throws on a missing token, and returns `data` (which may be
 * `null` for a DELETE). Mirrors `use-checkpoints.ts::authedWrite`.
 */
async function authedWrite<T>(
  getToken: (opts: { template: string }) => Promise<string | null>,
  path: string,
  method: "POST" | "PATCH" | "DELETE",
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

// ----- student reads (spine) -----

/**
 * GET `/courses/{id}/checklist` — the course's non-deleted work_items merged
 * with the caller's own `work_item_progress`, ordered by `due_at` then
 * `visible_from` (backend B6). Enrollment-scoped; a non-enrolled caller 403s.
 */
export function useChecklist(courseId: string) {
  return useAuthedQuery<readonly ChecklistItem[]>({
    queryKey: workItemKeys.checklist(courseId),
    path: `/courses/${courseId}/checklist`,
    enabled: Boolean(courseId),
  });
}

/**
 * GET `/courses/{id}/next-action` — the single next `pending`/`in_progress`
 * item by `due_at`, or `null` when the checklist is clear (Decision 7). Feeds
 * the dashboard next-action slot.
 */
export function useNextAction(courseId: string) {
  return useAuthedQuery<ChecklistItem | null>({
    queryKey: workItemKeys.nextAction(courseId),
    path: `/courses/${courseId}/next-action`,
    enabled: Boolean(courseId),
  });
}

// ----- teacher manager -----

/** GET `/courses/{id}/work-items` — the owner's course work_items (no progress). */
export function useWorkItems(courseId: string) {
  return useAuthedQuery<readonly WorkItemResponse[]>({
    queryKey: workItemKeys.workItems(courseId),
    path: `/courses/${courseId}/work-items`,
    enabled: Boolean(courseId),
  });
}

/** Body for a manual `POST /courses/{id}/work-items` add. */
export interface AddWorkItemInput {
  readonly title: string;
  readonly source_kind?: WorkItemSourceKind;
  readonly required?: boolean;
  readonly score_bearing?: boolean;
  readonly due_at?: string | null;
  readonly close_at?: string | null;
  readonly visible_from?: string | null;
}

/** Body subset for a `PATCH /work-items/{id}` edit. */
export interface UpdateWorkItemInput {
  readonly workItemId: string;
  readonly title?: string;
  readonly required?: boolean;
  readonly score_bearing?: boolean;
  readonly due_at?: string | null;
  readonly close_at?: string | null;
  readonly visible_from?: string | null;
}

/**
 * Invalidate every surface that reads the spine for a course — the teacher
 * manager list plus the student checklist / next-action reads — so an add,
 * edit, or removal refreshes without a manual refetch.
 */
function invalidateWorkItems(
  queryClient: ReturnType<typeof useQueryClient>,
  courseId: string
): void {
  void queryClient.invalidateQueries({
    queryKey: workItemKeys.workItems(courseId),
  });
  void queryClient.invalidateQueries({
    queryKey: workItemKeys.checklist(courseId),
  });
  void queryClient.invalidateQueries({
    queryKey: workItemKeys.nextAction(courseId),
  });
}

/**
 * POST `/courses/{id}/work-items` — manually add a course work_item. Defaults
 * `source_kind` to `"material"` (the only manual source in P4). Invalidates the
 * course spine on success.
 */
export function useAddWorkItem(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation<WorkItemResponse, Error, AddWorkItemInput>({
    mutationFn: (body) =>
      authedWrite<WorkItemResponse>(
        getToken,
        `/courses/${courseId}/work-items`,
        "POST",
        body
      ),
    onSuccess: () => invalidateWorkItems(queryClient, courseId),
  });
}

/**
 * PATCH `/work-items/{id}` — edit a work_item's title / required / score-bearing
 * flags or scheduling window. Only the supplied fields are sent. Invalidates
 * the course spine on success.
 */
export function useUpdateWorkItem(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation<WorkItemResponse, Error, UpdateWorkItemInput>({
    mutationFn: ({ workItemId, ...rest }) => {
      const body: Record<string, unknown> = {};
      if (rest.title !== undefined) body.title = rest.title;
      if (rest.required !== undefined) body.required = rest.required;
      if (rest.score_bearing !== undefined)
        body.score_bearing = rest.score_bearing;
      if (rest.due_at !== undefined) body.due_at = rest.due_at;
      if (rest.close_at !== undefined) body.close_at = rest.close_at;
      if (rest.visible_from !== undefined) body.visible_from = rest.visible_from;
      return authedWrite<WorkItemResponse>(
        getToken,
        `/work-items/${workItemId}`,
        "PATCH",
        body
      );
    },
    onSuccess: () => invalidateWorkItems(queryClient, courseId),
  });
}

/** DELETE `/work-items/{id}` — soft-remove a work_item. Invalidates the spine. */
export function useRemoveWorkItem(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation<null, Error, string>({
    mutationFn: (workItemId) =>
      authedWrite<null>(getToken, `/work-items/${workItemId}`, "DELETE"),
    onSuccess: () => invalidateWorkItems(queryClient, courseId),
  });
}
