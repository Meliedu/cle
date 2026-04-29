"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type {
  ConceptCluster,
  ConceptClusterDecision,
} from "@/lib/concept-types";

export function useConceptClusters(courseId: string) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["concept-clusters", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<ConceptCluster[]>>(
        `/courses/${courseId}/concept-clusters`,
        { token }
      );
      return res.data;
    },
  });
}

interface DecideClusterResult {
  readonly canonical_concept_id: string | null;
}

export function useDecideCluster(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: {
      clusterId: string;
      decision: ConceptClusterDecision;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<DecideClusterResult>>(
        `/courses/${courseId}/concept-clusters/${vars.clusterId}/decide`,
        { token, method: "POST", body: JSON.stringify(vars.decision) }
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["concept-clusters", courseId] });
      qc.invalidateQueries({ queryKey: ["concepts", courseId] });
    },
  });
}
