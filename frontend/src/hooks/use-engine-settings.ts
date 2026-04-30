"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type {
  EngineMode,
  EngineOverride,
  EngineSettings,
  OverrideMode,
} from "@/lib/decision-types";

export function useEngineSettings(courseId: string) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["engine-settings", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<EngineSettings>>(
        `/courses/${courseId}/engine`,
        { token },
      );
      return res.data;
    },
  });
}

export function useUpdateEngineMode(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (mode: EngineMode) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<EngineSettings>>(
        `/courses/${courseId}/engine`,
        { token, method: "PATCH", body: JSON.stringify({ mode }) },
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["engine-settings", courseId] });
    },
  });
}

export function useUpsertEngineOverride(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      userId,
      mode,
    }: {
      userId: string;
      mode: OverrideMode;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<EngineOverride>>(
        `/courses/${courseId}/engine/overrides/${userId}`,
        { token, method: "PUT", body: JSON.stringify({ mode }) },
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["engine-settings", courseId] });
    },
  });
}

export function useDeleteEngineOverride(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (userId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<{ deleted: number }>>(
        `/courses/${courseId}/engine/overrides/${userId}`,
        { token, method: "DELETE" },
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["engine-settings", courseId] });
    },
  });
}
