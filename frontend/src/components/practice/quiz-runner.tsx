"use client";

import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { Skeleton } from "@/components/ui/skeleton";
import { StateBanner } from "@/components/patterns";
import { useQuiz } from "@/hooks/use-quizzes";
import { useMyScores } from "@/hooks/use-scores";

import { toQuestionType } from "./answer-encoding";
import { type RenderableQuestion } from "./question-renderer";
import { QuizTaking } from "./quiz-taking";
import { QuizLanding } from "./quiz-landing";
import { AttemptResult } from "./attempt-result";
import { useSubmitAttempt, type AttemptResponse } from "./use-attempt";

interface QuizRunnerProps {
  readonly courseId: string;
  readonly quizId: string;
}

type Phase = "landing" | "taking" | "done";

/**
 * Student graded-quiz flow (F8 / S050–S052): landing with the score-bearing
 * disclosure → taking (reuses the F7 renderers via `QuizTaking`) → result. The
 * disclosure is shown BEFORE start; the student must explicitly begin. Category
 * name is resolved best-effort from the student's own score record (read-only).
 */
export function QuizRunner({ courseId, quizId }: QuizRunnerProps) {
  const t = useTranslations("student.quiz");
  const { data: quiz, isLoading, error } = useQuiz(quizId);
  const { data: myScores } = useMyScores(courseId);
  const submit = useSubmitAttempt(quizId);

  const [phase, setPhase] = useState<Phase>("landing");
  const [attempt, setAttempt] = useState<AttemptResponse | null>(null);

  const questions: RenderableQuestion[] = useMemo(
    () =>
      (quiz?.questions ?? []).map((q) => ({
        id: q.id,
        type: toQuestionType(q.type),
        questionText: q.question_text,
        options: q.options,
      })),
    [quiz]
  );

  const categoryName = useMemo(() => {
    if (!quiz?.score_category_id || !myScores) return null;
    const match = myScores.categories.find(
      (c) => c.category_id === quiz.score_category_id
    );
    return match?.category_name ?? null;
  }, [quiz, myScores]);

  const backHref = `/student/courses/${courseId}/activities`;

  const handleSubmit = useCallback(
    (answers: Record<string, string>, timeTakenSeconds: number) => {
      submit.mutate(
        { answers, time_taken_seconds: timeTakenSeconds },
        {
          onSuccess: (data) => {
            setAttempt(data);
            setPhase("done");
          },
        }
      );
    },
    [submit]
  );

  if (isLoading) {
    return (
      <div className="mx-auto max-w-2xl space-y-4">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-24 w-full rounded-[var(--radius-lg)]" />
        <Skeleton className="h-40 w-full rounded-[var(--radius-lg)]" />
      </div>
    );
  }

  if (error || !quiz) {
    return (
      <div className="mx-auto max-w-2xl">
        <StateBanner
          tone="warning"
          title={t("load.errorTitle")}
          reason={t("load.errorReason")}
          action={
            <Link
              href={backHref}
              className="text-[13px] font-medium text-[var(--color-primary)] hover:underline"
            >
              {t("load.back")}
            </Link>
          }
        />
      </div>
    );
  }

  if (phase === "done" && attempt) {
    return (
      <AttemptResult
        attempt={attempt}
        variant="quiz"
        backHref={backHref}
        backLabel={t("result.back")}
      />
    );
  }

  if (phase === "taking") {
    return (
      <QuizTaking
        questions={questions}
        isSubmitting={submit.isPending}
        submitError={submit.isError ? t("load.errorReason") : null}
        submitLabel={t("taking.submit")}
        onSubmit={handleSubmit}
      />
    );
  }

  // phase === "landing" (S050)
  return (
    <QuizLanding
      quiz={quiz}
      courseId={courseId}
      questionCount={questions.length}
      categoryName={categoryName}
      onStart={() => setPhase("taking")}
    />
  );
}
