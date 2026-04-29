"use client";
import { useState } from "react";
import type { ConceptCluster } from "@/lib/concept-types";

interface Props {
  readonly cluster: ConceptCluster;
  readonly onApprove: (finalName: string, finalDescription?: string) => void;
  readonly onReject: () => void;
  readonly onMerge: (mergeIntoId: string) => void;
  readonly approvedConceptOptions: ReadonlyArray<{ id: string; name: string }>;
  readonly disabled?: boolean;
}

export function ConceptClusterCard({
  cluster,
  onApprove,
  onReject,
  onMerge,
  approvedConceptOptions,
  disabled = false,
}: Props) {
  const [editingName, setEditingName] = useState(cluster.suggested_name);
  const [editingDescription, setEditingDescription] = useState(
    cluster.suggested_description ?? ""
  );
  const [mergeTargetId, setMergeTargetId] = useState<string>("");

  return (
    <article
      className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
      data-testid={`concept-cluster-${cluster.cluster_id}`}
    >
      <header className="space-y-2">
        <input
          type="text"
          value={editingName}
          onChange={(e) => setEditingName(e.target.value)}
          aria-label="Concept name"
          className="w-full rounded border border-[var(--color-border)] bg-transparent px-3 py-2 text-base font-medium text-[var(--color-text)]"
          disabled={disabled}
        />
        <textarea
          value={editingDescription}
          onChange={(e) => setEditingDescription(e.target.value)}
          aria-label="Concept description"
          rows={2}
          className="w-full resize-y rounded border border-[var(--color-border)] bg-transparent px-3 py-2 text-sm text-[var(--color-muted)]"
          disabled={disabled}
        />
      </header>

      <section className="mt-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
          {cluster.members.length} candidate variants
        </h3>
        <ul className="mt-2 space-y-1">
          {cluster.members.map((m) => (
            <li
              key={m.candidate_id}
              className="text-sm text-[var(--color-text)]"
            >
              {m.name}
              {m.description && (
                <span className="ml-2 text-xs text-[var(--color-muted)]">
                  — {m.description}
                </span>
              )}
            </li>
          ))}
        </ul>
      </section>

      <footer className="mt-4 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() =>
            onApprove(
              editingName.trim(),
              editingDescription.trim() || undefined
            )
          }
          disabled={disabled || !editingName.trim()}
          className="rounded bg-[var(--color-accent)] px-3 py-2 text-sm font-medium text-[var(--color-on-accent)] disabled:opacity-50"
        >
          Approve
        </button>

        <select
          aria-label="Merge into existing concept"
          value={mergeTargetId}
          onChange={(e) => setMergeTargetId(e.target.value)}
          disabled={disabled || approvedConceptOptions.length === 0}
          className="rounded border border-[var(--color-border)] bg-transparent px-2 py-2 text-sm"
        >
          <option value="">Merge into…</option>
          {approvedConceptOptions.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => onMerge(mergeTargetId)}
          disabled={disabled || !mergeTargetId}
          className="rounded border border-[var(--color-border)] px-3 py-2 text-sm"
        >
          Merge
        </button>

        <button
          type="button"
          onClick={onReject}
          disabled={disabled}
          className="ml-auto rounded border border-[var(--color-border)] px-3 py-2 text-sm text-[var(--color-error)]"
        >
          Reject
        </button>
      </footer>
    </article>
  );
}
