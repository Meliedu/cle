"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type { AssignmentSubmission } from "@/lib/curriculum-types";

export function useSubmissions(courseId: string, assignmentId: string) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["submissions", assignmentId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<AssignmentSubmission[]>>(
        `/courses/${courseId}/assignments/${assignmentId}/submissions`,
        { token }
      );
      return res.data;
    },
  });
}

export function useUpsertMySubmission(courseId: string, assignmentId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: {
      status: "in_progress" | "submitted";
      submission_payload?: Record<string, unknown>;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<AssignmentSubmission>>(
        `/courses/${courseId}/assignments/${assignmentId}/submission`,
        { token, method: "POST", body: JSON.stringify(body) }
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["submissions", assignmentId] });
      qc.invalidateQueries({ queryKey: ["assignments", courseId] });
    },
  });
}

export function useGradeSubmission(courseId: string, assignmentId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: {
      submissionId: string;
      score: string;
      feedback?: string;
      status?: "graded" | "excused";
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const { submissionId, ...rest } = vars;
      const res = await apiFetch<ApiEnvelope<AssignmentSubmission>>(
        `/courses/${courseId}/assignments/${assignmentId}/submissions/${submissionId}/grade`,
        { token, method: "POST", body: JSON.stringify(rest) }
      );
      return res.data;
    },
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["submissions", assignmentId] }),
  });
}
