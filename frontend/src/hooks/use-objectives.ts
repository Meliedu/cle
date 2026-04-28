"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type { BloomLevel, LearningObjective } from "@/lib/curriculum-types";

export function useObjectives(courseId: string) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["objectives", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<LearningObjective[]>>(
        `/courses/${courseId}/objectives`,
        { token }
      );
      return res.data;
    },
  });
}

export function useCreateObjective(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: {
      statement: string;
      bloom_level?: BloomLevel;
      module_id?: string;
      meeting_id?: string;
      order_index?: number;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<LearningObjective>>(
        `/courses/${courseId}/objectives`,
        { token, method: "POST", body: JSON.stringify(body) }
      );
      return res.data;
    },
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["objectives", courseId] }),
  });
}

export function useUpdateObjective(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: {
      objectiveId: string;
      patch: Partial<LearningObjective>;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<LearningObjective>>(
        `/courses/${courseId}/objectives/${vars.objectiveId}`,
        { token, method: "PUT", body: JSON.stringify(vars.patch) }
      );
      return res.data;
    },
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["objectives", courseId] }),
  });
}

export function useDeleteObjective(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (objectiveId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await apiFetch<ApiEnvelope<null>>(
        `/courses/${courseId}/objectives/${objectiveId}`,
        { token, method: "DELETE" }
      );
    },
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["objectives", courseId] }),
  });
}
