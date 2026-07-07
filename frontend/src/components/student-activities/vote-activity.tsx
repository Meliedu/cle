"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Check } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { VoteResponsePayload } from "@/hooks/use-activities";

interface VoteActivityProps {
  /** Selectable options from the activity `config.options`. */
  readonly options: readonly string[];
  /** The choice already submitted this session, if any (for the checked state). */
  readonly submittedChoice: string | null;
  readonly onSubmit: (payload: VoteResponsePayload) => Promise<unknown>;
  readonly isSubmitting: boolean;
}

/**
 * S055 — the single-choice vote. Radio-group of option cards on one mobile
 * column; the student picks one and submits `{choice}`. A vote REPLACES on the
 * server (one changeable opinion), so after submitting the chosen option stays
 * highlighted and the student may pick again to change it.
 */
export function VoteActivity({
  options,
  submittedChoice,
  onSubmit,
  isSubmitting,
}: VoteActivityProps) {
  const t = useTranslations("student.activities.vote");
  const [selected, setSelected] = useState<string | null>(submittedChoice);

  const canSubmit = selected !== null && selected !== submittedChoice;

  return (
    <div className="space-y-5">
      <fieldset className="space-y-2.5" disabled={isSubmitting}>
        <legend className="text-[14px] font-medium leading-snug text-[var(--color-text)]">
          {t("instructions")}
        </legend>
        <div className="space-y-2">
          {options.map((option) => {
            const isSelected = selected === option;
            const isSubmitted = submittedChoice === option;
            return (
              <label
                key={option}
                className={cn(
                  "flex cursor-pointer items-center gap-3 rounded-[var(--radius-lg)] border px-4 py-3 text-[14px] leading-snug transition-colors duration-[var(--duration-fast)] focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-[var(--color-primary)] motion-reduce:transition-none",
                  isSelected
                    ? "border-[var(--color-primary)] bg-[var(--color-primary-light)] font-medium text-[var(--color-text)]"
                    : "border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]"
                )}
              >
                <input
                  type="radio"
                  name="activity-vote"
                  className="sr-only"
                  checked={isSelected}
                  onChange={() => setSelected(option)}
                />
                <span
                  aria-hidden="true"
                  className={cn(
                    "flex size-5 shrink-0 items-center justify-center rounded-full border",
                    isSelected
                      ? "border-[var(--color-primary)] bg-[var(--color-primary)] text-[var(--color-primary-foreground)]"
                      : "border-[var(--color-border)]"
                  )}
                >
                  {isSelected ? <Check className="size-3" /> : null}
                </span>
                <span className="flex-1">{option}</span>
                {isSubmitted ? (
                  <span className="text-[12px] font-medium text-[var(--color-primary)]">
                    {t("yourVote")}
                  </span>
                ) : null}
              </label>
            );
          })}
        </div>
      </fieldset>

      <Button
        type="button"
        size="lg"
        disabled={!canSubmit || isSubmitting}
        onClick={() => selected && onSubmit({ choice: selected })}
        className="h-11 w-full justify-center"
      >
        {isSubmitting
          ? t("submitting")
          : submittedChoice
            ? t("change")
            : t("submit")}
      </Button>
    </div>
  );
}
