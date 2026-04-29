"use client";
import { ConceptClusterCard } from "./concept-cluster-card";
import {
  useConceptClusters,
  useDecideCluster,
} from "@/hooks/use-concept-clusters";
import { useConcepts } from "@/hooks/use-concepts";

interface Props {
  readonly courseId: string;
}

export function ConceptClusterQueue({ courseId }: Props) {
  const { data: clusters, isLoading } = useConceptClusters(courseId);
  const { data: concepts } = useConcepts(courseId);
  const decide = useDecideCluster(courseId);

  if (isLoading) return <p>Loading clusters…</p>;
  if (!clusters || clusters.length === 0) {
    return (
      <p className="text-sm text-[var(--color-muted)]">
        No pending clusters. Run extraction to generate candidates.
      </p>
    );
  }

  const approvedOptions = (concepts ?? [])
    .filter((c) => c.status === "approved")
    .map((c) => ({ id: c.id, name: c.name }));

  return (
    <ul className="space-y-4">
      {clusters.map((cluster) => (
        <li key={cluster.cluster_id}>
          <ConceptClusterCard
            cluster={cluster}
            approvedConceptOptions={approvedOptions}
            disabled={decide.isPending}
            onApprove={(final_name, final_description) =>
              decide.mutate({
                clusterId: cluster.cluster_id,
                decision: { action: "approve", final_name, final_description },
              })
            }
            onReject={() =>
              decide.mutate({
                clusterId: cluster.cluster_id,
                decision: { action: "reject" },
              })
            }
            onMerge={(mergeIntoId) =>
              decide.mutate({
                clusterId: cluster.cluster_id,
                decision: {
                  action: "merge",
                  merge_into_concept_id: mergeIntoId,
                },
              })
            }
          />
        </li>
      ))}
    </ul>
  );
}
