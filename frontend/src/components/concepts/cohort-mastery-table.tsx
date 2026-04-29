"use client";
import type { CohortMasteryRow } from "@/lib/concept-types";

interface Props {
  readonly rows: ReadonlyArray<CohortMasteryRow>;
}

export function CohortMasteryTable({ rows }: Props) {
  if (rows.length === 0) {
    return (
      <p className="text-sm text-[var(--color-muted)]">
        No mastery data yet — students need to take attempts.
      </p>
    );
  }
  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b border-[var(--color-border)] text-left">
          <th className="py-2 pr-4 font-medium">Concept</th>
          <th className="py-2 pr-4 font-medium">Avg mastery</th>
          <th className="py-2 pr-4 font-medium">Weak students</th>
          <th className="py-2 pr-4 font-medium">Total</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const avg = r.avg_mastery;
          const isWeak = avg !== null && avg < 0.5;
          return (
            <tr
              key={r.concept_id}
              className="border-b border-[var(--color-border)]"
            >
              <td className="py-2 pr-4 text-[var(--color-text)]">
                {r.concept_name}
              </td>
              <td
                className={`py-2 pr-4 ${
                  isWeak ? "text-[var(--color-error)]" : ""
                }`}
              >
                {avg === null ? "—" : `${Math.round(avg * 100)}%`}
              </td>
              <td className="py-2 pr-4">{r.weak_students}</td>
              <td className="py-2 pr-4 text-[var(--color-muted)]">
                {r.total_students_with_evidence}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
