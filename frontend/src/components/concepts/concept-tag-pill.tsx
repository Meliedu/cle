"use client";
import { useConceptTagsForTarget } from "@/hooks/use-concept-tags";
import type { ConceptTargetKind } from "@/lib/concept-types";

interface Props {
  readonly targetKind: ConceptTargetKind;
  readonly targetId: string;
}

export function ConceptTagList({ targetKind, targetId }: Props) {
  const { data } = useConceptTagsForTarget(targetKind, targetId);
  if (!data || data.length === 0) return null;
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Concept tags">
      {data.map((c) => (
        <li
          key={c.id}
          className="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-0.5 text-xs text-[var(--color-muted)]"
        >
          {c.name}
        </li>
      ))}
    </ul>
  );
}
