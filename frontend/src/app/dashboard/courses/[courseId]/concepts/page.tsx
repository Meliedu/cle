"use client";
import { use } from "react";
import { useConcepts, useDeleteConcept } from "@/hooks/use-concepts";

export default function ConceptsPage(props: {
  params: Promise<{ courseId: string }>;
}) {
  const { courseId } = use(props.params);
  const { data, isLoading } = useConcepts(courseId);
  const del = useDeleteConcept(courseId);
  if (isLoading) return <p>Loading concepts…</p>;
  return (
    <div className="mx-auto max-w-3xl space-y-3">
      <h1 className="text-2xl font-semibold text-[var(--color-text)]">
        Concepts
      </h1>
      <ul className="divide-y divide-[var(--color-border)]">
        {(data ?? []).map((c) => (
          <li
            key={c.id}
            className="flex items-center justify-between py-2"
          >
            <div>
              <p className="font-medium text-[var(--color-text)]">{c.name}</p>
              {c.description && (
                <p className="text-xs text-[var(--color-muted)]">
                  {c.description}
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => del.mutate(c.id)}
              className="text-sm text-[var(--color-error)]"
              aria-label={`Delete concept ${c.name}`}
            >
              Delete
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
