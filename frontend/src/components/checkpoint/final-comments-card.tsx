"use client";

import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

import { CheckpointProgress } from "./checkpoint-progress";

interface FinalCommentsCardProps {
  /** The final card's prompt (backend `final_comments` card). */
  readonly prompt: string;
  /** 1-based position of this card. */
  readonly current: number;
  /** Total number of cards. */
  readonly total: number;
  /** The captured free-text response (may be empty — this card is optional). */
  readonly value: string;
  readonly onChange: (value: string) => void;
  /** Submit the whole checkpoint. */
  readonly onSubmit: () => void;
  readonly onBack: () => void;
  readonly isSubmitting?: boolean;
}

/**
 * S036 — the final comments card. A single optional free-text field the student
 * can leave for the instructor, then the terminal "Submit checkpoint" action.
 * Submitting with an empty note is allowed (the copy says so). Single-column,
 * keyboard-completable; the note field never blocks submission.
 */
export function FinalCommentsCard({
  prompt,
  current,
  total,
  value,
  onChange,
  onSubmit,
  onBack,
  isSubmitting = false,
}: FinalCommentsCardProps) {
  const t = useTranslations("student.checkpoint.final");
  const fieldId = "checkpoint-final-comments";

  return (
    <form
      className="space-y-6"
      onSubmit={(e) => {
        e.preventDefault();
        if (!isSubmitting) onSubmit();
      }}
    >
      <CheckpointProgress
        current={current}
        total={total}
        label={t("stepLabel", { current, total })}
      />

      <div className="space-y-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <div className="space-y-1.5">
          <label
            htmlFor={fieldId}
            className="block text-[15px] font-medium leading-snug tracking-tight text-[var(--color-text)]"
          >
            {prompt || t("title")}
          </label>
          <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
            {t("helper")}
          </p>
        </div>

        <Textarea
          id={fieldId}
          value={value}
          disabled={isSubmitting}
          placeholder={t("placeholder")}
          className="min-h-28"
          onChange={(e) => onChange(e.target.value)}
        />

        <p className="text-[12px] italic text-[var(--color-text-muted)]">
          {t("optional")}
        </p>
      </div>

      <p className="text-center text-[12px] text-[var(--color-text-muted)]">
        {t("attendanceNote")}
      </p>

      <div className="flex flex-col gap-2 sm:flex-row sm:justify-between">
        <Button
          type="button"
          variant="outline"
          size="lg"
          disabled={isSubmitting}
          onClick={onBack}
        >
          {t("back")}
        </Button>
        <Button type="submit" size="lg" disabled={isSubmitting}>
          {isSubmitting ? t("submitting") : t("submit")}
        </Button>
      </div>
    </form>
  );
}
