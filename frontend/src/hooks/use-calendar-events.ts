"use client";

import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type { CalendarEvent } from "@/lib/curriculum-types";

export type { CalendarEvent };

// ---------------------------------------------------------------------------
// New API — used by Task 12 calendar page rewire
// ---------------------------------------------------------------------------

export function useCalendarEvents(
  courseId: string,
  fromDate: Date,
  toDate: Date
) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: [
      "calendar",
      courseId,
      fromDate.toISOString(),
      toDate.toISOString(),
    ],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const params = new URLSearchParams({
        from_date: fromDate.toISOString(),
        to_date: toDate.toISOString(),
      });
      const res = await apiFetch<ApiEnvelope<CalendarEvent[]>>(
        `/courses/${courseId}/calendar?${params}`,
        { token }
      );
      return res.data;
    },
  });
}

// ---------------------------------------------------------------------------
// TODO(task-12): remove everything below after calendar page is rebuilt.
// The legacy types and hook are kept only so that the existing dashboard page
// and calendar page continue to compile while Task 12 is pending.
// ---------------------------------------------------------------------------

export type CalendarEventKind = "todo" | "swarm" | "session";
export type CalendarEventColor = "honey" | "coral" | "salt";

/** @deprecated Use CalendarEvent from @/lib/curriculum-types instead. */
export interface LegacyCalendarEvent {
  readonly id: string;
  /** ISO yyyy-mm-dd */
  readonly date: string;
  readonly title: string;
  readonly kind: CalendarEventKind;
  readonly subtitle?: string;
  readonly href?: string;
  readonly color: CalendarEventColor;
  readonly done?: boolean;
}

/**
 * @deprecated Placeholder upcoming swarms. Replace with real backend data in
 * Task 12.
 */
export const UPCOMING_SWARMS: readonly LegacyCalendarEvent[] = [
  {
    id: "swarm-1",
    date: computeUpcoming(2),
    title: "Live Quiz · Cantonese Tones",
    subtitle: "10:00 – 11:30 · Room 2502A",
    kind: "swarm",
    color: "honey",
  },
  {
    id: "swarm-2",
    date: computeUpcoming(4),
    title: "Study Swarm · Mandarin Listening",
    subtitle: "14:00 – 15:00 · Online",
    kind: "swarm",
    color: "coral",
  },
  {
    id: "swarm-3",
    date: computeUpcoming(9),
    title: "Guest Swarm · Pronunciation Clinic",
    subtitle: "17:00 – 18:30 · LTH",
    kind: "swarm",
    color: "salt",
  },
] as const;

function computeUpcoming(daysAhead: number): string {
  const d = new Date();
  d.setDate(d.getDate() + daysAhead);
  return toIsoDate(d);
}

function toIsoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

// ---------------------------------------------------------------------------
// TODO(task-12): remove useLegacyCalendarEvents after calendar page is rebuilt
// ---------------------------------------------------------------------------
import { useMemo } from "react";
import { useTodos } from "@/hooks/use-todos";

/**
 * @deprecated Returns the old todo+placeholder-swarm shape. Task 12 will
 * replace callers with `useCalendarEvents`.
 */
export function useLegacyCalendarEvents(): readonly LegacyCalendarEvent[] {
  const { items } = useTodos();

  return useMemo(() => {
    const todoEvents: LegacyCalendarEvent[] = items
      .filter((it) => !!it.dueDate)
      .map((it) => ({
        id: `todo-${it.id}`,
        date: it.dueDate!,
        title: it.text,
        kind: "todo" as const,
        color: "honey" as const,
        done: it.done,
      }));

    return [...todoEvents, ...UPCOMING_SWARMS].sort((a, b) =>
      a.date.localeCompare(b.date)
    );
  }, [items]);
}
