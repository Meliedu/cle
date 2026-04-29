"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type { ConceptPrerequisite } from "@/lib/concept-types";

export function useConceptPrerequisites(courseId: string) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["concept-prerequisites", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<ConceptPrerequisite[]>>(
        `/courses/${courseId}/concept-prerequisites`,
        { token }
      );
      return res.data;
    },
  });
}

export function useCreatePrerequisite(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: {
      prereq_concept_id: string;
      dependent_concept_id: string;
      strength: string;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<ConceptPrerequisite>>(
        `/courses/${courseId}/concept-prerequisites`,
        { token, method: "POST", body: JSON.stringify(body) }
      );
      return res.data;
    },
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["concept-prerequisites", courseId] }),
  });
}

export function useDeletePrerequisite(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { prereqId: string; dependentId: string }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await apiFetch<ApiEnvelope<null>>(
        `/courses/${courseId}/concept-prerequisites/${vars.prereqId}/${vars.dependentId}`,
        { token, method: "DELETE" }
      );
    },
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["concept-prerequisites", courseId] }),
  });
}
