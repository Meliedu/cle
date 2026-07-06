"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/hooks/use-auth";
import { useAuthedQuery } from "@/hooks/use-authed-query";
import { apiFetch, type ApiEnvelope } from "@/lib/api";

/**
 * TanStack hooks over the existing `objectives.py` router
 * (`/courses/{id}/objectives`) plus the read-only concept-tag lookup
 * (`/concept-tags/objective/{id}`). The ILO-map step (T020) reuses these to
 * CRUD learning objectives and surface their concept links (read-only in P1).
 */

// ----- types (mirror backend `app/schemas/curriculum.py`) -----

export type BloomLevel =
  | "remember"
  | "understand"
  | "apply"
  | "analyze"
  | "evaluate"
  | "create";

export const BLOOM_LEVELS: readonly BloomLevel[] = [
  "remember",
  "understand",
  "apply",
  "analyze",
  "evaluate",
  "create",
];

/** Mirrors `LearningObjectiveResponse`. */
export interface Objective {
  readonly id: string;
  readonly course_id: string;
  readonly module_id: string | null;
  readonly meeting_id: string | null;
  readonly statement: string;
  readonly bloom_level: BloomLevel | null;
  readonly order_index: number;
  readonly created_at: string;
  readonly updated_at: string;
}

/** Mirrors `LearningObjectiveCreate`. */
export interface ObjectiveCreate {
  readonly statement: string;
  readonly bloom_level?: BloomLevel | null;
  readonly order_index?: number;
}

/** Mirrors `LearningObjectiveUpdate` (all fields optional). */
export type ObjectiveUpdate = Partial<ObjectiveCreate>;

/** Minimal concept shape used for read-only ILO source chips. */
export interface ConceptLink {
  readonly id: string;
  readonly name: string;
}

export const objectiveKeys = {
  list: (courseId: string) => ["objectives", courseId] as const,
  concepts: (objectiveId: string) =>
    ["objective-concepts", objectiveId] as const,
};

/** GET `/courses/{id}/objectives` — every ILO for the course, by order. */
export function useObjectives(courseId: string) {
  return useAuthedQuery<readonly Objective[]>({
    queryKey: objectiveKeys.list(courseId),
    path: `/courses/${courseId}/objectives`,
    enabled: Boolean(courseId),
  });
}

/**
 * GET `/concept-tags/objective/{objectiveId}` — concepts tagged on one ILO.
 * Read-only in P1: the wizard surfaces the AI-inferred concept links but does
 * not let the teacher edit them here.
 */
export function useObjectiveConcepts(objectiveId: string, enabled = true) {
  return useAuthedQuery<readonly ConceptLink[]>({
    queryKey: objectiveKeys.concepts(objectiveId),
    path: `/concept-tags/objective/${objectiveId}`,
    enabled: enabled && Boolean(objectiveId),
  });
}

/** POST `/courses/{id}/objectives` — add an ILO. */
export function useCreateObjective(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation<Objective, Error, ObjectiveCreate>({
    mutationFn: async (body) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<Objective>>(
        `/courses/${courseId}/objectives`,
        { method: "POST", token, body: JSON.stringify(body) }
      );
      return res.data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: objectiveKeys.list(courseId) });
    },
  });
}

interface UpdateObjectiveInput {
  readonly objectiveId: string;
  readonly patch: ObjectiveUpdate;
}

/** PUT `/courses/{id}/objectives/{objectiveId}` — edit an ILO. */
export function useUpdateObjective(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation<Objective, Error, UpdateObjectiveInput>({
    mutationFn: async ({ objectiveId, patch }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<Objective>>(
        `/courses/${courseId}/objectives/${objectiveId}`,
        { method: "PUT", token, body: JSON.stringify(patch) }
      );
      return res.data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: objectiveKeys.list(courseId) });
    },
  });
}

/** DELETE `/courses/{id}/objectives/{objectiveId}` — soft-delete an ILO. */
export function useDeleteObjective(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation<void, Error, string>({
    mutationFn: async (objectiveId) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await apiFetch<ApiEnvelope<null>>(
        `/courses/${courseId}/objectives/${objectiveId}`,
        { method: "DELETE", token }
      );
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: objectiveKeys.list(courseId) });
    },
  });
}
