"use client";

import { CheckCircle2, MessageSquare } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";

interface CheckpointCompleteProps {
  /** Number of review-point cards the student answered. */
  readonly reviewPointCount: number;
  /** Whether the final comments card was submitted. */
  readonly hasComment: boolean;
  /** ISO timestamp of the final submission (for the "submitted at" line). */
  readonly submittedAt: string | null;
  readonly onBackToSession: () => void;
  readonly onViewHistory: () => void;
}

/**
 * S037 — checkpoint submitted. The happy-path terminal after the last card:
 * a success mark, a short receipt of what was recorded (review points +
 * comment + attendance), and a "what happens next" note. Attendance is recorded
 * server-side on submission, so this doubles as the attendance receipt.
 */
export function CheckpointComplete({
  reviewPointCount,
  hasComment,
  submittedAt,
  onBackToSession,
  onViewHistory,
}: CheckpointCompleteProps) {
  const t = useTranslations("student.checkpoint.complete");
  const format = useFormatter();

  return (
    <div className="space-y-6 text-center">
      <div className="flex flex-col items-center gap-3">
        <div className="flex size-16 items-center justify-center rounded-full border border-[var(--color-success)]/40 bg-[var(--color-success-light)]">
          <CheckCircle2
            aria-hidden="true"
            strokeWidth={1.75}
            className="size-8 text-[var(--color-success)]"
          />
        </div>
        <div className="space-y-1.5">
          <h1 className="text-[20px] font-semibold tracking-tight text-[var(--color-text)]">
            {t("title")}
          </h1>
          <p className="text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
            {t("reason")}
          </p>
        </div>
      </div>

      <ul className="space-y-2 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-left">
        <ReceiptRow
          icon={CheckCircle2}
          label={t("reviewPoints", { count: reviewPointCount })}
        />
        {hasComment ? (
          <ReceiptRow icon={MessageSquare} label={t("commentCard")} />
        ) : null}
        {submittedAt ? (
          <ReceiptRow
            icon={CheckCircle2}
            label={t("submittedAt", {
              time: format.dateTime(new Date(submittedAt), {
                hour: "numeric",
                minute: "2-digit",
              }),
            })}
          />
        ) : null}
      </ul>

      <div className="space-y-2 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-hover)] p-4 text-left">
        <h2 className="text-[13px] font-semibold tracking-tight text-[var(--color-text)]">
          {t("whatsNext")}
        </h2>
        <ul className="list-disc space-y-1 pl-4 text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          <li>{t("next1")}</li>
          <li>{t("next2")}</li>
        </ul>
      </div>

      <div className="flex flex-col gap-2">
        <Button type="button" size="lg" onClick={onBackToSession}>
          {t("backToSession")}
        </Button>
        <Button type="button" size="lg" variant="ghost" onClick={onViewHistory}>
          {t("viewHistory")}
        </Button>
      </div>
    </div>
  );
}

function ReceiptRow({
  icon: Icon,
  label,
}: {
  readonly icon: typeof CheckCircle2;
  readonly label: string;
}) {
  return (
    <li className="flex items-center gap-2.5 text-[13px] text-[var(--color-text-secondary)]">
      <Icon
        aria-hidden="true"
        strokeWidth={1.85}
        className="size-4 shrink-0 text-[var(--color-success)]"
      />
      {label}
    </li>
  );
}
