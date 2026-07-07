"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { PageHeader, StateBanner } from "@/components/patterns";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useCourse, type CourseResponse } from "@/hooks/use-courses";

/** Course-workspace tab ids. P3+ extends the enabled set + adds routes. */
export type CourseTab =
  | "overview"
  | "schedule"
  | "setup"
  | "materials"
  | "activities"
  | "insights";

interface TabDef {
  readonly id: CourseTab;
  /** Path suffix under `/teacher/courses/[courseId]` — `null` = the index. */
  readonly segment: string | null;
  /** `false` = a P3+ placeholder rendered disabled (no route yet). */
  readonly enabled: boolean;
}

/**
 * Ordered workspace tabs. Overview + schedule (this task) and the existing
 * setup route are live; materials/activities/insights are P3+ placeholders,
 * rendered disabled so the nav shape is visible and a later phase only flips
 * `enabled` and adds the route — no restructuring.
 */
const TABS: readonly TabDef[] = [
  { id: "overview", segment: null, enabled: true },
  { id: "schedule", segment: "schedule", enabled: true },
  { id: "setup", segment: "setup", enabled: true },
  { id: "materials", segment: "materials", enabled: false },
  { id: "activities", segment: "activities", enabled: false },
  { id: "insights", segment: "insights", enabled: false },
];

export function isCoursePublished(course: CourseResponse): boolean {
  return (
    course.setup_status === "published" && course.context_status === "approved"
  );
}

interface CourseWorkspaceShellProps {
  readonly courseId: string;
  readonly activeTab: CourseTab;
  readonly children: ReactNode;
}

/**
 * Shared chrome for the teacher course-detail workspace: a `PageHeader` with
 * the course name / code / term / language and a draft-vs-published status
 * badge, plus a tab nav. Overview (T029) and schedule (T030) pages render
 * their content as `children`; P3+ tabs slot into `TABS`. This is the first
 * teacher course-detail route — none existed before this task (P1 deferred the
 * workspace). Setup keeps its own full-screen wizard chrome and is only linked
 * from here, so the shell deliberately does not wrap `/setup`.
 */
export function CourseWorkspaceShell({
  courseId,
  activeTab,
  children,
}: CourseWorkspaceShellProps) {
  const t = useTranslations("teacher.course");
  const { data: course, isLoading } = useCourse(courseId);
  const base = `/teacher/courses/${courseId}`;

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
              href="/teacher/courses"
              className="text-[13px] font-medium text-[var(--color-primary)] hover:underline"
            >
              {t("breadcrumb")}
            </Link>
          }
        />
      </div>
    );
  }

  const published = isCoursePublished(course);
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
            href="/teacher/courses"
            className="hover:text-[var(--color-text)]"
          >
            {t("breadcrumb")}
          </Link>
        }
        actions={
          <Badge variant={published ? "secondary" : "outline"}>
            {published ? t("status.published") : t("status.draft")}
          </Badge>
        }
      />

      <nav
        aria-label={t("overview.title")}
        className="flex gap-1 overflow-x-auto border-b border-[var(--color-border)]/70"
      >
        {TABS.map((tab) => {
          const label = t(`tabs.${tab.id}`);
          const isActive = tab.id === activeTab;
          const className = cn(
            "relative -mb-px whitespace-nowrap border-b-2 px-3 py-2 text-[13px] font-medium transition-colors duration-[var(--duration-fast)]",
            isActive
              ? "border-[var(--color-primary)] text-[var(--color-text)]"
              : "border-transparent text-[var(--color-text-muted)]"
          );

          if (!tab.enabled) {
            return (
              <span
                key={tab.id}
                aria-disabled="true"
                className={cn(
                  className,
                  "flex cursor-not-allowed items-center gap-1.5 opacity-55"
                )}
              >
                {label}
                <Badge variant="outline" className="h-4 px-1 text-[10px]">
                  {t("tabSoon")}
                </Badge>
              </span>
            );
          }

          const href = tab.segment ? `${base}/${tab.segment}` : base;
          return (
            <Link
              key={tab.id}
              href={href}
              aria-current={isActive ? "page" : undefined}
              className={cn(className, "hover:text-[var(--color-text)]")}
            >
              {label}
            </Link>
          );
        })}
      </nav>

      {children}
    </div>
  );
}
