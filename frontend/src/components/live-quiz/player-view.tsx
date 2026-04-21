"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { CheckCircle2, XCircle, Loader2, Clock } from "lucide-react";
import type { QuestionMessage } from "@/hooks/use-live-quiz";
import { useLiveTimer } from "@/hooks/use-live-timer";
import {
  OPTION_BUTTON_STYLES,
  OPTION_ICONS,
} from "@/components/live-quiz/option-colors";

interface PlayerViewProps {
  readonly currentQuestion: QuestionMessage | null;
  readonly questionText?: string;
  readonly options?: Record<string, string>;
  readonly questionType?: string;
  readonly elapsedSeconds?: number;
  readonly correctAnswer?: string;
  readonly explanation?: string | null;
  readonly onAnswer: (answer: string) => void;
}

export function PlayerView({
  currentQuestion,
  questionText,
  options,
  questionType,
  elapsedSeconds = 0,
  correctAnswer,
  explanation,
  onAnswer,
}: PlayerViewProps) {
  const [selectedAnswer, setSelectedAnswer] = useState<string | null>(null);

  /* Reset answer state when a new question arrives. Deps are primitives so
   * polling doesn't reset this every tick — that used to drive duplicate
   * submissions. */
  const questionIndex = currentQuestion?.index ?? -1;
  useEffect(() => {
    if (questionIndex >= 0) setSelectedAnswer(null);
  }, [questionIndex]);

  /* Server-anchored countdown shared with the host via useLiveTimer so both
   * sides agree on when time is up. */
  const timeRemaining = useLiveTimer(
    questionIndex,
    currentQuestion?.time_limit ?? 0,
    elapsedSeconds
  );

  const handleAnswer = useCallback(
    (option: string) => {
      if (selectedAnswer || timeRemaining <= 0) return;
      setSelectedAnswer(option);
      onAnswer(option);
    },
    [selectedAnswer, timeRemaining, onAnswer]
  );

  if (!currentQuestion) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-16">
        <Loader2 className="size-8 animate-spin text-[var(--color-primary)]" />
        <p className="text-sm font-medium text-[var(--color-text)]">
          Waiting for the next question...
        </p>
      </div>
    );
  }

  const timerPercent =
    currentQuestion.time_limit > 0
      ? (timeRemaining / currentQuestion.time_limit) * 100
      : 0;

  const timerColor =
    timerPercent > 50
      ? "var(--color-success)"
      : timerPercent > 20
        ? "var(--color-warning)"
        : "var(--color-error)";

  const keys = options ? Object.keys(options) : [];
  const isTrueFalse =
    questionType === "true_false" ||
    (keys.length === 2 &&
      keys.every((k) => ["T", "F", "True", "False"].includes(k)));

  const isRevealing = timeRemaining <= 0 && !!correctAnswer;
  const answeredCorrectly =
    selectedAnswer != null && correctAnswer != null && selectedAnswer === correctAnswer;

  return (
    <div className="mx-auto flex max-w-lg flex-col gap-4">
      {/* Timer bar */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-sm">
          <span className="flex items-center gap-1 text-[var(--color-text-muted)]">
            <Clock className="size-3.5" />
            Question {currentQuestion.index + 1}
          </span>
          <span className="font-mono font-semibold" style={{ color: timerColor }}>
            {timeRemaining}s
          </span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-[var(--color-surface-hover)]">
          <div
            className="h-full rounded-full transition-all duration-[var(--duration-normal)] ease-linear"
            style={{
              width: `${timerPercent}%`,
              backgroundColor: timerColor,
            }}
          />
        </div>
      </div>

      {questionText && (
        <Card>
          <CardContent className="py-4">
            <p className="text-center text-base font-medium text-[var(--color-text)]">
              {questionText}
            </p>
          </CardContent>
        </Card>
      )}

      {isRevealing ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-8">
            {answeredCorrectly ? (
              <>
                <CheckCircle2 className="size-10 text-[var(--color-success)]" />
                <p className="text-sm font-medium text-[var(--color-success)]">
                  Correct! You answered {selectedAnswer}.
                </p>
              </>
            ) : selectedAnswer ? (
              <>
                <XCircle className="size-10 text-[var(--color-error)]" />
                <p className="text-sm font-medium text-[var(--color-error)]">
                  Not quite — the correct answer was {correctAnswer}.
                </p>
              </>
            ) : (
              <>
                <Clock className="size-10 text-[var(--color-error)]" />
                <p className="text-sm font-medium text-[var(--color-text)]">
                  Time is up! Correct answer: {correctAnswer}.
                </p>
              </>
            )}
            {explanation && (
              <div className="w-full rounded-[var(--radius-md)] bg-[var(--color-surface-hover)] p-3">
                <p className="text-xs leading-relaxed text-[var(--color-text-secondary)]">
                  {explanation}
                </p>
              </div>
            )}
            <p className="text-xs text-[var(--color-text-muted)]">
              Waiting for the next question...
            </p>
          </CardContent>
        </Card>
      ) : selectedAnswer ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-8">
            <CheckCircle2 className="size-10 text-[var(--color-success)]" />
            <p className="text-sm font-medium text-[var(--color-text)]">
              Answer submitted: {selectedAnswer}
            </p>
            <p className="text-xs text-[var(--color-text-muted)]">
              Waiting for results...
            </p>
          </CardContent>
        </Card>
      ) : timeRemaining <= 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-8">
            <Clock className="size-10 text-[var(--color-error)]" />
            <p className="text-sm font-medium text-[var(--color-text)]">
              Time is up!
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {keys.map((label, i) => {
            const optionText = options?.[label];
            const style = OPTION_BUTTON_STYLES[i] ?? OPTION_BUTTON_STYLES[0];
            const icon = OPTION_ICONS[i] ?? "";
            const displayLabel = isTrueFalse
              ? label.charAt(0).toUpperCase()
              : label;

            return (
              <button
                key={label}
                onClick={() => handleAnswer(label)}
                className={`flex flex-col items-center justify-center gap-2 rounded-[var(--radius-xl)] px-4 py-6 text-center font-semibold shadow-[var(--shadow-md)] transition-all duration-[var(--duration-fast)] hover:scale-[1.02] active:scale-95 ${style}`}
              >
                <span className="flex items-center gap-2 text-2xl">
                  <span aria-hidden="true" className="text-base opacity-80">
                    {icon}
                  </span>
                  {displayLabel}
                </span>
                {optionText && optionText !== label && (
                  <span className="text-xs font-normal opacity-90">
                    {optionText}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
