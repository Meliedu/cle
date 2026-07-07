"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { CheckCircle2, RotateCcw, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

import type { AttemptResponse } from "./use-attempt";

interface AttemptResultProps {
  readonly attempt: AttemptResponse;
  /** `practice` = encouraging complete (S049); `quiz` = graded result (S052). */
  readonly variant: "practice" | "quiz";
  readonly backHref: string;
  readonly backLabel: string;
  /** Practice-only: restart the same set. */
  readonly onRetry?: () => void;
}

function scorePercent(score: number): number {
  return Math.max(0, Math.min(100, Math.round(Number(score))));
}

/**
 * Post-submit result surface shared by both flows. Practice frames it as a
 * complete screen (S049) with a "try again"; graded frames it as a result
 * (S052). Both render the per-question feedback list (S048): a correct/incorrect
 * marker plus the instructor explanation when present.
 */
export function AttemptResult({
  attempt,
  variant,
  backHref,
  backLabel,
  onRetry,
}: AttemptResultProps) {
  const t = useTranslations("student.practice");
  const percent = scorePercent(attempt.score);

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      {/* Score summary */}
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-8 text-center">
          <p className="text-[13px] font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
            {variant === "practice"
              ? t("result.practiceEyebrow")
              : t("result.quizEyebrow")}
          </p>
          <p className="text-5xl font-semibold tabular-nums text-[var(--color-text)]">
            {percent}
            <span className="text-2xl text-[var(--color-text-muted)]">%</span>
          </p>
          <p className="text-sm text-[var(--color-text-secondary)]">
            {t("result.correctOf", {
              correct: attempt.correct_count,
              total: attempt.total_questions,
            })}
          </p>
        </CardContent>
      </Card>

      {/* Per-question feedback (S048) */}
      <section className="space-y-3" aria-label={t("result.feedbackLabel")}>
        {attempt.results.map((item, index) => (
          <Card
            key={item.question_id}
            className={cn(
              "ring-1",
              item.is_correct
                ? "ring-[var(--color-success)]/30"
                : "ring-[var(--color-error)]/30"
            )}
          >
            <CardContent className="flex gap-3 py-4">
              {item.is_correct ? (
                <CheckCircle2
                  aria-hidden="true"
                  className="mt-0.5 size-5 shrink-0 text-[var(--color-success)]"
                />
              ) : (
                <XCircle
                  aria-hidden="true"
                  className="mt-0.5 size-5 shrink-0 text-[var(--color-error)]"
                />
              )}
              <div className="min-w-0 flex-1 space-y-1.5">
                <p className="text-sm font-medium text-[var(--color-text)]">
                  <span className="mr-1.5 text-[var(--color-text-muted)]">
                    {index + 1}.
                  </span>
                  {item.question_text}
                </p>
                <p
                  className={cn(
                    "text-[13px] font-medium",
                    item.is_correct
                      ? "text-[var(--color-success)]"
                      : "text-[var(--color-error)]"
                  )}
                >
                  {item.is_correct
                    ? t("result.correct")
                    : t("result.incorrect")}
                </p>
                {item.explanation ? (
                  <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
                    {item.explanation}
                  </p>
                ) : null}
              </div>
            </CardContent>
          </Card>
        ))}
      </section>

      {/* Actions */}
      <div className="flex flex-col gap-2 sm:flex-row sm:justify-center">
        {variant === "practice" && onRetry ? (
          <Button variant="outline" onClick={onRetry}>
            <RotateCcw className="size-4" />
            {t("result.retry")}
          </Button>
        ) : null}
        <Button render={<Link href={backHref} />}>{backLabel}</Button>
      </div>
    </div>
  );
}
