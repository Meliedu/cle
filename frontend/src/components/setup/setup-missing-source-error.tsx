"use client";

import { useTranslations } from "next-intl";
import { ArrowLeft, CircleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { StateBanner } from "@/components/patterns";
import {
  SETUP_STEP_KEYS,
  type MissingSource,
  type SetupStepKey,
} from "@/hooks/use-setup";

interface SetupMissingSourceErrorProps {
  /** Incomplete step keys returned by the publish gate (409 SETUP_INCOMPLETE). */
  readonly missingSteps: readonly string[];
  /** Ungrounded sources surfaced by the latest `analyze_course_setup` result. */
  readonly missingSources?: readonly MissingSource[];
  /** Jump back to the wizard step that resolves an item. */
  readonly onNavigate?: (step: SetupStepKey) => void;
  /** Return to the review checklist. */
  readonly onBack?: () => void;
}

/** Which wizard step resolves each analyzer missing-source kind. */
const MISSING_SOURCE_STEP: Record<string, SetupStepKey> = {
  objective_without_source: "ilo_map",
  session_without_material: "materials",
};

function isStepKey(value: string): value is SetupStepKey {
  return (SETUP_STEP_KEYS as readonly string[]).includes(value);
}

/**
 * T028 — setup-missing-source-error. The blocked state rendered when
 * `usePublishSetup` is rejected with `409 SETUP_INCOMPLETE`: the course cannot
 * open until every outstanding step is done. It lists each incomplete step with
 * a jump-back link, and — when the latest analysis flagged ungrounded outcomes
 * or sessions — surfaces those `missing_sources` too, each mapped to the step
 * that fixes it. `StateBanner tone="blocked"` (spec §3.4 hard gate).
 */
export function SetupMissingSourceError({
  missingSteps,
  missingSources = [],
  onNavigate,
  onBack,
}: SetupMissingSourceErrorProps) {
  const t = useTranslations("teacher.setup.missingSource");
  const ts = useTranslations("teacher.setup");

  const steps = missingSteps.filter(isStepKey);

  return (
    <div className="space-y-6">
      <div className="space-y-1.5">
        <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
          {t("title")}
        </h2>
        <p className="max-w-[56ch] text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          {t("subtitle")}
        </p>
      </div>

      <StateBanner tone="blocked" title={t("bannerTitle")} reason={t("bannerReason")} />

      {steps.length > 0 ? (
        <section className="space-y-2.5">
          <p className="text-[12px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            {t("stepsLabel")}
          </p>
          <ul aria-label={t("stepsLabel")} className="space-y-2">
            {steps.map((key) => (
              <li
                key={key}
                className="flex items-start justify-between gap-3 rounded-[var(--radius-md)] border border-[var(--color-error)]/30 bg-[var(--color-error-light)] p-3.5"
              >
                <div className="flex min-w-0 gap-2.5">
                  <CircleAlert
                    aria-hidden="true"
                    strokeWidth={1.85}
                    className="mt-0.5 size-4 shrink-0 text-[var(--color-error)]"
                  />
                  <div className="min-w-0 space-y-0.5">
                    <p className="text-[13px] font-medium text-[var(--color-text)]">
                      {ts(`steps.${key}`)}
                    </p>
                    <p className="text-[12px] leading-snug text-[var(--color-text-secondary)]">
                      {ts(`review.stepDesc.${key}`)}
                    </p>
                  </div>
                </div>
                {onNavigate ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="shrink-0"
                    onClick={() => onNavigate(key)}
                  >
                    {t("fix")}
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {missingSources.length > 0 ? (
        <section className="space-y-2.5">
          <p className="text-[12px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            {t("sourcesLabel")}
          </p>
          <ul aria-label={t("sourcesLabel")} className="space-y-2">
            {missingSources.map((source) => {
              const target = MISSING_SOURCE_STEP[source.kind] ?? "materials";
              return (
                <li
                  key={`${source.kind}-${source.id}`}
                  className="flex items-start justify-between gap-3 rounded-[var(--radius-md)] border border-[var(--color-warning)]/40 bg-[var(--color-warning-light)] p-3.5"
                >
                  <div className="min-w-0 space-y-0.5">
                    <p className="text-[12px] font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
                      {t(`kind.${source.kind}`)}
                    </p>
                    <p className="truncate text-[13px] text-[var(--color-text)]">
                      {source.label}
                    </p>
                  </div>
                  {onNavigate ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="shrink-0"
                      onClick={() => onNavigate(target)}
                    >
                      {t("fix")}
                    </Button>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      {onBack ? (
        <div className="flex items-center gap-3">
          <Button type="button" size="lg" variant="outline" onClick={onBack}>
            <ArrowLeft aria-hidden="true" />
            {t("back")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
