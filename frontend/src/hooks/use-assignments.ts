"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type { Assignment, AssignmentKind } from "@/lib/curriculum-types";

export function useAssignments(courseId: string) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["assignments", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<Assignment[]>>(
        `/courses/${courseId}/assignments`,
        { token }
      );
      return res.data;
    },
  });
}

export function useCreateAssignment(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: {
      title: string;
      kind: AssignmentKind;
      due_at: string;
      description?: string;
      weight?: string;
      module_id?: string;
      meeting_id?: string;
      available_from?: string;
      quiz_id?: string;
      is_published?: boolean;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<Assignment>>(
        `/courses/${courseId}/assignments`,
        { token, method: "POST", body: JSON.stringify(body) }
      );
      return res.data;
    },
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["assignments", courseId] }),
  });
}

export function useUpdateAssignment(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: {
      assignmentId: string;
      patch: Partial<Assignment>;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<Assignment>>(
        `/courses/${courseId}/assignments/${vars.assignmentId}`,
        { token, method: "PUT", body: JSON.stringify(vars.patch) }
      );
      return res.data;
    },
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["assignments", courseId] }),
  });
}

export function useDeleteAssignment(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (assignmentId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await apiFetch<ApiEnvelope<null>>(
        `/courses/${courseId}/assignments/${assignmentId}`,
        { token, method: "DELETE" }
      );
    },
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["assignments", courseId] }),
  });
}
