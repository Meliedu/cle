"use client";

import { useMemo } from "react";
import { useTodos } from "@/hooks/use-todos";

export type CalendarEventKind = "todo" | "swarm" | "session";
export type CalendarEventColor = "honey" | "coral" | "salt";

export interface CalendarEvent {
  readonly id: string;
  readonly date: string; // ISO yyyy-mm-dd
  readonly title: string;
  readonly kind: CalendarEventKind;
  readonly subtitle?: string;
  readonly href?: string;
  readonly color: CalendarEventColor;
  readonly done?: boolean;
}

/**
 * Placeholder upcoming events. Clearly labelled "Preview" in every consuming
 * surface — replace with backend feed when live-session scheduling lands.
 */
export const UPCOMING_SWARMS: readonly CalendarEvent[] = [
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

export function useCalendarEvents(): readonly CalendarEvent[] {
  const { items } = useTodos();

  return useMemo(() => {
    const todoEvents: CalendarEvent[] = items
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
