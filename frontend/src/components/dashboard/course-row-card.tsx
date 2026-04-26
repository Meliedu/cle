"use client";

import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { CourseResponse } from "@/hooks/use-courses";
import { CourseIllustration } from "@/components/dashboard/course-illustration";
import { formatRelativeTime } from "@/lib/format";

interface CourseRowCardProps {
  readonly course: CourseResponse;
  readonly className?: string;
}

export function CourseRowCard({ course, className }: CourseRowCardProps) {
  return (
    <Link
      href={`/dashboard/courses/${course.id}?tab=overview`}
      className={cn(
        "group relative flex w-full gap-4 rounded-[var(--radius-2xl)] border border-[var(--color-border)]/80 bg-[var(--color-surface)] p-3 transition-all duration-[var(--duration-normal)] hover:-translate-y-0.5 hover:border-[var(--color-border-hover)] hover:shadow-[var(--shadow-md)]",
        className
      )}
    >
      <CourseIllustration
        seed={course.id}
        language={course.language}
        className="shrink-0 overflow-hidden rounded-[var(--radius-xl)] size-[92px] sm:size-[104px]"
      />

      <div className="flex min-w-0 flex-1 flex-col py-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-[var(--radius-pill)] border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--color-text-secondary)]">
            {course.language}
          </span>
          {course.semester ? (
            <span className="text-[11px] font-medium text-[var(--color-text-muted)]">
              {course.semester}
            </span>
          ) : null}
          {course.code ? (
            <span className="text-[11px] font-medium text-[var(--color-text-muted)]">
              · {course.code}
            </span>
          ) : null}
        </div>

        <h3 className="mt-1 text-[15px] font-semibold leading-snug text-[var(--color-text)] line-clamp-2 transition-colors duration-[var(--duration-fast)] group-hover:text-[var(--color-primary-hover)]">
          {course.name}
        </h3>

        {course.description ? (
          <p className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
            {course.description}
          </p>
        ) : null}

        <div className="mt-auto pt-2 text-[11px] text-[var(--color-text-muted)]">
          Updated {formatRelativeTime(course.updated_at)}
        </div>
      </div>

      <span
        aria-hidden="true"
        className="absolute right-4 top-4 inline-flex size-7 items-center justify-center rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-muted)] opacity-0 transition-all duration-[var(--duration-fast)] group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:opacity-100"
      >
        <ArrowUpRight className="size-3.5" strokeWidth={2} />
      </span>
    </Link>
  );
}
