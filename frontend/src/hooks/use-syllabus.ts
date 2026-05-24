"use client";
import { useMutation } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";

interface SyllabusImportRef {
  readonly id: string;
}

export function useTriggerSyllabusImport(courseId: string) {
  const { getToken } = useAuth();
  return useMutation({
    mutationFn: async (documentId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<SyllabusImportRef>>(
        `/courses/${courseId}/syllabus/imports`,
        {
          token,
          method: "POST",
          body: JSON.stringify({ document_id: documentId }),
        }
      );
      return res.data;
    },
  });
}
