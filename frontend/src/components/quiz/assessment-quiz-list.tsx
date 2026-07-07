"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { HelpCircle, Clock, Sparkles, Plus } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, StateBanner } from "@/components/patterns";
import { GenerateQuizDialog } from "@/components/quiz/generate-quiz-dialog";
import { useQuizzes, type QuizResponse } from "@/hooks/use-quizzes";
import {
  filterByPurpose,
  type AssessmentConfig,
} from "@/components/quiz/assessment-config";

interface AssessmentQuizListProps {
  readonly courseId: string;
  readonly config: AssessmentConfig;
}

function relativeDate(iso: string, justNow: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const days = Math.floor(diffMs / 86_400_000);
  if (days > 7) return new Date(iso).toLocaleDateString();
  if (days > 0) return `${days}d`;
  const hours = Math.floor(diffMs / 3_600_000);
  if (hours > 0) return `${hours}h`;
  const mins = Math.floor(diffMs / 60_000);
  if (mins > 0) return `${mins}m`;
  return justNow;
}

/**
 * T060/T065 — the teacher practice / graded-quiz home. Reuses the shared quiz
 * engine (`useQuizzes` for `after_class` quizzes) and splits it by
 * `assessment_purpose` (Decision 1) so practice and graded quizzes each get
 * their own workspace. Each card links into the per-quiz builder; "Generate"
 * opens the shared `GenerateQuizDialog` stamped with this surface's
 * `assessment_purpose`. Designed empty / loading / error states — never a bare
 * spinner or blank grid.
 */
export function AssessmentQuizList({ courseId, config }: AssessmentQuizListProps) {
  const t = useTranslations(config.ns);
  const [generateOpen, setGenerateOpen] = useState(false);
  const { data, isLoading, error } = useQuizzes(courseId, "after_class");

  const quizzes = useMemo(
    () => filterByPurpose(data, config.purpose),
    [data, config.purpose]
  );

  const generateAction = (
    <Button type="button" size="sm" onClick={() => setGenerateOpen(true)}>
      <Sparkles aria-hidden="true" className="size-4" />
      {t("list.generate")}
    </Button>
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h2 className="text-[17px] font-semibold tracking-tight text-[var(--color-text)]">
            {t("list.title")}
          </h2>
          <p className="max-w-[60ch] text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
            {t("list.subtitle")}
          </p>
        </div>
        {!isLoading && !error && quizzes.length > 0 ? generateAction : null}
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="space-y-3">
                <Skeleton className="h-4 w-40" />
                <Skeleton className="h-5 w-24 rounded-full" />
                <Skeleton className="h-3 w-28" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : error ? (
        <StateBanner
          tone="warning"
          title={t("list.loadErrorTitle")}
          reason={t("list.loadError")}
        />
      ) : quizzes.length === 0 ? (
        <EmptyState
          variant="empty"
          icon={Sparkles}
          title={t("list.empty.title")}
          reason={t("list.empty.reason")}
          action={
            <Button type="button" onClick={() => setGenerateOpen(true)}>
              <Plus aria-hidden="true" className="size-4" />
              {t("list.empty.action")}
            </Button>
          }
        />
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {quizzes.map((quiz) => (
            <li key={quiz.id}>
              <QuizCard courseId={courseId} config={config} quiz={quiz} t={t} />
            </li>
          ))}
        </ul>
      )}

      <GenerateQuizDialog
        courseId={courseId}
        open={generateOpen}
        onOpenChange={setGenerateOpen}
        assessmentPurpose={config.purpose}
      />
    </div>
  );
}

interface QuizCardProps {
  readonly courseId: string;
  readonly config: AssessmentConfig;
  readonly quiz: QuizResponse;
  readonly t: ReturnType<typeof useTranslations>;
}

function QuizCard({ courseId, config, quiz, t }: QuizCardProps) {
  const published = quiz.is_published;
  return (
    <Card className="group h-full transition-all duration-[var(--duration-normal)] hover:border-[var(--color-border-hover)] hover:shadow-[var(--shadow-md)]">
      <Link href={`${config.base(courseId)}/${quiz.id}`} className="block">
        <CardContent className="space-y-3">
          <h3 className="line-clamp-2 font-semibold text-[var(--color-text)] transition-colors duration-[var(--duration-fast)] group-hover:text-[var(--color-primary)]">
            {quiz.title}
          </h3>
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              variant={published ? "secondary" : "outline"}
              className={
                published
                  ? "border-transparent bg-[oklch(90%_0.05_145)] text-[var(--color-success)]"
                  : undefined
              }
            >
              {published ? t("status.published") : t("status.draft")}
            </Badge>
            {config.graded ? (
              <Badge variant="outline">{t("list.gradedBadge")}</Badge>
            ) : null}
            <Badge variant="outline">
              <HelpCircle aria-hidden="true" className="size-3" />
              {t("list.questionCount", { count: quiz.question_count })}
            </Badge>
          </div>
          <span className="flex items-center gap-1 text-xs text-[var(--color-text-muted)]">
            <Clock aria-hidden="true" className="size-3" />
            {relativeDate(quiz.created_at, t("list.justNow"))}
          </span>
        </CardContent>
      </Link>
    </Card>
  );
}
