"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { ArrowLeft, ArrowRight, Check } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { SwipeResponsePayload } from "@/hooks/use-activities";

type SwipeDirection = "left" | "right";

interface SwipeActivityProps {
  /** Ordered prompts from the activity `config.prompts`. */
  readonly prompts: readonly string[];
  /** Submit one card's answer; resolves once the response is persisted. */
  readonly onSubmit: (payload: SwipeResponsePayload) => Promise<unknown>;
  readonly isSubmitting: boolean;
}

/**
 * S054 — the swipe deck. One prompt card at a time on a single mobile column;
 * the student answers with Left / Right buttons (a keyboard- and screen-reader-
 * accessible stand-in for a touch swipe) which post `{prompt_index, direction}`.
 * Local `answers` drives a progress line; when the last card is answered the
 * deck shows a done state and the runner surfaces the submitted confirmation.
 * Transitions are suppressed under `prefers-reduced-motion`.
 */
export function SwipeActivity({
  prompts,
  onSubmit,
  isSubmitting,
}: SwipeActivityProps) {
  const t = useTranslations("student.activities.swipe");
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<readonly SwipeDirection[]>([]);

  const total = prompts.length;
  const done = index >= total;

  async function answer(direction: SwipeDirection) {
    if (isSubmitting || done) return;
    const promptIndex = index;
    await onSubmit({ prompt_index: promptIndex, direction });
    setAnswers((prev) => [...prev, direction]);
    setIndex((prev) => prev + 1);
  }

  if (done) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-[var(--radius-xl)] border border-[var(--color-success)]/40 bg-[var(--color-success-light)] px-6 py-8 text-center">
        <span className="flex size-11 items-center justify-center rounded-full bg-[var(--color-success)]/15 text-[var(--color-success)]">
          <Check aria-hidden="true" className="size-5" />
        </span>
        <p className="text-[15px] font-semibold text-[var(--color-text)]">
          {t("doneTitle")}
        </p>
        <p className="text-[13px] text-[var(--color-text-secondary)]">
          {t("doneReason", { count: total })}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <div
          className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-surface-hover)]"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={index}
        >
          <div
            className="h-full rounded-full bg-[var(--color-primary)] transition-[width] duration-[var(--duration-fast)] motion-reduce:transition-none"
            style={{ width: `${total === 0 ? 0 : (index / total) * 100}%` }}
          />
        </div>
        <p className="text-[12px] font-medium text-[var(--color-text-muted)]">
          {t("progress", { current: index + 1, total })}
        </p>
      </div>

      <div
        key={index}
        className="flex min-h-[9rem] items-center justify-center rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] px-6 py-8 text-center"
      >
        <p className="text-[17px] font-semibold leading-snug text-[var(--color-text)]">
          {prompts[index]}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Button
          type="button"
          variant="outline"
          size="lg"
          disabled={isSubmitting}
          onClick={() => answer("left")}
          className={cn("h-12 justify-center gap-2 text-[14px]")}
        >
          <ArrowLeft aria-hidden="true" className="size-4" />
          {t("left")}
        </Button>
        <Button
          type="button"
          size="lg"
          disabled={isSubmitting}
          onClick={() => answer("right")}
          className={cn("h-12 justify-center gap-2 text-[14px]")}
        >
          {t("right")}
          <ArrowRight aria-hidden="true" className="size-4" />
        </Button>
      </div>
    </div>
  );
}
