"use client";

import { Sparkles } from "lucide-react";
import { useTranslations } from "next-intl";

import { EmptyState, StateBanner } from "@/components/patterns";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useFollowUpSuggested } from "@/hooks/use-checkpoints";
import { usePilotConfig } from "@/hooks/use-pilot-config";

interface FollowUpSuggestedProps {
  readonly checkpointId: string;
  /** Begin the revisit (S041). */
  readonly onStart: () => void;
  /** Return to the checkpoint history without revisiting. */
  readonly onViewHistory: () => void;
}

/**
 * S040 — follow-up suggested. Surfaces the review points the student was least
 * confident about last time (weak cards below the pilot's low-confidence
 * threshold) and offers a focused revisit. When nothing was flagged, a positive
 * empty state reassures the student they're on track.
 */
export function FollowUpSuggested({
  checkpointId,
  onStart,
  onViewHistory,
}: FollowUpSuggestedProps) {
  const t = useTranslations("student.checkpoint.followUp");
  const suggested = useFollowUpSuggested(checkpointId);
  const { config } = usePilotConfig();
  const scale = config?.confidence_scale ?? null;

  if (suggested.isLoading) {
    return (
      <div className="space-y-4" aria-busy="true">
        <Skeleton className="h-7 w-2/3" />
        <Skeleton className="h-32 w-full rounded-[var(--radius-lg)]" />
      </div>
    );
  }

  if (suggested.isError || !suggested.data) {
    return (
      <StateBanner
        tone="warning"
        title={t("loadErrorTitle")}
        reason={t("loadErrorReason")}
      />
    );
  }

  const weakCards = suggested.data.weak_cards;

  if (weakCards.length === 0) {
    return (
      <div className="space-y-6">
        <Header />
        <EmptyState
          variant="empty"
          title={t("emptyTitle")}
          reason={t("emptyReason")}
        />
        <Button type="button" size="lg" variant="outline" onClick={onViewHistory}>
          {t("viewHistory")}
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Header />

      <ul className="space-y-3">
        {weakCards.map((card) => {
          const label = scale?.labels[String(card.confidence)] ?? null;
          return (
            <li
              key={card.card_id}
              className="space-y-2.5 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
            >
              <div className="flex items-start gap-2.5">
                <Sparkles
                  aria-hidden="true"
                  strokeWidth={1.85}
                  className="mt-0.5 size-4 shrink-0 text-[var(--color-primary-hover)]"
                />
                <p className="text-[14px] font-medium leading-snug tracking-tight text-[var(--color-text)]">
                  {card.prompt}
                </p>
              </div>
              {card.concept_name ? (
                <p className="text-[12px] font-medium uppercase tracking-[0.12em] text-[var(--color-text-muted)]">
                  {card.concept_name}
                </p>
              ) : null}
              <p className="text-[13px] text-[var(--color-text-secondary)]">
                {label
                  ? t("lastConfidenceLabelled", { value: label })
                  : t("lastConfidence", { value: card.confidence })}
              </p>
              <p className="text-[13px] text-[var(--color-text-secondary)]">
                {t("reason")}
              </p>
            </li>
          );
        })}
      </ul>

      <div className="flex flex-col gap-2">
        <Button type="button" size="lg" onClick={onStart}>
          {t("start")}
        </Button>
        <Button type="button" size="lg" variant="ghost" onClick={onViewHistory}>
          {t("viewHistory")}
        </Button>
      </div>

      <p className="text-center text-[12px] text-[var(--color-text-muted)]">
        {t("footer")}
      </p>
    </div>
  );
}

function Header() {
  const t = useTranslations("student.checkpoint.followUp");
  return (
    <div className="space-y-1.5">
      <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
        {t("eyebrow")}
      </p>
      <h1 className="text-[22px] font-semibold leading-tight tracking-tight text-[var(--color-text)]">
        {t("title")}
      </h1>
      <p className="text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
        {t("subtitle")}
      </p>
    </div>
  );
}
