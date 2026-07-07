"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { PageHeader, StateBanner } from "@/components/patterns";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useCourse } from "@/hooks/use-courses";

/**
 * Student course-workspace tab ids. Mirrors the teacher `CourseTab` union
 * shape but with the student-facing set — the teacher shell is left untouched
 * (P4 F2). Overview is the index; the rest map to route segments.
 */
export type StudentCourseTab =
  | "overview"
  | "checklist"
  | "schedule"
  | "sessions"
  | "materials"
  | "activities";

interface TabDef {
  readonly id: StudentCourseTab;
  /** Path suffix under `/student/courses/[courseId]` — `null` = the index. */
  readonly segment: string | null;
}

/** Ordered student workspace tabs. */
const TABS: readonly TabDef[] = [
  { id: "overview", segment: null },
  { id: "checklist", segment: "checklist" },
  { id: "schedule", segment: "schedule" },
  { id: "sessions", segment: "sessions" },
  { id: "materials", segment: "materials" },
  { id: "activities", segment: "activities" },
];

interface StudentCourseShellProps {
  readonly courseId: string;
  readonly activeTab: StudentCourseTab;
  readonly children: ReactNode;
}

/**
 * Shared chrome for the student course-detail workspace: a `PageHeader` with
 * the course name + code/term/language and a tab nav (overview / checklist /
 * schedule / sessions / materials / activities). Each tab page renders its
 * content as `children`. This is the student mirror of
 * `course-workspace-shell.tsx`; the teacher shell is intentionally not reused
 * so the two lanes can diverge (student has no setup/enrollment tabs).
 */
export function StudentCourseShell({
  courseId,
  activeTab,
  children,
}: StudentCourseShellProps) {
  const t = useTranslations("student.workspace");
  const { data: course, isLoading } = useCourse(courseId);
  const base = `/student/courses/${courseId}`;

  if (isLoading) {
    return (
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="space-y-3">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-9 w-72" />
          <Skeleton className="h-4 w-96" />
        </div>
        <Skeleton className="h-9 w-full max-w-md" />
      </div>
    );
  }

  if (!course) {
    return (
      <div className="mx-auto max-w-6xl">
        <StateBanner
          tone="warning"
          title={t("loadErrorTitle")}
          reason={t("loadError")}
          action={
            <Link
              href="/student/courses"
              className="text-[13px] font-medium text-[var(--color-primary)] hover:underline"
            >
              {t("breadcrumb")}
            </Link>
          }
        />
      </div>
    );
  }

  const meta = [course.code, course.semester, course.language]
    .filter((v): v is string => Boolean(v))
    .join(" · ");

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title={course.name}
        description={meta || undefined}
        breadcrumb={
          <Link
            href="/student/courses"
            className="hover:text-[var(--color-text)]"
          >
            {t("breadcrumb")}
          </Link>
        }
      />

      <nav
        aria-label={t("navLabel")}
        className="flex gap-1 overflow-x-auto border-b border-[var(--color-border)]/70"
      >
        {TABS.map((tab) => {
          const isActive = tab.id === activeTab;
          const href = tab.segment ? `${base}/${tab.segment}` : base;
          return (
            <Link
              key={tab.id}
              href={href}
              aria-current={isActive ? "page" : undefined}
              className={cn(
                "relative -mb-px whitespace-nowrap border-b-2 px-3 py-2 text-[13px] font-medium transition-colors duration-[var(--duration-fast)] hover:text-[var(--color-text)]",
                isActive
                  ? "border-[var(--color-primary)] text-[var(--color-text)]"
                  : "border-transparent text-[var(--color-text-muted)]"
              )}
            >
              {t(`tabs.${tab.id}`)}
            </Link>
          );
        })}
      </nav>

      {children}
    </div>
  );
}
