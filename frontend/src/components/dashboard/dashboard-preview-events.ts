"use client";

import { useMemo } from "react";
import { useTodos } from "@/hooks/use-todos";

// ---------------------------------------------------------------------------
// Placeholder event shape used by dashboard preview widgets.
// These are self-contained here so the calendar page can use the real backend
// feed while the dashboard overview keeps showing illustrative data.
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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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
// Placeholder swarms data
// ---------------------------------------------------------------------------

export const DASHBOARD_UPCOMING_SWARMS: readonly DashboardPreviewEvent[] = [
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

// ---------------------------------------------------------------------------
// Hook: combines todo items (with due dates) + placeholder swarms
// ---------------------------------------------------------------------------

export function useDashboardPreviewEvents(): readonly DashboardPreviewEvent[] {
  const { items } = useTodos();

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

    return [...todoEvents, ...DASHBOARD_UPCOMING_SWARMS].sort((a, b) =>
      a.date.localeCompare(b.date)
    );
  }, [items]);
}
