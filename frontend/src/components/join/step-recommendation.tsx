"use client";

import { useCallback, useEffect, useRef } from "react";
import { useTranslations } from "next-intl";

import { StateBanner } from "@/components/patterns";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useSubmitPhase } from "@/hooks/use-readiness";

import { levelHintLabel } from "./level-hint";
import {
  PlacementEvidence,
  type SkillEvidence,
} from "./placement-evidence";

interface StepRecommendationProps {
  readonly courseId: string;
  readonly code: string;
  /** Advance the funnel to the deep preview (S010). */
  readonly onContinue: () => void;
  /** Return to the diagnostic step (S008). */
  readonly onBack?: () => void;
  /**
   * Ask for a human advisor. Kept SEPARATE from `onContinue` because the
   * approved placement flow requires it: "Request advising and course preview
   * remain separate actions." Collapsing them would make advising look like a
   * step on the way to enrolment rather than an alternative to it.
   */
  readonly onRequestAdvising?: () => void;
}

/** Safely read a string field off the untyped, server-computed result. */
function readString(
  result: Record<string, unknown> | undefined,
  key: string
): string {
  const value = result?.[key];
  return typeof value === "string" ? value : "";
}

/** Safely read a numeric field off the untyped result, or `null` if absent. */
function readNumber(
  result: Record<string, unknown> | undefined,
  key: string
): number | null {
  const value = result?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/**
 * S009 — recommendation result. On entry it POSTs the `recommendation` phase
 * (empty answers — the server computes the result from the earlier ready-check),
 * then renders the coarse `level_hint` bucket plus, PROMINENTLY, the pilot's
 * `claim_limit` copy VERBATIM. The claim limit is a trust/legal boundary: it is
 * shown exactly as the backend returned it (never paraphrased or hardcoded) so
 * the UI never fabricates placement authority — this is guidance, not a
 * placement decision.
 */
export function StepRecommendation({
  courseId,
  code,
  onContinue,
  onBack,
  onRequestAdvising,
}: StepRecommendationProps) {
  const t = useTranslations("student.join");
  const submit = useSubmitPhase(courseId, code);
  const { mutate } = submit;
  const requested = useRef(false);

  // Compute once on entry. The submission is an idempotent upsert server-side,
  // but the ref guards against React's double-invoked effects double-POSTing.
  useEffect(() => {
    if (requested.current) return;
    requested.current = true;
    mutate({ phase: "recommendation", answers: {} });
  }, [mutate]);

  const retry = useCallback(() => {
    mutate({ phase: "recommendation", answers: {} });
  }, [mutate]);

  if (submit.isPending || (!submit.isError && !submit.data)) {
    return (
      <StateBanner
        tone="waiting"
        title={t("recommendation.loadingTitle")}
        reason={t("recommendation.loadingReason")}
      />
    );
  }

  if (submit.isError || !submit.data) {
    return (
      <div className="space-y-6">
        <StateBanner
          tone="warning"
          title={t("recommendation.errorTitle")}
          reason={t("recommendation.errorReason")}
        />
        <div className="flex flex-col gap-2 sm:flex-row sm:justify-between">
          {onBack ? (
            <Button type="button" variant="outline" size="lg" onClick={onBack}>
              {t("recommendation.back")}
            </Button>
          ) : (
            <span />
          )}
          <Button type="button" size="lg" onClick={retry}>
            {t("recommendation.retry")}
          </Button>
        </div>
      </div>
    );
  }

  const result = submit.data.result;
  const levelHint = readString(result, "level_hint");
  const confidence = readNumber(result, "confidence_average");
  const band = readString(result, "confidence_band");
  const evidence = readEvidence(result);
  // Rendered VERBATIM — the backend guarantees this key (a missing claim limit
  // is a 500, not an empty string), so it is always present on success. No
  // hardcoded fallback: if it is somehow absent we render nothing rather than
  // substitute inconsistent disclaimer copy.
  const claimLimit = readString(result, "claim_limit");

  const safeBand: "high" | "medium" | "low" =
    band === "high" || band === "medium" || band === "low" ? band : "low";

  return (
    <div className="space-y-8">
      {/* The recommendation itself. Framed as a recommendation in the chip, the
          eyebrow, and the boundary copy below, so nothing on the screen reads
          as a placement decision. */}
      <section
        aria-labelledby="placement-recommendation"
        className="relative overflow-hidden rounded-[var(--radius-2xl)] border border-[var(--color-gold)]/45 bg-[var(--color-cream)] pl-[5px]"
      >
        <span
          aria-hidden="true"
          className="absolute inset-y-0 left-0 w-[5px] bg-[var(--color-primary)]"
        />
        <div className="flex flex-col gap-6 px-6 py-6 lg:flex-row lg:items-start lg:justify-between lg:gap-10">
          <div className="min-w-0 flex-1">
            <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
              {t("recommendation.eyebrow")}
            </p>
            <h2
              id="placement-recommendation"
              className="mt-2 text-[26px] font-semibold leading-tight tracking-[-0.02em] text-[var(--color-text)]"
            >
              {levelHintLabel(t, levelHint)}
            </h2>
            <p className="mt-2 max-w-[56ch] text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
              {t("recommendation.body")}
            </p>
          </div>

          <div className="shrink-0 lg:w-[260px]">
            <p className="text-[12px] font-medium uppercase tracking-[0.1em] text-[var(--color-text-muted)]">
              {t("recommendation.confidenceLabel")}
            </p>
            <p
              className={cn(
                "mt-1 text-[24px] font-semibold tracking-tight",
                safeBand === "high"
                  ? "text-[var(--color-success)]"
                  : safeBand === "medium"
                    ? "text-[var(--color-primary-hover)]"
                    : "text-[var(--color-text-secondary)]"
              )}
            >
              {t(`recommendation.confidence.${safeBand}`)}
            </p>
            <p className="mt-1 text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
              {t(`recommendation.confidenceReason.${safeBand}`)}
            </p>
            {confidence !== null ? (
              <p className="sr-only">
                {t("recommendation.confidence", {
                  value: confidence.toFixed(1),
                })}
              </p>
            ) : null}
          </div>
        </div>
      </section>

      <section aria-labelledby="placement-evidence">
        <h3
          id="placement-evidence"
          className="text-[13px] font-semibold uppercase tracking-[0.1em] text-[var(--color-text-muted)]"
        >
          {t("recommendation.evidenceTitle")}
        </h3>
        <p className="mt-1 text-[14px] text-[var(--color-text-secondary)]">
          {t("recommendation.evidenceReason")}
        </p>
        <div className="mt-4">
          <PlacementEvidence evidence={evidence} />
        </div>
      </section>

      {/* The claim-limit surface: shown prominently and VERBATIM, only when
          the config-sourced copy is present. */}
      {claimLimit ? (
        <StateBanner
          tone="info"
          title={t("recommendation.claimLimitTitle")}
          reason={claimLimit}
        />
      ) : null}

      {/*
        The decision boundary, stated once and plainly. It sits directly above
        the actions because that is the moment the learner decides what to do
        with the recommendation.
      */}
      <div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-4">
        <p className="text-[12px] font-medium uppercase tracking-[0.1em] text-[var(--color-text-muted)]">
          {t("recommendation.boundaryTitle")}
        </p>
        <p className="mt-1 text-[14px] leading-relaxed text-[var(--color-text)]">
          {t("recommendation.boundaryBody")}
        </p>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        {onBack ? (
          <Button type="button" variant="outline" size="xl" onClick={onBack}>
            {t("recommendation.back")}
          </Button>
        ) : (
          <span />
        )}

        {/* Advising and course preview are separate, and advising is not
            styled as the lesser option: it is a text action, not a disabled
            or dimmed one. */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          {onRequestAdvising ? (
            <button
              type="button"
              onClick={onRequestAdvising}
              className="inline-flex h-11 items-center justify-center rounded-[var(--radius-md)] px-3 text-[14px] font-medium text-[var(--color-text)] underline-offset-4 outline-none transition-colors hover:underline focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none"
            >
              {t("recommendation.requestAdvising")}
            </button>
          ) : null}
          <Button type="button" size="xl" onClick={onContinue}>
            {t("recommendation.previewCourse")}
          </Button>
        </div>
      </div>
    </div>
  );
}

/** Read the typed per-skill evidence rows off the untyped server result. */
function readEvidence(
  result: Record<string, unknown> | undefined
): readonly SkillEvidence[] {
  const raw = result?.evidence;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((entry) => {
    if (!entry || typeof entry !== "object") return [];
    const row = entry as Record<string, unknown>;
    const skill = typeof row.skill === "string" ? row.skill : null;
    const state = row.state;
    if (
      !skill ||
      (state !== "ready" && state !== "developing" && state !== "needs_support")
    ) {
      return [];
    }
    return [
      {
        skill,
        state,
        score: typeof row.score === "number" ? row.score : 0,
      } satisfies SkillEvidence,
    ];
  });
}
