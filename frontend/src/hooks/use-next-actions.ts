"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type { NextAction, NextActionClick } from "@/lib/decision-types";

export function useNextActions(courseId: string) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["next-actions", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<NextAction[]>>(
        `/users/me/courses/${courseId}/next-actions`,
        { token },
      );
      return res.data;
    },
    staleTime: 30 * 60 * 1000, // matches backend lazy refresh
  });
}

export function useClickNextAction(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (actionId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<NextActionClick>>(
        `/next-actions/${actionId}/click`,
        { token, method: "POST" },
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["next-actions", courseId] });
    },
  });
}
