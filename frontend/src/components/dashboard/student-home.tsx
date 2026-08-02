"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";

import { Skeleton } from "@/components/ui/skeleton";
import { courseTitle } from "@/lib/format";
import { useUser } from "@/hooks/use-auth";
import { useCourses } from "@/hooks/use-courses";
import { useLearningPath } from "@/hooks/use-learning-path";
import { useTeachingDay } from "@/hooks/use-teaching-day";
import { LearningActionHero } from "@/components/dashboard/learning-action-hero";
import { LearningQueue } from "@/components/dashboard/learning-queue";
import { DayRail } from "@/components/dashboard/day-rail";

const HONORIFIC = /^(dr|prof|mr|mrs|ms|mx|sir|madam)\.?$/i;

function firstNameFrom(
  firstName: string | null | undefined,
  fullName: string | null | undefined
): string | null {
  if (firstName && !HONORIFIC.test(firstName)) return firstName;
  if (!fullName) return null;
  const parts = fullName
    .trim()
    .split(/\s+/)
    .filter((part) => !HONORIFIC.test(part));
  return parts[0] ?? null;
}

/**
 * Student re-entry (Student 01).
 *
 *   01  Home resolves one recoverable next action with saved progress, source,
 *       due time, and a direct resume action.
 *   03  Calendar explains when; the course path explains what unlocks next.
 *       Do not duplicate sequence ownership.
 *
 * The rail therefore shows time only. It does not restate the learning
 * sequence, does not repeat lock reasons, and cannot start work: those belong
 * to the path on the left and to the course.
 */
export function StudentHome() {
  const t = useTranslations("student.home");
  const locale = useLocale();
  const { user } = useUser();
  const { data: courses, isLoading: coursesLoading } = useCourses();

  // One clock read per mount, shared by both resolutions.
  const now = useMemo(() => new Date(), []);

  const { next, rest, isLoading: pathLoading } = useLearningPath(now);
  const { afterThis, isLoading: dayLoading } = useTeachingDay(now);

  const courseList = useMemo(() => courses ?? [], [courses]);
  const firstName = firstNameFrom(user?.firstName, user?.fullName);

  if (coursesLoading || pathLoading) return <StudentHomeSkeleton />;

  const readyCount = next ? 1 + rest.filter((a) => a.availability.state === "available" && a.work !== "reviewed" && a.work !== "submitted").length : 0;

  return (
    <div className="mx-auto w-full max-w-[1400px] px-6 py-8 md:px-10 md:py-10">
      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-10">
          <header>
            <h1 className="text-[30px] font-semibold leading-tight tracking-[-0.02em] text-[var(--color-text)] md:text-[34px]">
              {firstName
                ? t("greeting", { name: firstName })
                : t("greetingFallback")}
            </h1>
            <p className="mt-1.5 text-[15px] text-[var(--color-text-secondary)]">
              {t("subtitle", {
                date: now.toLocaleDateString(locale, {
                  weekday: "long",
                  day: "numeric",
                  month: "long",
                }),
                count: readyCount,
              })}
            </p>
          </header>

          <LearningActionHero action={next} />

          <LearningQueue actions={rest} />

          <StudentCourses courses={courseList} />
        </div>

        <DayRail
          today={now}
          focus={now}
          entries={dayLoading ? [] : afterThis}
          hasClass={false}
          calendarHref="/student/calendar"
        />
      </div>
    </div>
  );
}

interface StudentCoursesProps {
  readonly courses: readonly { id: string; name: string; code: string | null }[];
}

function StudentCourses({ courses }: StudentCoursesProps) {
  const t = useTranslations("student.home");

  return (
    <section aria-labelledby="student-courses-title">
      <h2
        id="student-courses-title"
        className="text-[13px] font-semibold uppercase tracking-[0.1em] text-[var(--color-text-muted)]"
      >
        {t("yourCourses")}
      </h2>

      {courses.length === 0 ? (
        <div className="mt-3 border-t border-[var(--color-border)] pt-4">
          <p className="text-[14px] text-[var(--color-text-muted)]">
            {t("yourCoursesEmpty")}
          </p>
          <Link
            href="/student/join"
            className="mt-3 inline-flex h-11 items-center rounded-[var(--radius-md)] text-[14px] font-medium text-[var(--color-primary-text)] underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40"
          >
            {t("joinCourse")}
          </Link>
        </div>
      ) : (
        <ul className="mt-3 grid gap-px border-t border-[var(--color-border)] sm:grid-cols-2 lg:grid-cols-3">
          {courses.map((course) => (
            <li key={course.id}>
              <Link
                href={`/student/courses/${course.id}`}
                className="flex h-full min-h-[84px] flex-col justify-center rounded-[var(--radius-md)] px-2 py-4 outline-none transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none"
              >
                <p className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
                  {course.code ?? course.name}
                </p>
                {course.code ? (
                  <p className="mt-0.5 truncate text-[14px] text-[var(--color-text-secondary)]">
                    {courseTitle(course.code, course.name)}
                  </p>
                ) : null}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function StudentHomeSkeleton() {
  return (
    <div className="mx-auto w-full max-w-[1400px] px-6 py-8 md:px-10 md:py-10">
      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-10">
          <div className="space-y-3">
            <Skeleton className="h-9 w-72" />
            <Skeleton className="h-4 w-80" />
          </div>
          <Skeleton className="h-[228px] rounded-[var(--radius-2xl)]" />
          <div className="space-y-3">
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-[64px]" />
          </div>
        </div>
        <div className="space-y-6">
          <Skeleton className="h-[180px] rounded-[var(--radius-xl)]" />
          <Skeleton className="h-[240px] rounded-[var(--radius-xl)]" />
        </div>
      </div>
    </div>
  );
}
