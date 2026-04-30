"use client";
import { ConceptClusterCard } from "./concept-cluster-card";
import {
  useConceptClusters,
  useDecideCluster,
} from "@/hooks/use-concept-clusters";
import {
  useConcepts,
  useEnqueueConceptExtraction,
} from "@/hooks/use-concepts";
import { ApiError } from "@/lib/api";

interface Props {
  readonly courseId: string;
}

export function ConceptClusterQueue({ courseId }: Props) {
  const { data: clusters, isLoading } = useConceptClusters(courseId);
  const { data: concepts } = useConcepts(courseId);
  const decide = useDecideCluster(courseId);
  const enqueue = useEnqueueConceptExtraction(courseId);

  if (isLoading) return <p>Loading clusters…</p>;

  const approvedOptions = (concepts ?? [])
    .filter((c) => c.status === "approved")
    .map((c) => ({ id: c.id, name: c.name }));

  const clusterCount = clusters?.length ?? 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-[var(--color-muted)]">
          {clusterCount === 0
            ? "No pending clusters yet."
            : `${clusterCount} clusters to review`}
        </p>
        <button
          type="button"
          onClick={() => enqueue.mutate()}
          disabled={enqueue.isPending}
          className="rounded bg-[var(--color-accent)] px-3 py-2 text-sm font-medium text-[var(--color-on-accent)] disabled:opacity-50"
        >
          {enqueue.isPending ? "Starting…" : "Run extraction"}
        </button>
      </div>
      {enqueue.isError && (
        <p className="text-xs text-[var(--color-error)]">
          {enqueue.error instanceof ApiError && enqueue.error.status < 500
            ? enqueue.error.message
            : "Extraction failed. Please try again."}
        </p>
      )}
      {clusterCount === 0 ? (
        <p className="text-sm text-[var(--color-muted)]">
          Run extraction to generate candidates for review.
        </p>
      ) : (
        <ul className="space-y-4">
          {(clusters ?? []).map((cluster) => (
            <li key={cluster.cluster_id}>
              <ConceptClusterCard
                cluster={cluster}
                approvedConceptOptions={approvedOptions}
                disabled={decide.isPending}
                onApprove={(final_name, final_description) =>
                  decide.mutate({
                    clusterId: cluster.cluster_id,
                    decision: {
                      action: "approve",
                      final_name,
                      final_description,
                    },
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
      )}
    </div>
  );
}
