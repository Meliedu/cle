"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CheckCircle2, Loader2, Clock } from "lucide-react";
import type { QuestionMessage } from "@/hooks/use-live-quiz";

const OPTION_LABELS = ["A", "B", "C", "D"] as const;

const OPTION_BUTTON_STYLES: Record<string, string> = {
  A: "bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-[var(--color-text-on-primary)]",
  B: "bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white",
  C: "bg-[var(--color-success)] hover:bg-[oklch(58%_0.17_155)] text-white",
  D: "bg-[var(--color-warning)] hover:bg-[oklch(65%_0.16_75)] text-[var(--color-text-on-primary)]",
};

interface PlayerViewProps {
  readonly currentQuestion: QuestionMessage | null;
  readonly questionText?: string;
  readonly options?: Record<string, string>;
  readonly onAnswer: (answer: string) => void;
}

export function PlayerView({
  currentQuestion,
  questionText,
  options,
  onAnswer,
}: PlayerViewProps) {
  const [selectedAnswer, setSelectedAnswer] = useState<string | null>(null);
  const [timeRemaining, setTimeRemaining] = useState(0);
  const [answerStartTime, setAnswerStartTime] = useState<number>(0);

  /* Reset state when a new question arrives */
  useEffect(() => {
    if (currentQuestion) {
      setSelectedAnswer(null);
      setTimeRemaining(currentQuestion.time_limit);
      setAnswerStartTime(Date.now());
    }
  }, [currentQuestion]);

  /* Countdown timer */
  useEffect(() => {
    if (!currentQuestion || selectedAnswer) return;

    const interval = setInterval(() => {
      setTimeRemaining((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [currentQuestion, selectedAnswer]);

  const handleAnswer = useCallback(
    (option: string) => {
      if (selectedAnswer || timeRemaining <= 0) return;
      setSelectedAnswer(option);
      onAnswer(option);
    },
    [selectedAnswer, timeRemaining, onAnswer]
  );

  /* Waiting for next question */
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

  /* Timer progress */
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
            className="h-full rounded-full transition-all duration-1000 ease-linear"
            style={{
              width: `${timerPercent}%`,
              backgroundColor: timerColor,
            }}
          />
        </div>
      </div>

      {/* Question text */}
      {questionText && (
        <Card>
          <CardContent className="py-4">
            <p className="text-center text-base font-medium text-[var(--color-text)]">
              {questionText}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Already answered */}
      {selectedAnswer ? (
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
        /* Answer buttons */
        <div className="grid grid-cols-2 gap-3">
          {OPTION_LABELS.map((label) => {
            const optionText = options?.[label];
            const style = OPTION_BUTTON_STYLES[label] ?? "";

            return (
              <button
                key={label}
                onClick={() => handleAnswer(label)}
                className={`flex flex-col items-center justify-center gap-1 rounded-[var(--radius-xl)] px-4 py-6 text-center font-semibold transition-all duration-[var(--duration-fast)] active:scale-95 ${style}`}
              >
                <span className="text-2xl">{label}</span>
                {optionText && (
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
