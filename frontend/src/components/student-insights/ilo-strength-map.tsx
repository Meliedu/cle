"use client";

import { useTranslations } from "next-intl";
import { Target } from "lucide-react";

import { EmptyState, StateBanner } from "@/components/patterns";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useIloMap,
  type StudentIloObjective,
} from "@/hooks/use-insights";

interface IloStrengthMapProps {
  readonly courseId: string;
}

/**
 * S064 — student ILO strength map. Reshapes `concept_mastery` aggregated over the
 * concepts tagged to each learning objective (`useIloMap`, pure read). An
 * objective with no evidence-bearing concept renders an honest no-evidence cell —
 * NEVER a fabricated 0 (Decision 7). A course with no objective evidence at all
 * collapses to the designed no-evidence state (S070).
 */
export function IloStrengthMap({ courseId }: IloStrengthMapProps) {
  const t = useTranslations("student.insights.ilo");
  const { data, isLoading, isError } = useIloMap(courseId);

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-20 w-full rounded-[var(--radius-xl)]" />
        ))}
      </div>
    );
  }

  if (isError || !data) {
    return (
      <StateBanner
        tone="warning"
        title={t("error.title")}
        reason={t("error.reason")}
      />
    );
  }

  return (
    <section className="space-y-3">
      <header className="space-y-1">
        <h2 className="flex items-center gap-2 text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
          <Target
            aria-hidden="true"
            className="size-4 text-[var(--color-text-muted)]"
          />
          {t("title")}
        </h2>
        <p className="text-[13px] text-[var(--color-text-secondary)]">
          {t("subtitle")}
        </p>
      </header>

      {!data.has_evidence ? (
        <EmptyState
          variant="waiting"
          title={t("empty.title")}
          reason={t("empty.reason")}
        />
      ) : (
        <ul className="space-y-2">
          {data.objectives.map((objective) => (
            <IloRow key={objective.objective_id} objective={objective} />
          ))}
        </ul>
      )}
    </section>
  );
}

/** One objective: a strength meter when evidence exists, an honest cell when not. */
function IloRow({ objective }: { readonly objective: StudentIloObjective }) {
  const t = useTranslations("student.insights.ilo");

  return (
    <li className="space-y-2 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[14px] font-medium text-[var(--color-text)]">
          {objective.statement}
        </p>
        {objective.bloom_level ? (
          <span className="shrink-0 rounded-[var(--radius-pill)] border border-[var(--color-border)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-text-muted)]">
            {t("bloom", { level: objective.bloom_level })}
          </span>
        ) : null}
      </div>

      {objective.has_evidence && objective.strength !== null ? (
        <div className="space-y-1">
          <div className="flex items-center justify-between text-[12px]">
            <span className="font-medium text-[var(--color-text-secondary)]">
              {t("strength")}
            </span>
            <span className="tabular-nums font-semibold text-[var(--color-text)]">
              {Math.round(objective.strength * 100)}%
            </span>
          </div>
          <div
            role="progressbar"
            aria-label={t("strength")}
            aria-valuenow={Math.round(objective.strength * 100)}
            aria-valuemin={0}
            aria-valuemax={100}
            className="h-2 w-full overflow-hidden rounded-[var(--radius-pill)] bg-[var(--color-surface-hover)]"
          >
            <div
              className="h-full rounded-[var(--radius-pill)] bg-[var(--color-primary)]"
              style={{ width: `${objective.strength * 100}%` }}
            />
          </div>
          <p className="text-[12px] text-[var(--color-text-muted)]">
            {t("coverage", {
              evidence: objective.evidence_concept_count,
              total: objective.concept_count,
            })}
          </p>
        </div>
      ) : (
        // Honest no-evidence cell — never a fabricated 0 (Decision 7).
        <div className="flex items-center gap-2 rounded-[var(--radius-md)] bg-[var(--color-surface-hover)] px-3 py-2">
          <span className="text-[12px] font-medium text-[var(--color-text-muted)]">
            {t("noEvidence")}
          </span>
          <span className="text-[12px] text-[var(--color-text-muted)]">
            · {t("noEvidenceReason")}
          </span>
        </div>
      )}
    </li>
  );
}
