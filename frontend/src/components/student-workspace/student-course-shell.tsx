"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { PageHeader, StateBanner } from "@/components/patterns";
import { Skeleton } from "@/components/ui/skeleton";
import { courseTitle, displayLanguage } from "@/lib/format";
import { useCourse } from "@/hooks/use-courses";

interface StudentCourseShellProps {
  readonly courseId: string;
  readonly children: ReactNode;
}

/**
 * Shared chrome for the student course-detail workspace: a `PageHeader` with
 * the course title + code/term/language. Each page renders its content as
 * `children`. This is the student mirror of `course-workspace-shell.tsx`; the
 * teacher shell is intentionally not reused so the two lanes can diverge.
 *
 * Deliberately NO tab row: removal rule 05 makes the course rail the only
 * course navigation system, for the student lane exactly as for the teacher
 * lane. A second horizontal nav drifted out of sync with the rail (each
 * listed destinations the other did not), which is the duplicate-navigation
 * failure the handoff removes. Checklist and Schedule stay reachable from the
 * overview's next-action button and quick links.
 */
export function StudentCourseShell({
  courseId,
  children,
}: StudentCourseShellProps) {
  const t = useTranslations("student.workspace");
  const { data: course, isLoading } = useCourse(courseId);

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

  // The code leads the meta line, so the title must not repeat it (course
  // names in the wild often embed their code).
  const meta = [
    course.code,
    course.semester,
    course.language ? displayLanguage(course.language) : null,
  ]
    .filter((v): v is string => Boolean(v))
    .join(" · ");

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title={courseTitle(course.code, course.name)}
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

      {children}
    </div>
  );
}
