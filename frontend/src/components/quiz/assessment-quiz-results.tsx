"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowLeft, BarChart3 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, StateBanner } from "@/components/patterns";
import { useQuiz } from "@/hooks/use-quizzes";
import type { AssessmentConfig } from "@/components/quiz/assessment-config";

interface AssessmentQuizResultsProps {
  readonly courseId: string;
  readonly quizId: string;
  readonly config: AssessmentConfig;
}

/**
 * T064 (practice) / T068 (graded) — the teacher results / evidence view. The
 * per-question attempt rollup endpoint is a later backend seam (no attempts
 * aggregation exists yet), so this ships the designed results scaffold with an
 * honest state: an unpublished quiz collects no attempts (publish first), and a
 * published quiz with no attempts yet shows a waiting state rather than fake
 * zero stats. It reads publish status from the shared quiz detail.
 */
export function AssessmentQuizResults({
  courseId,
  quizId,
  config,
}: AssessmentQuizResultsProps) {
  const t = useTranslations(config.ns);
  const { data: quiz, isLoading, error } = useQuiz(quizId);

  const backHref = `${config.base(courseId)}/${quizId}`;

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Link
          href={backHref}
          className="inline-flex items-center gap-1 text-[13px] text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
        >
          <ArrowLeft aria-hidden="true" className="size-3.5" />
          {t("results.back")}
        </Link>
        <div className="space-y-1">
          <h2 className="text-[18px] font-semibold tracking-tight text-[var(--color-text)]">
            {t("results.title")}
          </h2>
          <p className="text-[13px] text-[var(--color-text-secondary)]">
            {quiz ? quiz.title : t("results.subtitle")}
          </p>
        </div>
      </div>

      {isLoading ? (
        <Skeleton className="h-48 w-full" />
      ) : error || !quiz ? (
        <StateBanner
          tone="warning"
          title={t("results.loadErrorTitle")}
          reason={t("results.loadError")}
        />
      ) : !quiz.is_published ? (
        <EmptyState
          variant="empty"
          icon={BarChart3}
          title={t("results.unpublished.title")}
          reason={t("results.unpublished.reason")}
          action={
            <Button type="button" variant="outline" render={<Link href={backHref} />}>
              {t("results.unpublished.action")}
            </Button>
          }
        />
      ) : (
        <EmptyState
          variant="waiting"
          title={t("results.awaiting.title")}
          reason={t("results.awaiting.reason")}
        />
      )}
    </div>
  );
}
