"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { CheckCircle2, XCircle, ArrowLeft } from "lucide-react";
import Link from "next/link";

interface QuestionResult {
  readonly question_id: string;
  readonly question_text: string;
  readonly your_answer: string;
  readonly correct_answer: string;
  readonly is_correct: boolean;
  readonly explanation: string;
}

interface QuizAttemptResult {
  readonly score: number;
  readonly total_questions: number;
  readonly correct_count: number;
  readonly time_taken_seconds: number;
  readonly results: readonly QuestionResult[];
}

interface QuizResultsProps {
  readonly attempt: QuizAttemptResult;
  readonly courseId: string;
}

function formatTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes === 0) {
    return `${remainingSeconds}s`;
  }
  return `${minutes}m ${remainingSeconds}s`;
}

function scoreColor(score: number): string {
  if (score >= 80) return "var(--color-success)";
  if (score >= 60) return "var(--color-warning)";
  return "var(--color-error)";
}

function scoreBg(score: number): string {
  if (score >= 80) return "oklch(90% 0.05 145)";
  if (score >= 60) return "oklch(93% 0.05 75)";
  return "oklch(93% 0.05 25)";
}

const CIRCLE_CIRCUMFERENCE = 2 * Math.PI * 54;

export function QuizResults({ attempt, courseId }: QuizResultsProps) {
  const percentage = Math.round(attempt.score);
  const dashOffset =
    CIRCLE_CIRCUMFERENCE - (percentage / 100) * CIRCLE_CIRCUMFERENCE;

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      {/* Score section */}
      <div className="flex flex-col items-center gap-6 py-4">
        <div className="relative flex size-36 items-center justify-center">
          <svg className="size-full -rotate-90" viewBox="0 0 120 120">
            <circle
              cx="60"
              cy="60"
              r="54"
              fill="none"
              stroke="var(--color-border)"
              strokeWidth="8"
            />
            <circle
              cx="60"
              cy="60"
              r="54"
              fill="none"
              stroke={scoreColor(percentage)}
              strokeWidth="8"
              strokeLinecap="round"
              strokeDasharray={CIRCLE_CIRCUMFERENCE}
              strokeDashoffset={dashOffset}
              className="transition-all duration-1000"
              style={{ transitionTimingFunction: "var(--ease-out)" }}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span
              className="text-3xl font-bold"
              style={{ color: scoreColor(percentage) }}
            >
              {percentage}%
            </span>
          </div>
        </div>

        <div className="flex items-center gap-6 text-sm">
          <div className="text-center">
            <p className="text-xs text-[var(--color-text-muted)]">Correct</p>
            <p className="text-lg font-bold text-[var(--color-text)]">
              {attempt.correct_count}/{attempt.total_questions}
            </p>
          </div>
          <Separator orientation="vertical" className="h-8" />
          <div className="text-center">
            <p className="text-xs text-[var(--color-text-muted)]">Time</p>
            <p className="text-lg font-bold text-[var(--color-text)]">
              {formatTime(attempt.time_taken_seconds)}
            </p>
          </div>
        </div>

        <Badge
          className="px-3 py-1 text-sm border-transparent"
          style={{
            backgroundColor: scoreBg(percentage),
            color: scoreColor(percentage),
          }}
        >
          {percentage >= 80
            ? "Great job!"
            : percentage >= 60
              ? "Good effort"
              : "Keep practicing"}
        </Badge>
      </div>

      {/* Per-question review */}
      <div className="space-y-3">
        <h3 className="text-lg font-semibold text-[var(--color-text)]">
          Question Review
        </h3>
        {attempt.results.map((result, index) => (
          <Card
            key={result.question_id}
            className={
              result.is_correct
                ? "ring-1 ring-[var(--color-success)]/20"
                : "ring-1 ring-[var(--color-error)]/20"
            }
          >
            <CardContent className="space-y-3">
              <div className="flex items-start gap-3">
                <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-[var(--color-surface-hover)] text-xs font-medium text-[var(--color-text-muted)]">
                  {index + 1}
                </span>
                <p className="flex-1 text-sm font-medium text-[var(--color-text)]">
                  {result.question_text}
                </p>
                {result.is_correct ? (
                  <CheckCircle2 className="size-5 shrink-0 text-[var(--color-success)]" />
                ) : (
                  <XCircle className="size-5 shrink-0 text-[var(--color-error)]" />
                )}
              </div>

              <div className="ml-9 space-y-1.5 text-sm">
                <div className="flex items-center gap-2">
                  <span className="text-[var(--color-text-muted)]">
                    Your answer:
                  </span>
                  <span
                    className="font-medium"
                    style={{
                      color: result.is_correct
                        ? "var(--color-success)"
                        : "var(--color-error)",
                    }}
                  >
                    {result.your_answer}
                  </span>
                </div>
                {!result.is_correct && (
                  <div className="flex items-center gap-2">
                    <span className="text-[var(--color-text-muted)]">
                      Correct answer:
                    </span>
                    <span className="font-medium text-[var(--color-success)]">
                      {result.correct_answer}
                    </span>
                  </div>
                )}
              </div>

              {result.explanation && (
                <div className="ml-9 rounded-[var(--radius-md)] bg-[var(--color-surface-hover)] p-3">
                  <p className="text-xs leading-relaxed text-[var(--color-text-secondary)]">
                    {result.explanation}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Back button */}
      <div className="flex justify-center pb-8">
        <Button variant="outline" render={<Link href={`/dashboard/courses/${courseId}`} />}>
          <ArrowLeft className="size-4" />
          Back to Course
        </Button>
      </div>
    </div>
  );
}
