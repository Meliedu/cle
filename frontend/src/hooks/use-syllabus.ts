"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type { SyllabusImport } from "@/lib/curriculum-types";

export function useSyllabusImports(courseId: string) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["syllabus-imports", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<SyllabusImport[]>>(
        `/courses/${courseId}/syllabus/imports`,
        { token }
      );
      return res.data;
    },
    refetchInterval: (q) => {
      const data = q.state.data;
      if (data && data.some((i) => i.status === "pending")) return 3000;
      return false;
    },
  });
}

export function useTriggerSyllabusImport(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (documentId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<SyllabusImport>>(
        `/courses/${courseId}/syllabus/imports`,
        {
          token,
          method: "POST",
          body: JSON.stringify({ document_id: documentId }),
        }
      );
      return res.data;
    },
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["syllabus-imports", courseId] }),
  });
}

export function useApplySyllabusImport(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: {
      importId: string;
      payload: Record<string, unknown>;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<SyllabusImport>>(
        `/courses/${courseId}/syllabus/imports/${vars.importId}/apply`,
        {
          token,
          method: "POST",
          body: JSON.stringify({ parsed_payload: vars.payload }),
        }
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["syllabus-imports", courseId] });
      qc.invalidateQueries({ queryKey: ["modules", courseId] });
      qc.invalidateQueries({ queryKey: ["meetings", courseId] });
      qc.invalidateQueries({ queryKey: ["objectives", courseId] });
      qc.invalidateQueries({ queryKey: ["assignments", courseId] });
    },
  });
}
