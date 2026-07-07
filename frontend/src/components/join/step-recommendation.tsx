"use client";

import { useCallback, useEffect, useRef } from "react";
import { useTranslations } from "next-intl";

import { StateBanner } from "@/components/patterns";
import { Button } from "@/components/ui/button";
import { useSubmitPhase } from "@/hooks/use-readiness";

import { levelHintLabel } from "./level-hint";

interface StepRecommendationProps {
  readonly courseId: string;
  readonly code: string;
  /** Advance the funnel to the deep preview (S010). */
  readonly onContinue: () => void;
  /** Return to the diagnostic step (S008). */
  readonly onBack?: () => void;
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
  // Rendered VERBATIM — the backend guarantees this key (a missing claim limit
  // is a 500, not an empty string), so it is always present on success. No
  // hardcoded fallback: if it is somehow absent we render nothing rather than
  // substitute inconsistent disclaimer copy.
  const claimLimit = readString(result, "claim_limit");

  return (
    <div className="space-y-6">
      <div className="space-y-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <div className="space-y-1.5">
          <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
            {t("recommendation.eyebrow")}
          </p>
          <h2 className="text-[20px] font-semibold leading-tight tracking-tight text-[var(--color-text)]">
            {levelHintLabel(t, levelHint)}
          </h2>
          <p className="text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
            {t("recommendation.body")}
          </p>
        </div>

        {confidence !== null ? (
          <p className="text-[13px] text-[var(--color-text-muted)]">
            {t("recommendation.confidence", {
              value: confidence.toFixed(1),
            })}
          </p>
        ) : null}
      </div>

      {/* The claim-limit surface: shown prominently and VERBATIM, only when
          the config-sourced copy is present. */}
      {claimLimit ? (
        <StateBanner
          tone="info"
          title={t("recommendation.claimLimitTitle")}
          reason={claimLimit}
        />
      ) : null}

      <div className="flex flex-col gap-2 sm:flex-row sm:justify-between">
        {onBack ? (
          <Button type="button" variant="outline" size="lg" onClick={onBack}>
            {t("recommendation.back")}
          </Button>
        ) : (
          <span />
        )}
        <Button type="button" size="lg" onClick={onContinue}>
          {t("recommendation.continue")}
        </Button>
      </div>
    </div>
  );
}
