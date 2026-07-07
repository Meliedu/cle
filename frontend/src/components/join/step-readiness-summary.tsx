"use client";

import { Check } from "lucide-react";
import { useTranslations } from "next-intl";

import { StateBanner } from "@/components/patterns";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useReadinessSummary } from "@/hooks/use-readiness";

interface StepReadinessSummaryProps {
  readonly courseId: string;
  readonly code: string;
  /** Trigger the terminal join (Task 12 builds the actual enroll action). */
  readonly onJoin: () => void;
  /** Return to the deep preview (S010). */
  readonly onBack?: () => void;
}

/** Phases we render a friendly label for; anything else falls back to its id. */
const KNOWN_PHASES = [
  "eligibility_survey",
  "ready_check",
  "diagnostic",
  "recommendation",
] as const;

function phaseLabel(
  t: ReturnType<typeof useTranslations>,
  phase: string
): string {
  if ((KNOWN_PHASES as readonly string[]).includes(phase)) {
    return t(`summary.phases.${phase}`);
  }
  return phase;
}

function readString(
  result: Record<string, unknown> | null | undefined,
  key: string
): string {
  const value = result?.[key];
  return typeof value === "string" ? value : "";
}

/**
 * S011 — readiness summary. Assembles every completed readiness phase plus the
 * server-computed recommendation into a final "you're ready" recap, then offers
 * the primary CTA to join. The recommendation's `claim_limit` copy is repeated
 * VERBATIM next to the CTA (its second, deliberate surface) so the trust
 * boundary is unmissable at the decision point. The CTA advances the funnel to
 * the terminal join step — Task 12 wires the actual enroll + success/pending.
 */
export function StepReadinessSummary({
  courseId,
  code,
  onJoin,
  onBack,
}: StepReadinessSummaryProps) {
  const t = useTranslations("student.join");
  const summary = useReadinessSummary(courseId, code);

  if (summary.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-7 w-2/3" />
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-10 w-40" />
      </div>
    );
  }

  if (summary.isError || !summary.data) {
    return (
      <div className="space-y-6">
        <StateBanner
          tone="warning"
          title={t("summary.errorTitle")}
          reason={t("summary.errorReason")}
        />
        {onBack ? (
          <Button type="button" variant="outline" size="lg" onClick={onBack}>
            {t("summary.back")}
          </Button>
        ) : null}
      </div>
    );
  }

  const { completed_phases, recommendation } = summary.data;
  const levelHint = readString(recommendation, "level_hint");
  const claimLimit = readString(recommendation, "claim_limit");

  return (
    <div className="space-y-6">
      <div className="space-y-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <div className="space-y-1.5">
          <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
            {t("summary.eyebrow")}
          </p>
          <h2 className="text-[20px] font-semibold leading-tight tracking-tight text-[var(--color-text)]">
            {t("summary.title")}
          </h2>
          <p className="text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
            {t("summary.body")}
          </p>
        </div>

        {completed_phases.length > 0 ? (
          <ul className="space-y-2">
            {completed_phases.map((phase) => (
              <li
                key={phase}
                className="flex items-center gap-2 text-[14px] text-[var(--color-text)]"
              >
                <Check
                  aria-hidden="true"
                  strokeWidth={2.25}
                  className="size-4 shrink-0 text-[var(--color-success, var(--color-text-secondary))]"
                />
                {phaseLabel(t, phase)}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[13px] italic text-[var(--color-text-muted)]">
            {t("summary.noPhases")}
          </p>
        )}

        {levelHint ? (
          <p className="text-[13px] text-[var(--color-text-secondary)]">
            {t("summary.recommendationEcho", {
              level: levelHint,
            })}
          </p>
        ) : null}
      </div>

      {/* Claim-limit surface repeated at the decision point, VERBATIM. */}
      {claimLimit ? (
        <StateBanner
          tone="info"
          title={t("summary.claimLimitTitle")}
          reason={claimLimit}
        />
      ) : null}

      <div className="flex flex-col gap-2 sm:flex-row sm:justify-between">
        {onBack ? (
          <Button type="button" variant="outline" size="lg" onClick={onBack}>
            {t("summary.back")}
          </Button>
        ) : (
          <span />
        )}
        <Button type="button" size="lg" onClick={onJoin}>
          {t("summary.join")}
        </Button>
      </div>
    </div>
  );
}
