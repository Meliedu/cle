"use client";

import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { Dumbbell, ListChecks } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader, StateBanner } from "@/components/patterns";
import { useQuiz } from "@/hooks/use-quizzes";

import { toQuestionType } from "./answer-encoding";
import { type RenderableQuestion } from "./question-renderer";
import { QuizTaking } from "./quiz-taking";
import { AttemptResult } from "./attempt-result";
import { useSubmitAttempt, type AttemptResponse } from "./use-attempt";

interface PracticeRunnerProps {
  readonly courseId: string;
  readonly quizId: string;
}

type Phase = "intro" | "taking" | "done";

/**
 * Student practice flow (F7 / S043–S049): start card → one-question-at-a-time
 * taking → per-question feedback + complete. Practice is never score-bearing, so
 * there is no disclosure gate — the intro just previews the set. On submit the
 * server grades every question (MC / matching / ordering / short-answer via
 * `grade_question`) and returns per-question results for the feedback screen.
 */
export function PracticeRunner({ courseId, quizId }: PracticeRunnerProps) {
  const t = useTranslations("student.practice");
  const { data: quiz, isLoading, error } = useQuiz(quizId);
  const submit = useSubmitAttempt(quizId);

  const [phase, setPhase] = useState<Phase>("intro");
  const [attemptKey, setAttemptKey] = useState(0);
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

  const handleRetry = useCallback(() => {
    setAttempt(null);
    submit.reset();
    setAttemptKey((k) => k + 1);
    setPhase("taking");
  }, [submit]);

  if (isLoading) {
    return (
      <div className="mx-auto max-w-2xl space-y-4">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-32 w-full rounded-[var(--radius-lg)]" />
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
        variant="practice"
        backHref={backHref}
        backLabel={t("result.back")}
        onRetry={handleRetry}
      />
    );
  }

  if (phase === "taking") {
    if (questions.length === 0) {
      return (
        <div className="mx-auto max-w-2xl">
          <StateBanner
            tone="waiting"
            title={t("intro.emptyTitle")}
            reason={t("intro.emptyReason")}
          />
        </div>
      );
    }
    return (
      <QuizTaking
        key={attemptKey}
        questions={questions}
        isSubmitting={submit.isPending}
        submitError={submit.isError ? t("taking.submitErrorReason") : null}
        submitLabel={t("taking.finish")}
        onSubmit={handleSubmit}
      />
    );
  }

  // phase === "intro" (S043)
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <PageHeader
        title={quiz.title}
        description={quiz.description ?? undefined}
        breadcrumb={
          <Link href={backHref} className="hover:text-[var(--color-text)]">
            {t("load.back")}
          </Link>
        }
      />
      <Card>
        <CardContent className="space-y-5 py-6">
          <div className="flex items-center gap-3">
            <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary-light)] text-[var(--color-primary)]">
              <Dumbbell aria-hidden="true" className="size-5" />
            </span>
            <div className="space-y-0.5">
              <p className="text-sm font-semibold text-[var(--color-text)]">
                {t("intro.eyebrow")}
              </p>
              <p className="text-[13px] text-[var(--color-text-secondary)]">
                {t("intro.subtitle")}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 text-[13px] text-[var(--color-text-secondary)]">
            <ListChecks
              aria-hidden="true"
              className="size-4 text-[var(--color-text-muted)]"
            />
            {t("intro.questionCount", { count: questions.length })}
          </div>

          <Button
            className="w-full sm:w-auto"
            disabled={questions.length === 0}
            onClick={() => setPhase("taking")}
          >
            {t("intro.start")}
          </Button>

          {questions.length === 0 ? (
            <StateBanner
              tone="waiting"
              title={t("intro.emptyTitle")}
              reason={t("intro.emptyReason")}
            />
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
