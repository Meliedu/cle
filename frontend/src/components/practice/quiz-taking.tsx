"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { ChevronLeft, ChevronRight, SendHorizontal } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { StateBanner } from "@/components/patterns";
import { cn } from "@/lib/utils";

import {
  encodeAnswer,
  initialDraft,
  isDraftAnswered,
  matchingColumns,
  type AnswerDraft,
} from "./answer-encoding";
import { QuestionRenderer, type RenderableQuestion } from "./question-renderer";

interface QuizTakingProps {
  readonly questions: readonly RenderableQuestion[];
  readonly isSubmitting: boolean;
  readonly submitError: string | null;
  readonly submitLabel: string;
  /** Called with the per-type encoded answers + elapsed seconds. */
  readonly onSubmit: (
    answers: Record<string, string>,
    timeTakenSeconds: number
  ) => void;
}

/**
 * The shared quiz-taking flow reused by practice (F7) and graded quiz (F8):
 * single-column, one question at a time, progress + dot nav, and a submit
 * confirmation. It manages per-question `AnswerDraft` state and encodes every
 * answer to the exact backend wire shape on submit — so the two flows differ
 * only in how they present the RESULT, never in how answers are produced.
 */
export function QuizTaking({
  questions,
  isSubmitting,
  submitError,
  submitLabel,
  onSubmit,
}: QuizTakingProps) {
  const t = useTranslations("student.practice");
  const startRef = useRef<number>(Date.now());
  const [currentIndex, setCurrentIndex] = useState(0);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, AnswerDraft>>(() =>
    Object.fromEntries(
      questions.map((q) => [q.id, initialDraft(q.type, q.options)])
    )
  );

  const setDraft = useCallback((id: string, draft: AnswerDraft) => {
    setDrafts((prev) => ({ ...prev, [id]: draft }));
  }, []);

  const answeredCount = useMemo(
    () =>
      questions.reduce((count, q) => {
        const draft = drafts[q.id];
        if (!draft) return count;
        const columns =
          q.type === "matching" ? matchingColumns(q.options) : undefined;
        return isDraftAnswered(draft, columns) ? count + 1 : count;
      }, 0),
    [questions, drafts]
  );

  const total = questions.length;
  const current = questions[currentIndex];
  const currentDraft = current
    ? drafts[current.id] ?? initialDraft(current.type, current.options)
    : null;
  const isLast = currentIndex === total - 1;
  const allAnswered = answeredCount === total;
  const progressPercent = total > 0 ? ((currentIndex + 1) / total) * 100 : 0;

  const handleSubmit = useCallback(() => {
    const answers = Object.fromEntries(
      questions.map((q) => [
        q.id,
        encodeAnswer(drafts[q.id] ?? initialDraft(q.type, q.options)),
      ])
    );
    const timeTaken = Math.max(
      0,
      Math.floor((Date.now() - startRef.current) / 1000)
    );
    onSubmit(answers, timeTaken);
  }, [questions, drafts, onSubmit]);

  if (!current || !currentDraft) return null;

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      {/* Progress */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs text-[var(--color-text-muted)]">
          <span>{t("taking.progress", { current: currentIndex + 1, total })}</span>
          <span>{t("taking.answered", { count: answeredCount, total })}</span>
        </div>
        <div
          className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-border)]"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={currentIndex + 1}
        >
          <div
            className="h-full rounded-full bg-[var(--color-primary)] transition-[width] duration-[var(--duration-normal)] motion-reduce:transition-none"
            style={{
              width: `${progressPercent}%`,
              transitionTimingFunction: "var(--ease-out)",
            }}
          />
        </div>
      </div>

      {/* Question */}
      <div className="space-y-6 pt-1">
        <h2 className="text-lg font-semibold leading-relaxed text-[var(--color-text)]">
          <span className="mr-2 text-[var(--color-text-muted)]">
            {currentIndex + 1}.
          </span>
          {current.questionText}
        </h2>

        <QuestionRenderer
          question={current}
          draft={currentDraft}
          onChange={(draft) => setDraft(current.id, draft)}
        />
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between pt-2">
        <Button
          variant="outline"
          disabled={currentIndex === 0}
          onClick={() => setCurrentIndex((i) => i - 1)}
        >
          <ChevronLeft className="size-4" />
          {t("taking.previous")}
        </Button>

        <div
          className="hidden items-center gap-1.5 sm:flex"
          aria-hidden="true"
        >
          {questions.map((q, i) => {
            const draft = drafts[q.id];
            const columns =
              q.type === "matching" ? matchingColumns(q.options) : undefined;
            const answered = draft ? isDraftAnswered(draft, columns) : false;
            const isCurrent = i === currentIndex;
            return (
              <button
                key={q.id}
                type="button"
                onClick={() => setCurrentIndex(i)}
                className={cn(
                  "size-2.5 rounded-full transition-transform duration-[var(--duration-fast)] motion-reduce:transition-none",
                  isCurrent
                    ? "scale-125 bg-[var(--color-primary)]"
                    : answered
                      ? "bg-[var(--color-primary)]/50"
                      : "bg-[var(--color-border)]"
                )}
              />
            );
          })}
        </div>

        {isLast ? (
          <Button onClick={() => setConfirmOpen(true)}>
            <SendHorizontal className="size-4" />
            {submitLabel}
          </Button>
        ) : (
          <Button variant="outline" onClick={() => setCurrentIndex((i) => i + 1)}>
            {t("taking.next")}
            <ChevronRight className="size-4" />
          </Button>
        )}
      </div>

      {submitError ? (
        <StateBanner
          tone="warning"
          title={t("taking.submitErrorTitle")}
          reason={submitError}
        />
      ) : null}

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("taking.confirmTitle")}</DialogTitle>
            <DialogDescription>
              {allAnswered
                ? t("taking.confirmAllAnswered", { total })
                : t("taking.confirmSomeBlank", {
                    answered: answeredCount,
                    total,
                  })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirmOpen(false)}
              disabled={isSubmitting}
            >
              {t("taking.confirmReview")}
            </Button>
            <Button onClick={handleSubmit} disabled={isSubmitting}>
              {isSubmitting ? t("taking.submitting") : t("taking.confirmSubmit")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
