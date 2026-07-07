"use client";

import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";

import { useAuth } from "@/hooks/use-auth";
import { useCourses } from "@/hooks/use-courses";
import { calendarKeys, type CalendarEvent } from "@/hooks/use-calendar";
import { apiFetch, isAuthError, type ApiEnvelope } from "@/lib/api";

import type { CalendarLegendCourse, CourseCalendarEvent } from "./calendar-types";

/**
 * Aggregates the merged calendar feed across EVERY course the signed-in user can
 * see, for the `[from, to)` window the active grid is showing. The per-course
 * `useCalendar` hook (F1) is single-course; the full calendar page spans all
 * courses, so this fans out one feed query per course via `useQueries` (cached
 * under the same `calendarKeys.feed` keys, so no duplicate fetching) and tags
 * each event with its course + a stable legend color slot — mirroring the
 * established `dashboard-preview-events.ts` fan-out.
 *
 * `from`/`to` are ISO date bounds; the queries stay disabled until both are set
 * and the user is signed in. Backend enforces `from < to` + the 366-day cap.
 */
export interface CalendarEventsResult {
  readonly events: readonly CourseCalendarEvent[];
  readonly courses: readonly CalendarLegendCourse[];
  readonly isLoading: boolean;
}

export function useCalendarEvents(from: string, to: string): CalendarEventsResult {
  const { getToken, isSignedIn } = useAuth();
  const { data: courses } = useCourses();

  const courseList = useMemo(() => courses ?? [], [courses]);

  const enabled = isSignedIn === true && Boolean(from && to);

  const feedQueries = useQueries({
    queries: courseList.map((course) => ({
      queryKey: calendarKeys.feed(course.id, from, to),
      queryFn: async () => {
        const token = await getToken({ template: "backend" });
        if (!token) throw new Error("Not authenticated");
        const res = await apiFetch<ApiEnvelope<readonly CalendarEvent[]>>(
          `/courses/${course.id}/calendar?from_date=${encodeURIComponent(
            from
          )}&to_date=${encodeURIComponent(to)}`,
          { token }
        );
        return res.data;
      },
      enabled,
      staleTime: 60_000,
      retry: (count: number, error: unknown) =>
        !isAuthError(error) && count < 2,
    })),
  });

  // Stable signature so the memo only recomputes when feed data changes.
  const signature = feedQueries
    .map((q) => (q.data ? q.data.length : -1))
    .join(",");

  const isLoading =
    enabled && courseList.length > 0 && feedQueries.some((q) => q.isLoading);

  const courseLegend = useMemo<readonly CalendarLegendCourse[]>(
    () =>
      courseList.map((course, index) => ({
        courseId: course.id,
        courseCode: course.code ?? course.name,
        courseName: course.name,
        colorIndex: index,
      })),
    [courseList]
  );

  const events = useMemo<readonly CourseCalendarEvent[]>(() => {
    const tagged: CourseCalendarEvent[] = [];
    feedQueries.forEach((query, index) => {
      const course = courseList[index];
      if (!course || !query.data) return;
      for (const event of query.data) {
        tagged.push({
          event,
          courseId: course.id,
          courseCode: course.code ?? course.name,
          courseName: course.name,
          colorIndex: index,
        });
      }
    });
    return tagged.sort((a, b) => a.event.at.localeCompare(b.event.at));
    // `signature` captures the meaningful change in the fanned-out query data.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseList, signature]);

  return { events, courses: courseLegend, isLoading };
}
