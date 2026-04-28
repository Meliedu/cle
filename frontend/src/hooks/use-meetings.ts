"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type { CourseMeeting } from "@/lib/curriculum-types";

export function useMeetings(courseId: string) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["meetings", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<CourseMeeting[]>>(
        `/courses/${courseId}/meetings`,
        { token }
      );
      return res.data;
    },
  });
}

export function useCreateMeeting(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: {
      meeting_index: number;
      scheduled_at: string;
      title?: string;
      duration_minutes?: number;
      location?: string;
      module_id?: string;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<CourseMeeting>>(
        `/courses/${courseId}/meetings`,
        { token, method: "POST", body: JSON.stringify(body) }
      );
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["meetings", courseId] }),
  });
}

export function useUpdateMeeting(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: {
      meetingId: string;
      patch: Partial<CourseMeeting>;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<CourseMeeting>>(
        `/courses/${courseId}/meetings/${vars.meetingId}`,
        { token, method: "PUT", body: JSON.stringify(vars.patch) }
      );
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["meetings", courseId] }),
  });
}

export function useDeleteMeeting(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (meetingId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await apiFetch<ApiEnvelope<null>>(
        `/courses/${courseId}/meetings/${meetingId}`,
        { token, method: "DELETE" }
      );
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["meetings", courseId] }),
  });
}
