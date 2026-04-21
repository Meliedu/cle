"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CheckCircle2, XCircle, Minus } from "lucide-react";
import type { LiveReviewQuestion } from "@/hooks/use-live-quiz";

interface LiveReviewProps {
  readonly questions: readonly LiveReviewQuestion[];
  readonly isHost: boolean;
}

function Verdict({ isCorrect }: { readonly isCorrect: boolean | null }) {
  if (isCorrect === true) {
    return (
      <span role="img" aria-label="Correct" className="shrink-0">
        <CheckCircle2 className="size-5 text-[var(--color-success)]" />
        <span className="sr-only">Correct</span>
      </span>
    );
  }
  if (isCorrect === false) {
    return (
      <span role="img" aria-label="Incorrect" className="shrink-0">
        <XCircle className="size-5 text-[var(--color-error)]" />
        <span className="sr-only">Incorrect</span>
      </span>
    );
  }
  return (
    <span role="img" aria-label="Not answered" className="shrink-0">
      <Minus className="size-5 text-[var(--color-text-muted)]" />
      <span className="sr-only">Not answered</span>
    </span>
  );
}

export function LiveReview({ questions, isHost }: LiveReviewProps) {
  if (questions.length === 0) return null;

  const correctCount = questions.filter((q) => q.is_correct === true).length;
  const answeredCount = questions.filter((q) => q.your_answer != null).length;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Question Review</CardTitle>
        {!isHost && (
          <p className="text-sm text-[var(--color-text-muted)]">
            You answered {correctCount} of {questions.length} correctly
            {answeredCount < questions.length
              ? ` (${questions.length - answeredCount} unanswered)`
              : ""}
            .
          </p>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {questions.map((q, idx) => {
          const optionEntries = q.options ? Object.entries(q.options) : [];
          const totalAnswers = q.answer_distribution
            ? Object.values(q.answer_distribution).reduce((a, b) => a + b, 0)
            : 0;
          const ringColor =
            q.is_correct === true
              ? "ring-1 ring-[var(--color-success)]/20"
              : q.is_correct === false
                ? "ring-1 ring-[var(--color-error)]/20"
                : "ring-1 ring-[var(--color-border)]";

          return (
            <Card key={q.question_id} className={ringColor}>
              <CardContent className="space-y-3">
                <div className="flex items-start gap-3">
                  <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-[var(--color-surface-hover)] text-xs font-medium text-[var(--color-text-muted)]">
                    {idx + 1}
                  </span>
                  <p className="flex-1 text-sm font-medium text-[var(--color-text)]">
                    {q.question_text}
                  </p>
                  {!isHost && <Verdict isCorrect={q.is_correct} />}
                </div>

                {optionEntries.length > 0 ? (
                  <div className="ml-9 space-y-1.5">
                    {optionEntries.map(([key, value]) => {
                      const isCorrectOption = key === q.correct_answer;
                      const isChosen = !isHost && key === q.your_answer;
                      const count = q.answer_distribution?.[key] ?? 0;
                      const pct =
                        isHost && totalAnswers > 0
                          ? Math.round((count / totalAnswers) * 100)
                          : 0;

                      return (
                        <div
                          key={key}
                          className={`flex items-center gap-2 rounded-[var(--radius-md)] border px-3 py-2 text-sm ${
                            isCorrectOption
                              ? "border-[var(--color-success)] bg-[var(--color-success-light)]"
                              : isChosen
                                ? "border-[var(--color-error)] bg-[var(--color-error-light)]"
                                : "border-[var(--color-border)]"
                          }`}
                        >
                          <span className="font-semibold text-[var(--color-text)]">
                            {key}:
                          </span>
                          <span className="flex-1 text-[var(--color-text-secondary)]">
                            {value}
                          </span>
                          {isCorrectOption && (
                            <span className="text-xs font-medium text-[var(--color-success)]">
                              Correct
                            </span>
                          )}
                          {!isHost && isChosen && !isCorrectOption && (
                            <span className="text-xs font-medium text-[var(--color-error)]">
                              Your answer
                            </span>
                          )}
                          {isHost && q.answer_distribution && totalAnswers > 0 && (
                            <span className="text-xs font-mono text-[var(--color-text-muted)]">
                              {count} · {pct}%
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  /* Free-text / short-answer fallback — no option grid to
                   * highlight, so render the answers inline instead. */
                  <div className="ml-9 space-y-1.5 text-sm">
                    {!isHost && (
                      <div className="flex items-center gap-2">
                        <span className="text-[var(--color-text-muted)]">
                          Your answer:
                        </span>
                        <span
                          className="font-medium"
                          style={{
                            color:
                              q.is_correct === true
                                ? "var(--color-success)"
                                : q.is_correct === false
                                  ? "var(--color-error)"
                                  : "var(--color-text-muted)",
                          }}
                        >
                          {q.your_answer ?? "(no answer)"}
                        </span>
                      </div>
                    )}
                    <div className="flex items-center gap-2">
                      <span className="text-[var(--color-text-muted)]">
                        Correct answer:
                      </span>
                      <span className="font-medium text-[var(--color-success)]">
                        {q.correct_answer}
                      </span>
                    </div>
                  </div>
                )}

                {!isHost && q.your_answer == null && optionEntries.length > 0 && (
                  <p className="ml-9 text-xs text-[var(--color-text-muted)]">
                    You did not answer this question.
                  </p>
                )}

                {q.explanation && (
                  <div className="ml-9 rounded-[var(--radius-md)] bg-[var(--color-surface-hover)] p-3">
                    <p className="text-xs leading-relaxed text-[var(--color-text-secondary)]">
                      {q.explanation}
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </CardContent>
    </Card>
  );
}
