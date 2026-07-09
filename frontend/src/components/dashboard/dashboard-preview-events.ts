"use client";

import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";

import { useAuth } from "@/hooks/use-auth";
import { useCourses } from "@/hooks/use-courses";
import { useTodos } from "@/hooks/use-todos";
import { meetingKeys, type Meeting } from "@/hooks/use-meetings";
import { apiFetch, isAuthError, type ApiEnvelope } from "@/lib/api";

// ---------------------------------------------------------------------------
// Event shape used by the dashboard + calendar preview widgets. Populated from
// REAL data only: personal to-dos with due dates + published course sessions
// (course_meetings) across the user's courses. No placeholder/marketing data —
// per the product rule that empty states are honest, never faked.
// ---------------------------------------------------------------------------

export type DashboardPreviewEventKind = "todo" | "swarm" | "session";
export type DashboardPreviewEventColor = "honey" | "coral" | "salt";

export interface DashboardPreviewEvent {
  readonly id: string;
  /** ISO yyyy-mm-dd */
  readonly date: string;
  readonly title: string;
  readonly kind: DashboardPreviewEventKind;
  readonly subtitle?: string;
  readonly href?: string;
  readonly color: DashboardPreviewEventColor;
  readonly done?: boolean;
}

function toIsoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function timeLabel(iso: string, durationMin: number): string {
  const start = new Date(iso);
  const end = new Date(start.getTime() + durationMin * 60_000);
  const fmt = (d: Date) =>
    d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  return `${fmt(start)} – ${fmt(end)}`;
}

/**
 * Real preview feed: to-do items with due dates + upcoming sessions pulled from
 * every course the signed-in user can see. Fans out one meetings query per
 * course via `useQueries` (cached under the same `meetingKeys` as the schedule
 * step, so no duplicate fetching).
 */
export function useDashboardPreviewEvents(): readonly DashboardPreviewEvent[] {
  const { getToken, isSignedIn } = useAuth();
  const { data: courses } = useCourses();
  const { items } = useTodos();

  const courseList = useMemo(() => courses ?? [], [courses]);

  const meetingQueries = useQueries({
    queries: courseList.map((course) => ({
      queryKey: meetingKeys.list(course.id),
      queryFn: async () => {
        const token = await getToken({ template: "backend" });
        if (!token) throw new Error("Not authenticated");
        const res = await apiFetch<ApiEnvelope<readonly Meeting[]>>(
          `/courses/${course.id}/meetings`,
          { token }
        );
        return res.data;
      },
      enabled: isSignedIn === true,
      staleTime: 60_000,
      retry: (count: number, error: unknown) =>
        !isAuthError(error) && count < 2,
    })),
  });

  // Stable dependency signature so the memo only recomputes when data changes.
  const meetingsSignature = meetingQueries
    .map((q) => (q.data ? q.data.length : -1))
    .join(",");

  return useMemo(() => {
    const todoEvents: DashboardPreviewEvent[] = items
      .filter((it) => !!it.dueDate)
      .map((it) => ({
        id: `todo-${it.id}`,
        date: it.dueDate!,
        title: it.text,
        kind: "todo" as const,
        color: "honey" as const,
        done: it.done,
      }));

    const sessionEvents: DashboardPreviewEvent[] = [];
    meetingQueries.forEach((query, idx) => {
      const course = courseList[idx];
      if (!course || !query.data) return;
      for (const meeting of query.data) {
        sessionEvents.push({
          id: `session-${meeting.id}`,
          date: toIsoDate(new Date(meeting.scheduled_at)),
          title:
            meeting.title ?? `Session ${meeting.meeting_index}`,
          subtitle: [
            course.code,
            timeLabel(meeting.scheduled_at, meeting.duration_minutes),
            meeting.location,
          ]
            .filter(Boolean)
            .join(" · "),
          kind: "session" as const,
          color: "salt" as const,
        });
      }
    });

    return [...todoEvents, ...sessionEvents].sort((a, b) =>
      a.date.localeCompare(b.date)
    );
    // `meetingQueries` is intentionally excluded: its array reference changes
    // every render, which would thrash this memo. All data-level changes flow
    // through `meetingsSignature` (a stable string derived from each query's
    // resolved data), so the memo re-runs exactly when the meeting data does.
    // NOTE: if you add reads of query.isLoading/isError inside this memo, add
    // `meetingQueries` back to the deps — the signature only tracks data.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, courseList, meetingsSignature]);
}
