"use client";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type { CohortMasteryRow, MasteryRow } from "@/lib/concept-types";

export function useMyMastery(courseId: string) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["mastery", "me", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<MasteryRow[]>>(
        `/users/me/courses/${courseId}/mastery`,
        { token }
      );
      return res.data;
    },
  });
}

export function useCohortMastery(courseId: string) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["mastery", "cohort", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<CohortMasteryRow[]>>(
        `/courses/${courseId}/mastery`,
        { token }
      );
      return res.data;
    },
  });
}
