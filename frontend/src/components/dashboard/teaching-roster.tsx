"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowRight } from "lucide-react";

import { formatRelativeTime } from "@/lib/format";
import { courseLifecycle } from "@/lib/contracts/state";
import type { CourseResponse } from "@/hooks/use-courses";

interface TeachingRosterProps {
  readonly courses: readonly CourseResponse[];
  /** Courses shown before the list defers to the Courses destination. */
  readonly limit?: number;
}

/**
 * The compact roster region on the dashboard (Plate 01, rule 3).
 *
 * This is a glance, not the roster. The operational roster (with filters,
 * next-class ordering, and per-course verbs) lives on `/teacher/courses`,
 * which owns it. Duplicating that here would be a second copy of the same
 * destination, so this shows identity plus recency and links onward.
 */
export function TeachingRoster({ courses, limit = 3 }: TeachingRosterProps) {
  const t = useTranslations("teacher.home");

  const shown = [...courses]
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    .slice(0, limit);

  return (
    <section aria-labelledby="teaching-roster-title">
      <div className="flex items-baseline justify-between gap-4">
        <h2
          id="teaching-roster-title"
          className="text-[13px] font-semibold uppercase tracking-[0.1em] text-[var(--color-text-muted)]"
        >
          {t("roster.title")}
        </h2>
        {courses.length > shown.length ? (
          <Link
            href="/teacher/courses"
            className="inline-flex items-center gap-1 rounded-[var(--radius-sm)] text-[13px] font-medium text-[var(--color-primary-text)] underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 pointer-coarse:min-h-11"
          >
            {t("roster.viewAll")}
            <ArrowRight aria-hidden="true" className="size-3.5" />
          </Link>
        ) : null}
      </div>

      {shown.length === 0 ? (
        <p className="mt-3 border-t border-[var(--color-border)] pt-4 text-[14px] text-[var(--color-text-muted)]">
          {t("roster.empty")}
        </p>
      ) : (
        <ul className="mt-3 grid gap-px overflow-hidden border-t border-[var(--color-border)] sm:grid-cols-2 lg:grid-cols-3">
          {shown.map((course) => (
            <li key={course.id}>
              <Link
                href={`/teacher/courses/${course.id}`}
                className="flex h-full min-h-[92px] flex-col justify-center rounded-[var(--radius-md)] px-2 py-4 outline-none transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none"
              >
                <p className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
                  {course.code ?? course.name}
                </p>
                <p className="mt-0.5 truncate text-[14px] text-[var(--color-text-secondary)]">
                  {course.code ? course.name : ""}
                </p>
                <p className="mt-1.5 text-[12px] text-[var(--color-text-muted)]">
                  {courseLifecycle(course) === "published"
                    ? t("roster.updated", {
                        when: formatRelativeTime(course.updated_at),
                      })
                    : t(`status.${courseLifecycle(course)}`)}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
