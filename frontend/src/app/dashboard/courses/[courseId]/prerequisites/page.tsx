"use client";
import { use, useState } from "react";
import { useConcepts } from "@/hooks/use-concepts";
import {
  useConceptPrerequisites,
  useCreatePrerequisite,
  useDeletePrerequisite,
} from "@/hooks/use-concept-prerequisites";

export default function PrerequisitesPage(props: {
  params: Promise<{ courseId: string }>;
}) {
  const { courseId } = use(props.params);
  const { data: concepts } = useConcepts(courseId);
  const { data: edges } = useConceptPrerequisites(courseId);
  const create = useCreatePrerequisite(courseId);
  const del = useDeletePrerequisite(courseId);
  const [prereqId, setPrereqId] = useState("");
  const [depId, setDepId] = useState("");

  const conceptOptions = (concepts ?? []).filter(
    (c) => c.status === "approved"
  );
  const conceptName = (id: string) =>
    conceptOptions.find((c) => c.id === id)?.name ?? id;

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-2xl font-semibold text-[var(--color-text)]">
        Concept Prerequisites
      </h1>

      <form
        onSubmit={(event: React.FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          if (prereqId && depId && prereqId !== depId) {
            create.mutate({
              prereq_concept_id: prereqId,
              dependent_concept_id: depId,
              strength: "1.0",
            });
          }
        }}
        className="flex flex-wrap items-center gap-2"
      >
        <select
          value={prereqId}
          onChange={(e) => setPrereqId(e.target.value)}
          aria-label="Prerequisite concept"
          className="rounded border border-[var(--color-border)] bg-transparent px-2 py-1 text-sm"
        >
          <option value="">Prerequisite…</option>
          {conceptOptions.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <span className="text-[var(--color-muted)]">→</span>
        <select
          value={depId}
          onChange={(e) => setDepId(e.target.value)}
          aria-label="Dependent concept"
          className="rounded border border-[var(--color-border)] bg-transparent px-2 py-1 text-sm"
        >
          <option value="">Dependent…</option>
          {conceptOptions.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={!prereqId || !depId || prereqId === depId || create.isPending}
          className="rounded bg-[var(--color-accent)] px-3 py-1 text-sm text-[var(--color-on-accent)] disabled:opacity-50"
        >
          Add edge
        </button>
      </form>

      <ul className="divide-y divide-[var(--color-border)]">
        {(edges ?? []).map((e) => (
          <li
            key={`${e.prereq_concept_id}-${e.dependent_concept_id}`}
            className="flex items-center justify-between py-2 text-sm"
          >
            <span>
              <strong>{conceptName(e.prereq_concept_id)}</strong>
              <span className="mx-2 text-[var(--color-muted)]">→</span>
              <strong>{conceptName(e.dependent_concept_id)}</strong>
            </span>
            <button
              type="button"
              onClick={() =>
                del.mutate({
                  prereqId: e.prereq_concept_id,
                  dependentId: e.dependent_concept_id,
                })
              }
              className="text-xs text-[var(--color-error)]"
              aria-label="Remove prerequisite edge"
            >
              Remove
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
