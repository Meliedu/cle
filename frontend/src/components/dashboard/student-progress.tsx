"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowRight } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, PageHeader } from "@/components/patterns";
import { useLearningPath } from "@/hooks/use-learning-path";
import { courseTitle } from "@/lib/format";
import type { LearningAction } from "@/lib/learning-path";
import type { StudentWork } from "@/lib/contracts/state";

/** Per-course roll-up of the learner's assigned work. */
interface CourseProgress {
  readonly courseId: string;
  readonly courseCode: string;
  readonly courseName: string;
  readonly total: number;
  readonly done: number;
  readonly byState: Readonly<Record<StudentWork, number>>;
}

const WORK_ORDER: readonly StudentWork[] = [
  "not_started",
  "in_progress",
  "submitted",
  "reviewed",
];

/** "Done" means the learner has nothing left to do on the item. */
const DONE_STATES: ReadonlySet<StudentWork> = new Set(["submitted", "reviewed"]);

export function rollUpByCourse(
  actions: readonly LearningAction[]
): readonly CourseProgress[] {
  const byCourse = new Map<string, CourseProgress>();

  for (const action of actions) {
    const existing = byCourse.get(action.courseId);
    const base =
      existing ??
      {
        courseId: action.courseId,
        courseCode: action.courseCode,
        courseName: action.courseName,
        total: 0,
        done: 0,
        byState: { not_started: 0, in_progress: 0, submitted: 0, reviewed: 0 },
      };

    byCourse.set(action.courseId, {
      ...base,
      total: base.total + 1,
      done: base.done + (DONE_STATES.has(action.work) ? 1 : 0),
      byState: {
        ...base.byState,
        [action.work]: base.byState[action.work] + 1,
      },
    });
  }

  // Least-complete first: the courses needing attention lead.
  return [...byCourse.values()].sort((a, b) => {
    const ra = a.total === 0 ? 1 : a.done / a.total;
    const rb = b.total === 0 ? 1 : b.done / b.total;
    if (ra !== rb) return ra - rb;
    return a.courseCode.localeCompare(b.courseCode);
  });
}



/**
 * The "My progress" destination.
 *
 * Reuses `useLearningPath`, the same cross-course checklist fan-out Home
 * resolves its next action from, so this page and Home can never disagree
 * about what is outstanding. It rolls up rather than restating: the per-course
 * detail lives on that course's insights surface, which this links to.
 */
export function StudentProgress() {
  const t = useTranslations("student.progress");
  const now = useMemo(() => new Date(), []);
  const { all, isLoading } = useLearningPath(now);

  const courses = useMemo(() => rollUpByCourse(all), [all]);

  if (isLoading) {
    return (
      <div className="mx-auto w-full max-w-3xl space-y-6 py-2" aria-busy="true">
        <PageHeader title={t("title")} description={t("subtitle")} />
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-28 w-full" />
        <span className="sr-only">{t("loading")}</span>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6 py-2">
      <PageHeader title={t("title")} description={t("subtitle")} />

      {courses.length === 0 ? (
        <EmptyState
          title={t("empty")}
          action={
            // Styled Link rather than a Button: `Button` here is a Base UI
            // primitive with no `asChild`, and student-home uses the same
            // treatment for this exact action.
            <Link
              href="/student/join"
              className="inline-flex h-11 items-center rounded-[var(--radius-md)] text-[14px] font-medium text-[var(--color-primary-text)] underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40"
            >
              {t("emptyAction")}
            </Link>
          }
        />
      ) : (
        <ul className="space-y-4">
          {courses.map((course) => (
            <li
              key={course.courseId}
              className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                <h2 className="text-[16px] font-semibold tracking-tight text-[var(--color-text)]">
                  {course.courseCode}
                </h2>
                <p className="text-[13px] tabular-nums text-[var(--color-text-secondary)]">
                  {course.total === 0
                    ? t("noWork")
                    : t("done", { done: course.done, total: course.total })}
                </p>
              </div>
              <p className="mt-0.5 text-[14px] text-[var(--color-text-secondary)]">
                {courseTitle(course.courseCode, course.courseName)}
              </p>

              {course.total > 0 ? (
                <>
                  <div
                    className="mt-3 h-2 overflow-hidden rounded-[var(--radius-pill)] bg-[var(--color-surface-hover)]"
                    role="progressbar"
                    aria-valuemin={0}
                    aria-valuemax={course.total}
                    aria-valuenow={course.done}
                    aria-label={t("done", {
                      done: course.done,
                      total: course.total,
                    })}
                  >
                    <div
                      className="h-full rounded-[var(--radius-pill)] bg-[var(--color-primary)]"
                      style={{
                        width: `${Math.round((course.done / course.total) * 100)}%`,
                      }}
                    />
                  </div>

                  {/* Counts as words, not colour alone. */}
                  <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-[var(--color-text-muted)]">
                    {WORK_ORDER.filter((state) => course.byState[state] > 0).map(
                      (state) => (
                        <li key={state} className="tabular-nums">
                          {t(`state.${state}`)}: {course.byState[state]}
                        </li>
                      )
                    )}
                  </ul>
                </>
              ) : null}

              <div className="mt-4 flex flex-wrap gap-3">
                <Link
                  href={`/student/courses/${course.courseId}`}
                  className="inline-flex items-center gap-1 rounded-[var(--radius-sm)] text-[14px] font-medium text-[var(--color-primary-text)] underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 pointer-coarse:min-h-11"
                >
                  {t("openCourse")}
                  <ArrowRight aria-hidden="true" className="size-3.5" />
                </Link>
                <Link
                  href={`/student/courses/${course.courseId}/insights`}
                  className="inline-flex items-center gap-1 rounded-[var(--radius-sm)] text-[14px] font-medium text-[var(--color-text-secondary)] underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 pointer-coarse:min-h-11"
                >
                  {t("viewInsights")}
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
