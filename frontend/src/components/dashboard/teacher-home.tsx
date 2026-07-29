"use client";

import { useMemo } from "react";
import { useLocale, useTranslations } from "next-intl";

import { Skeleton } from "@/components/ui/skeleton";
import { useUser } from "@/hooks/use-auth";
import { useCourses } from "@/hooks/use-courses";
import {
  useCourseSourceReadiness,
  useTeachingDay,
} from "@/hooks/use-teaching-day";
import { NextTeachingHero } from "@/components/dashboard/next-teaching-hero";
import { LaterToday } from "@/components/dashboard/later-today";
import { TeachingRoster } from "@/components/dashboard/teaching-roster";
import { DayRail } from "@/components/dashboard/day-rail";

const HONORIFIC = /^(dr|prof|mr|mrs|ms|mx|sir|madam)\.?$/i;

/** First given name, skipping a leading honorific ("Dr. Wei Chen" → "Wei"). */
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
 * The teacher command surface (Plate 01).
 *
 * Composition, top to bottom: greeting, then the ONE next teaching action as
 * the dominant object, then later-today work and the roster as compact
 * subordinate regions, with a read-only day rail alongside.
 *
 * What is deliberately absent, versus the previous dashboard:
 *   - The to-do widget no longer takes the largest work surface. Local chores
 *     never outrank the next class (rule 1).
 *   - There is no second calendar. The rail reads the shared event model and
 *     cannot edit it (rule 2).
 *   - There is exactly one filled button on the page (rule 3).
 */
export function TeacherHome() {
  const t = useTranslations("teacher.home");
  const locale = useLocale();
  const { user } = useUser();
  const { data: courses, isLoading: coursesLoading } = useCourses();

  // One clock read per mount. A ticking clock would re-resolve the whole day on
  // every tick and would fight the reduced-motion requirement for status.
  const now = useMemo(() => new Date(), []);

  const { next, laterToday, afterThis, isLoading: dayLoading } =
    useTeachingDay(now);

  // Readiness is fetched only for the course we are about to teach.
  const sources = useCourseSourceReadiness(next?.entry.courseId ?? null);

  const courseList = useMemo(() => courses ?? [], [courses]);
  const firstName = firstNameFrom(user?.firstName, user?.fullName);

  if (coursesLoading || dayLoading) return <TeacherHomeSkeleton />;

  const focusDay = next ? new Date(next.entry.at) : now;

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
                count: courseList.length,
              })}
            </p>
          </header>

          <NextTeachingHero
            next={next}
            sources={sources}
            sourcesLoading={sources.isLoading}
          />

          <LaterToday entries={laterToday} />

          <TeachingRoster courses={courseList} />
        </div>

        <DayRail
          today={now}
          focus={focusDay}
          entries={afterThis}
          hasClass={next !== null}
          calendarHref="/teacher/calendar"
        />
      </div>
    </div>
  );
}

function TeacherHomeSkeleton() {
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
            <Skeleton className="h-[60px]" />
            <Skeleton className="h-[60px]" />
          </div>
          <div className="space-y-3">
            <Skeleton className="h-4 w-32" />
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 3 }).map((_, index) => (
                <Skeleton key={index} className="h-[92px]" />
              ))}
            </div>
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
