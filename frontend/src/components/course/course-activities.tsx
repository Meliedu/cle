"use client";

import { useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowUpRight } from "lucide-react";

import { PageHeader, StateBanner, EmptyState } from "@/components/patterns";
import { Skeleton } from "@/components/ui/skeleton";
import { ActivityListSection } from "@/components/activities/activity-list-section";
import { ActivityDetail } from "@/components/activities/activity-detail";
import { FoldinLinks } from "@/components/activities/foldin-links";
import { GradeExportCard } from "@/components/activities/grade-export-card";
import {
  useQuizzes,
  type AssessmentPurpose,
  type QuizResponse,
} from "@/hooks/use-quizzes";
import type { Activity, ActivityFormat } from "@/hooks/use-activities";

interface CourseActivitiesProps {
  readonly courseId: string;
}

type View =
  | { readonly mode: "home" }
  | { readonly mode: "new"; readonly format: ActivityFormat }
  | { readonly mode: "edit"; readonly activity: Activity };

/**
 * T074 — teacher Activities home. The hub for this course's participation
 * activities (swipe / vote / comment), a summary of practice + graded quizzes,
 * the folded-in study / live surfaces (Decision 9 — links, not rebuilds), and
 * the audited grade export (T075). Selecting or creating an activity swaps the
 * body for the builder + live monitor + results detail (F4/F5).
 */
export function CourseActivities({ courseId }: CourseActivitiesProps) {
  const t = useTranslations("teacher.activities.home");
  const [view, setView] = useState<View>({ mode: "home" });

  if (view.mode !== "home") {
    return (
      <ActivityDetail
        courseId={courseId}
        format={view.mode === "new" ? view.format : view.activity.format}
        activity={view.mode === "edit" ? view.activity : undefined}
        onBack={() => setView({ mode: "home" })}
      />
    );
  }

  return (
    <div className="space-y-8">
      <PageHeader as="h2" title={t("title")} description={t("description")} />

      <ActivityListSection
        courseId={courseId}
        onNew={(format) => setView({ mode: "new", format })}
        onSelect={(activity) => setView({ mode: "edit", activity })}
      />

      <QuizSummarySection
        courseId={courseId}
        purpose="practice"
        heading={t("sections.practice")}
        emptyTitle={t("emptyPractice.title")}
        emptyReason={t("emptyPractice.reason")}
      />

      <QuizSummarySection
        courseId={courseId}
        purpose="graded"
        heading={t("sections.quiz")}
        emptyTitle={t("emptyQuiz.title")}
        emptyReason={t("emptyQuiz.reason")}
      />

      <section className="space-y-4">
        <h2 className="text-[16px] font-semibold text-[var(--color-text)]">
          {t("sections.foldins")}
        </h2>
        <FoldinLinks courseId={courseId} />
      </section>

      <GradeExportCard courseId={courseId} />
    </div>
  );
}

interface QuizSummarySectionProps {
  readonly courseId: string;
  readonly purpose: AssessmentPurpose;
  readonly heading: string;
  readonly emptyTitle: string;
  readonly emptyReason: string;
}

/**
 * Read-only summary of practice or graded quizzes for this course, filtered by
 * `assessment_purpose`. Each row deep-links into the existing quiz surface —
 * the quiz builders themselves live in the teacher-quiz track (F2/F3).
 */
function QuizSummarySection({
  courseId,
  purpose,
  heading,
  emptyTitle,
  emptyReason,
}: QuizSummarySectionProps) {
  const t = useTranslations("teacher.activities.home");
  const { data, isLoading, isError } = useQuizzes(courseId);
  const quizzes = (data ?? []).filter((q) => q.assessment_purpose === purpose);

  return (
    <section className="space-y-4">
      <h2 className="text-[16px] font-semibold text-[var(--color-text)]">{heading}</h2>

      {isLoading ? (
        <Skeleton className="h-12 w-full rounded-[var(--radius-lg)]" />
      ) : isError ? (
        <StateBanner tone="warning" title={t("error.title")} reason={t("error.reason")} />
      ) : quizzes.length === 0 ? (
        <EmptyState
          className="rounded-[var(--radius-xl)] border border-dashed border-[var(--color-border)]"
          title={emptyTitle}
          reason={emptyReason}
        />
      ) : (
        <ul className="space-y-2">
          {quizzes.map((quiz) => (
            <li key={quiz.id}>
              <QuizRow courseId={courseId} quiz={quiz} openLabel={t("open")} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

interface QuizRowProps {
  readonly courseId: string;
  readonly quiz: QuizResponse;
  readonly openLabel: string;
}

function QuizRow({ courseId, quiz, openLabel }: QuizRowProps) {
  const t = useTranslations("teacher.activities.home");
  return (
    <Link
      href={`/dashboard/courses/${courseId}/quizzes/${quiz.id}`}
      className="group flex items-center gap-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 transition-colors hover:border-[var(--color-primary)]/50 hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-[var(--color-primary)]/40"
    >
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[14px] font-medium text-[var(--color-text)]">
          {quiz.title}
        </span>
        <span className="text-[12px] text-[var(--color-text-muted)]">
          {t("questionCount", { count: quiz.question_count })}
        </span>
      </span>
      <span className="shrink-0 text-[11px] font-medium text-[var(--color-text-muted)]">
        {quiz.is_published ? t("status.published") : t("status.draft")}
      </span>
      <span className="inline-flex shrink-0 items-center gap-1 text-[12px] font-medium text-[var(--color-primary)]">
        {openLabel}
        <ArrowUpRight
          aria-hidden="true"
          className="size-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
        />
      </span>
    </Link>
  );
}
