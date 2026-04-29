"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type { Concept } from "@/lib/concept-types";

export function useConcepts(courseId: string) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["concepts", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<Concept[]>>(
        `/courses/${courseId}/concepts`,
        { token }
      );
      return res.data;
    },
  });
}

export function useCreateConcept(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { name: string; description?: string }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<Concept>>(
        `/courses/${courseId}/concepts`,
        {
          token,
          method: "POST",
          body: JSON.stringify({ ...body, instructor_curated: true }),
        }
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["concepts", courseId] });
      qc.invalidateQueries({ queryKey: ["concept-clusters", courseId] });
    },
  });
}

export function useUpdateConcept(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: {
      conceptId: string;
      patch: Partial<Concept>;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<Concept>>(
        `/courses/${courseId}/concepts/${vars.conceptId}`,
        { token, method: "PUT", body: JSON.stringify(vars.patch) }
      );
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["concepts", courseId] }),
  });
}

export function useDeleteConcept(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (conceptId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await apiFetch<ApiEnvelope<null>>(
        `/courses/${courseId}/concepts/${conceptId}`,
        { token, method: "DELETE" }
      );
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["concepts", courseId] }),
  });
}
