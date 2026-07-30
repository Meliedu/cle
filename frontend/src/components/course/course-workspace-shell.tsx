"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";

import { StateBanner } from "@/components/patterns";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useCourse, type CourseResponse } from "@/hooks/use-courses";
import {
  courseLifecycle,
  type CourseLifecycle,
} from "@/lib/contracts/state";

/**
 * Course-workspace destination ids.
 *
 * These are no longer tabs. The course rail (`SidebarCourseNav`) is the only
 * course navigation system. The handoff removes the second horizontal tab row
 * outright (Plate 04 rule 1, removal rule 05) because it duplicated the rail
 * and widened without bound as tools accumulated.
 *
 * The id survives as the shell's way of knowing which destination title to
 * render, and to keep the 16 existing call sites working unchanged.
 */
export type CourseTab =
  | "overview"
  | "schedule"
  | "sessions"
  | "enrollment"
  | "setup"
  | "materials"
  | "activities"
  | "practice"
  | "students"
  | "insights"
  | "reports"
  | "memory";

const LIFECYCLE_BADGE: Record<
  CourseLifecycle,
  { readonly key: string; readonly className: string }
> = {
  draft: {
    key: "status.draft",
    className:
      "border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-secondary)]",
  },
  setup: {
    key: "status.setup",
    className:
      "border-[var(--color-gold)]/45 bg-[var(--color-cream)] text-[var(--color-primary-text)]",
  },
  published: {
    key: "status.published",
    className:
      "border-[var(--color-success)]/40 bg-[var(--color-success-light)] text-[var(--color-success)]",
  },
  archived: {
    key: "status.archived",
    className:
      "border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text-muted)]",
  },
};

interface CourseWorkspaceShellProps {
  readonly courseId: string;
  readonly activeTab: CourseTab;
  readonly children: ReactNode;
  /**
   * Optional right-aligned actions for the destination (e.g. "Add session").
   * The lifecycle badge always renders; these sit beside it.
   */
  readonly actions?: ReactNode;
}

/**
 * Chrome for a teacher course destination.
 *
 * Composition follows the approved course header: a breadcrumb back to Courses
 * carrying the course code, the DESTINATION as the heading (course identity
 * already lives in the rail, so repeating it here would be a third copy), the
 * course name plus term as supporting text, and quiet lifecycle context on the
 * right.
 *
 * Setup is deliberately absent from every navigation surface here. It is
 * transient: reachable while the course is incomplete, and replaced by
 * contextual course settings once published.
 */
export function CourseWorkspaceShell({
  courseId,
  activeTab,
  children,
  actions,
}: CourseWorkspaceShellProps) {
  const t = useTranslations("teacher.course");
  const searchParams = useSearchParams();
  const { data: course, isLoading } = useCourse(courseId);

  /**
   * The roster hands its filter query along as `?from=`. Carrying it back into
   * the breadcrumb is what makes "preserve filters across course entry and back
   * navigation" true for the explicit link as well as for browser Back.
   */
  const from = searchParams.get("from");
  const coursesHref = from
    ? `/teacher/courses?${from}`
    : "/teacher/courses";

  if (isLoading) {
    return (
      <div className="mx-auto max-w-6xl space-y-8 px-6 py-8 md:px-10">
        <div className="space-y-3">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-9 w-72" />
          <Skeleton className="h-4 w-96" />
        </div>
        <Skeleton className="h-64 rounded-[var(--radius-2xl)]" />
      </div>
    );
  }

  if (!course) {
    return (
      <div className="mx-auto max-w-6xl px-6 py-8 md:px-10">
        <StateBanner
          tone="warning"
          title={t("loadErrorTitle")}
          reason={t("loadError")}
          action={
            <Link
              href={coursesHref}
              className="rounded-[var(--radius-sm)] text-[13px] font-medium text-[var(--color-primary-text)] underline-offset-2 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40"
            >
              {t("breadcrumb")}
            </Link>
          }
        />
      </div>
    );
  }

  const lifecycle = courseLifecycle(course);
  const badge = LIFECYCLE_BADGE[lifecycle];
  const supporting = [course.name, course.semester, course.language]
    .filter((value): value is string => Boolean(value))
    .join(" · ");

  return (
    <div className="mx-auto max-w-6xl px-6 py-8 md:px-10">
      <header className="mb-8">
        <nav aria-label="Breadcrumb" className="mb-3">
          <ol className="flex items-center gap-1.5 text-[13px] text-[var(--color-text-muted)]">
            <li>
              <Link
                href={coursesHref}
                className="rounded-[var(--radius-sm)] outline-none transition-colors hover:text-[var(--color-text)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none"
              >
                {t("breadcrumb")}
              </Link>
            </li>
            {course.code ? (
              <>
                <li aria-hidden="true">/</li>
                <li className="font-medium text-[var(--color-text-secondary)]">
                  {course.code}
                </li>
              </>
            ) : null}
          </ol>
        </nav>

        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.02em] text-[var(--color-text)]">
              {t(`tabs.${activeTab}`)}
            </h1>
            {supporting ? (
              <p className="mt-1 text-[15px] text-[var(--color-text-secondary)]">
                {supporting}
              </p>
            ) : null}
          </div>

          <div className="flex shrink-0 items-center gap-3">
            {actions}
            <span
              className={cn(
                "inline-flex h-7 items-center rounded-[var(--radius-pill)] border px-3 text-[12px] font-medium",
                badge.className
              )}
            >
              {t(badge.key)}
            </span>
          </div>
        </div>
      </header>

      {children}
    </div>
  );
}
