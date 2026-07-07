"use client";

import { useAuthedQuery } from "@/hooks/use-authed-query";
import type { WorkItemSourceKind, WorkItemStatus } from "@/hooks/use-work-items";

/**
 * TanStack hook over the merged course calendar feed (P4 backend B7). The feed
 * flattens THREE independent sources — meetings, assignments, and work_items —
 * into one `kind`-discriminated event list sorted by `at`, gated by the
 * student-or-owner `_accessible_course` guard. A student additionally sees their
 * own `work_item_progress.status` overlay on `work_item` events; a teacher does
 * not. Read-only; no mutations here (the sources are authored elsewhere).
 */

// ----- types (mirror backend `meetings.py::calendar_feed`) -----

/** A `course_meetings` row surfaced on the calendar. */
export interface CalendarMeetingEvent {
  readonly id: string;
  readonly kind: "meeting";
  readonly title: string;
  readonly at: string;
  readonly duration_minutes: number | null;
  readonly location: string | null;
  readonly status: string;
}

/** A Canvas/synced assignment surfaced on the calendar. */
export interface CalendarAssignmentEvent {
  readonly id: string;
  readonly kind: "assignment";
  readonly title: string;
  readonly at: string;
  readonly assignment_kind: string;
  readonly weight: number | null;
}

/**
 * A work_item surfaced on the calendar by its `due_at`/`close_at`. `status` is
 * present only for a student (their own `work_item_progress` overlay); a teacher
 * sees the same event without it.
 */
export interface CalendarWorkItemEvent {
  readonly id: string;
  readonly kind: "work_item";
  readonly title: string;
  readonly at: string;
  readonly source_kind: WorkItemSourceKind;
  readonly required: boolean;
  readonly status?: WorkItemStatus;
}

/** The `kind`-discriminated union the calendar feed emits. */
export type CalendarEvent =
  | CalendarMeetingEvent
  | CalendarAssignmentEvent
  | CalendarWorkItemEvent;

export const calendarKeys = {
  feed: (courseId: string, from: string, to: string) =>
    ["calendar", courseId, from, to] as const,
};

/**
 * GET `/courses/{id}/calendar?from_date&to_date` — every meeting, assignment,
 * and in-window work_item as a flat, `at`-sorted event list. `from`/`to` are
 * ISO date/datetime bounds; the backend enforces `from < to` and a 366-day cap.
 * The query stays disabled until all three of `courseId`/`from`/`to` are set.
 */
export function useCalendar(courseId: string, from: string, to: string) {
  return useAuthedQuery<readonly CalendarEvent[]>({
    queryKey: calendarKeys.feed(courseId, from, to),
    path: `/courses/${courseId}/calendar?from_date=${encodeURIComponent(
      from
    )}&to_date=${encodeURIComponent(to)}`,
    enabled: Boolean(courseId && from && to),
  });
}
