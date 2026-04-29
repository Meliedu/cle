"use client";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type { Concept, ConceptTargetKind } from "@/lib/concept-types";

export function useConceptTagsForTarget(
  targetKind: ConceptTargetKind,
  targetId: string
) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["concept-tags", targetKind, targetId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<Concept[]>>(
        `/concept-tags/${targetKind}/${targetId}`,
        { token }
      );
      return res.data;
    },
  });
}
