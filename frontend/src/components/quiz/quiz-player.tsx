"use client";

import { useState, useRef, useCallback } from "react";
import { useAuth } from "@clerk/nextjs";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  ChevronLeft,
  ChevronRight,
  SendHorizontal,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { QuizResults } from "@/components/quiz/quiz-results";

interface QuizOption {
  readonly label: string;
  readonly text: string;
}

interface QuizQuestion {
  readonly id: string;
  readonly text: string;
  readonly options: readonly QuizOption[];
}

interface QuizDetail {
  readonly id: string;
  readonly title: string;
  readonly questions: readonly QuizQuestion[];
}

interface QuestionResult {
  readonly question_id: string;
  readonly question_text: string;
  readonly your_answer: string;
  readonly correct_answer: string;
  readonly is_correct: boolean;
  readonly explanation: string;
}

interface AttemptResponse {
  readonly score: number;
  readonly total_questions: number;
  readonly correct_count: number;
  readonly time_taken_seconds: number;
  readonly results: readonly QuestionResult[];
}

interface QuizPlayerProps {
  readonly quizId: string;
  readonly courseId: string;
}

export function QuizPlayer({ quizId, courseId }: QuizPlayerProps) {
  const { getToken, isSignedIn } = useAuth();
  const startTimeRef = useRef<number>(Date.now());
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [attemptResult, setAttemptResult] = useState<AttemptResponse | null>(
    null
  );

  const {
    data: quiz,
    isLoading,
    error,
  } = useQuery<QuizDetail>({
    queryKey: ["quiz", quizId],
    queryFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      startTimeRef.current = Date.now();
      const res = await apiFetch<{
        success: boolean;
        data: {
          id: string;
          title: string;
          questions: {
            id: string;
            question_text: string;
            options: Record<string, string> | null;
            explanation: string | null;
          }[];
        };
      }>(`/quizzes/${quizId}`, { token: token! });

      return {
        id: res.data.id,
        title: res.data.title,
        questions: (res.data.questions ?? []).map((q) => ({
          id: q.id,
          text: q.question_text,
          options: Object.entries(q.options ?? {}).map(([label, text]) => ({
            label,
            text,
          })),
        })),
      };
    },
    enabled: isSignedIn === true,
    retry: (count, error) => {
      if (error.message.includes("401") || error.message.includes("Unauthorized")) return false;
      return count < 3;
    },
  });

  const selectAnswer = useCallback(
    (questionId: string, label: string) => {
      setAnswers((prev) => ({ ...prev, [questionId]: label }));
    },
    []
  );

  const handleSubmit = useCallback(async () => {
    if (!quiz) return;

    setIsSubmitting(true);
    setSubmitError(null);

    const timeTaken = Math.floor(
      (Date.now() - startTimeRef.current) / 1000
    );

    try {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      const result = await apiFetch<AttemptResponse>(
        `/quizzes/${quizId}/attempt`,
        {
          method: "POST",
          token: token!,
          body: JSON.stringify({
            answers,
            time_taken_seconds: timeTaken,
          }),
        }
      );
      setAttemptResult(result);
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : "Failed to submit quiz";
      setSubmitError(message);
    } finally {
      setIsSubmitting(false);
      setConfirmOpen(false);
    }
  }, [quiz, quizId, answers, getToken]);

  if (attemptResult) {
    return <QuizResults attempt={attemptResult} courseId={courseId} />;
  }

  if (isLoading) {
    return (
      <div className="mx-auto max-w-2xl space-y-6">
        <Skeleton className="h-2 w-full rounded-full" />
        <div className="space-y-4 pt-4">
          <Skeleton className="h-6 w-3/4" />
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton
                key={i}
                className="h-14 w-full rounded-[var(--radius-lg)]"
              />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (error || !quiz) {
    return (
      <Card className="mx-auto max-w-2xl">
        <CardContent className="flex flex-col items-center py-12 text-center">
          <p className="text-sm text-[var(--color-error)]">
            {error instanceof Error
              ? error.message
              : "Failed to load quiz"}
          </p>
        </CardContent>
      </Card>
    );
  }

  const totalQuestions = quiz.questions.length;
  const currentQuestion = quiz.questions[currentIndex];
  const answeredCount = Object.keys(answers).length;
  const allAnswered = answeredCount === totalQuestions;
  const progressPercent = ((currentIndex + 1) / totalQuestions) * 100;

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      {/* Progress bar */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs text-[var(--color-text-muted)]">
          <span>
            Question {currentIndex + 1} of {totalQuestions}
          </span>
          <span>
            {answeredCount}/{totalQuestions} answered
          </span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-border)]">
          <div
            className="h-full rounded-full bg-[var(--color-primary)] transition-all duration-[var(--duration-normal)]"
            style={{
              width: `${progressPercent}%`,
              transitionTimingFunction: "var(--ease-out)",
            }}
          />
        </div>
      </div>

      {/* Question */}
      <div className="space-y-6 pt-2">
        <h2 className="text-lg font-semibold leading-relaxed text-[var(--color-text)]">
          {currentQuestion.text}
        </h2>

        {/* Options */}
        <div className="space-y-3">
          {currentQuestion.options.map((option) => {
            const isSelected =
              answers[currentQuestion.id] === option.label;

            return (
              <button
                key={option.label}
                type="button"
                onClick={() =>
                  selectAnswer(currentQuestion.id, option.label)
                }
                className="flex w-full items-center gap-3 rounded-[var(--radius-lg)] border p-4 text-left transition-all duration-[var(--duration-fast)] outline-none focus-visible:ring-3 focus-visible:ring-[var(--color-primary)]/30"
                style={{
                  minHeight: "48px",
                  borderColor: isSelected
                    ? "var(--color-primary)"
                    : "var(--color-border)",
                  backgroundColor: isSelected
                    ? "var(--color-primary-light)"
                    : "var(--color-surface)",
                }}
                onMouseEnter={(e) => {
                  if (!isSelected) {
                    e.currentTarget.style.borderColor =
                      "var(--color-border-hover)";
                    e.currentTarget.style.backgroundColor =
                      "var(--color-surface-hover)";
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isSelected) {
                    e.currentTarget.style.borderColor =
                      "var(--color-border)";
                    e.currentTarget.style.backgroundColor =
                      "var(--color-surface)";
                  }
                }}
              >
                <span
                  className="flex size-7 shrink-0 items-center justify-center rounded-full border text-xs font-semibold transition-colors duration-[var(--duration-fast)]"
                  style={{
                    borderColor: isSelected
                      ? "var(--color-primary)"
                      : "var(--color-border)",
                    backgroundColor: isSelected
                      ? "var(--color-primary)"
                      : "transparent",
                    color: isSelected
                      ? "white"
                      : "var(--color-text-muted)",
                  }}
                >
                  {option.label}
                </span>
                <span
                  className="flex-1 text-sm font-medium"
                  style={{
                    color: isSelected
                      ? "var(--color-primary)"
                      : "var(--color-text)",
                  }}
                >
                  {option.text}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between pt-2">
        <Button
          variant="outline"
          disabled={currentIndex === 0}
          onClick={() => setCurrentIndex((prev) => prev - 1)}
        >
          <ChevronLeft className="size-4" />
          Previous
        </Button>

        {/* Question dots */}
        <div className="hidden items-center gap-1.5 sm:flex">
          {quiz.questions.map((q, i) => {
            const isAnswered = q.id in answers;
            const isCurrent = i === currentIndex;

            return (
              <button
                key={q.id}
                type="button"
                onClick={() => setCurrentIndex(i)}
                className="flex size-2.5 rounded-full transition-all duration-[var(--duration-fast)]"
                style={{
                  backgroundColor: isCurrent
                    ? "var(--color-primary)"
                    : isAnswered
                      ? "var(--color-primary)"
                      : "var(--color-border)",
                  opacity: isCurrent ? 1 : isAnswered ? 0.5 : 1,
                  transform: isCurrent ? "scale(1.3)" : "scale(1)",
                }}
                aria-label={`Go to question ${i + 1}`}
              />
            );
          })}
        </div>

        {currentIndex < totalQuestions - 1 ? (
          <Button
            variant="outline"
            onClick={() => setCurrentIndex((prev) => prev + 1)}
          >
            Next
            <ChevronRight className="size-4" />
          </Button>
        ) : (
          <Button disabled={!allAnswered} onClick={() => setConfirmOpen(true)}>
            <SendHorizontal className="size-4" />
            Submit Quiz
          </Button>
        )}
      </div>

      {submitError && (
        <p className="text-center text-sm text-[var(--color-error)]">
          {submitError}
        </p>
      )}

      {/* Submit confirmation */}
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Submit Quiz</DialogTitle>
            <DialogDescription>
              You have answered all {totalQuestions} questions. Are you ready
              to submit?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirmOpen(false)}
              disabled={isSubmitting}
            >
              Review Answers
            </Button>
            <Button onClick={handleSubmit} disabled={isSubmitting}>
              {isSubmitting ? "Submitting..." : "Submit"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
