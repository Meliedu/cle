"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type { AlertStatus, InstructorAlert } from "@/lib/decision-types";

export function useInstructorAlerts(courseId: string, status: AlertStatus = "open") {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["instructor-alerts", courseId, status],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<InstructorAlert[]>>(
        `/courses/${courseId}/alerts?status=${status}`,
        { token },
      );
      return res.data;
    },
  });
}

export function useUpdateInstructorAlert(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      alertId,
      status,
    }: {
      alertId: string;
      status: "dismissed" | "resolved";
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<InstructorAlert>>(
        `/courses/${courseId}/alerts/${alertId}`,
        { token, method: "PATCH", body: JSON.stringify({ status }) },
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instructor-alerts", courseId] });
    },
  });
}
