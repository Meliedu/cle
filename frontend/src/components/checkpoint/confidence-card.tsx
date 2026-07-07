"use client";

import { useTranslations } from "next-intl";

import { ConfidenceScaleInput } from "@/components/patterns";
import { Button } from "@/components/ui/button";
import type { ConfidenceScale } from "@/lib/pilot-config";

import { CheckpointProgress } from "./checkpoint-progress";

export interface ConfidenceCardProps {
  /** The card prompt shown to the student (a review-point statement). */
  readonly prompt: string;
  /** 1-based position of this card in the flow. */
  readonly current: number;
  /** Total number of cards in the flow. */
  readonly total: number;
  /** The pilot's −2..+2 confidence scale (config-driven). */
  readonly scale: ConfidenceScale;
  /** The chosen scale point, or `null` before a choice is made. */
  readonly value: number | null;
  readonly onChange: (value: number) => void;
  /** Advance to the next card / submit this response. Disabled until a value is picked. */
  readonly onNext: () => void;
  /** Step back to the previous card. Omitted on the first card. */
  readonly onBack?: () => void;
  /** In-flight state for the submit that this card triggers. */
  readonly isSubmitting?: boolean;
  /** Optional prior confidence label rendered as a "last time" hint (revisit / S041). */
  readonly lastConfidenceLabel?: string | null;
  /** Question prompt above the scale — differs between a fresh card and a revisit. */
  readonly question: string;
  /** Primary CTA label (e.g. "Next card" / "Submit follow-up"). */
  readonly nextLabel: string;
}

/**
 * S035 / S041 — a single confidence card. One review-point prompt plus the
 * config-driven `ConfidenceScaleInput` (−2..+2). Fully keyboard-completable and
 * single-column (mobile-first); the card is a form so Enter submits and the
 * scale radios are arrow-key reachable. The CTA stays disabled until a scale
 * point is chosen. NB: review-point cards are confidence-only — the backend
 * (`_validate_shape`) rejects free text on them, so no note field lives here;
 * only the final-comments card carries prose.
 */
export function ConfidenceCard({
  prompt,
  current,
  total,
  scale,
  value,
  onChange,
  onNext,
  onBack,
  isSubmitting = false,
  lastConfidenceLabel,
  question,
  nextLabel,
}: ConfidenceCardProps) {
  const t = useTranslations("student.checkpoint.card");
  const groupName = `checkpoint-card-${current}`;
  const canSubmit = value !== null && !isSubmitting;

  return (
    <form
      className="space-y-6"
      onSubmit={(e) => {
        e.preventDefault();
        if (canSubmit) onNext();
      }}
    >
      <CheckpointProgress
        current={current}
        total={total}
        label={t("stepLabel", { current, total })}
      />

      <div className="space-y-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <div className="flex items-start gap-3">
          <span
            aria-hidden="true"
            className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary-light)] text-[13px] font-semibold text-[var(--color-primary-hover)]"
          >
            {current}
          </span>
          <p className="text-[15px] font-medium leading-snug tracking-tight text-[var(--color-text)]">
            {prompt}
          </p>
        </div>

        {lastConfidenceLabel ? (
          <p className="rounded-[var(--radius-md)] bg-[var(--color-surface-hover)] px-3 py-2 text-[13px] text-[var(--color-text-secondary)]">
            {t("lastTime", { value: lastConfidenceLabel })}
          </p>
        ) : null}

        <fieldset className="space-y-2.5" disabled={isSubmitting}>
          <legend className="text-[14px] font-medium leading-snug text-[var(--color-text)]">
            {question}
          </legend>
          <ConfidenceScaleInput
            scale={scale}
            name={groupName}
            value={value}
            onChange={onChange}
            disabled={isSubmitting}
          />
        </fieldset>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:justify-between">
        {onBack ? (
          <Button
            type="button"
            variant="outline"
            size="lg"
            disabled={isSubmitting}
            onClick={onBack}
          >
            {t("back")}
          </Button>
        ) : (
          <span className="hidden sm:block" />
        )}
        <Button type="submit" size="lg" disabled={!canSubmit}>
          {isSubmitting ? t("saving") : nextLabel}
        </Button>
      </div>
    </form>
  );
}
