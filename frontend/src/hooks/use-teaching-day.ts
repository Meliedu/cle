"use client";

import { useMemo } from "react";

import { useCalendarEvents } from "@/components/calendar/use-calendar-events";
import { useDocuments } from "@/hooks/use-documents";
import { toIsoDate } from "@/components/calendar/calendar-date-math";
import {
  documentReadiness,
  resolveTeachingDay,
  toTeachingEntry,
  type TeachingDay,
  type TeachingEntry,
} from "@/lib/teaching-day";
import { rollUpSources, type SourceRollup } from "@/lib/contracts/state";

/**
 * How far ahead the dashboard looks for the next class.
 *
 * The SAME window the roster uses (`ROSTER_LOOKAHEAD_DAYS`), for the same
 * reason the two share a feed: with different windows the roster row can show
 * "Next to teach: Sep 1" while the hero claims no class is scheduled at all,
 * which is a false claim, not an empty state. A 21-day hero window shipped
 * exactly that contradiction during a term break. The calendar feed caps at
 * 366 days server-side; nothing here approaches that.
 */
const LOOKAHEAD_DAYS = 120;

export interface TeachingDayResult extends TeachingDay {
  readonly isLoading: boolean;
}

/**
 * The dashboard's read of the shared calendar feed.
 *
 * This is deliberately the SAME `useCalendarEvents` fan-out the Calendar page
 * uses, hitting the same query keys, so the two surfaces cannot drift and the
 * dashboard never becomes a second event model (Plate 01, rule 2). The
 * dashboard renders it read-only; all editing stays on Calendar.
 */
export function useTeachingDay(now: Date): TeachingDayResult {
  const { from, to } = useMemo(() => {
    const start = new Date(now);
    start.setHours(0, 0, 0, 0);
    const end = new Date(start);
    end.setDate(end.getDate() + LOOKAHEAD_DAYS);
    return { from: toIsoDate(start), to: toIsoDate(end) };
  }, [now]);

  const { events, isLoading } = useCalendarEvents(from, to);

  // `now` is passed by the caller (stabilised there), so the resolution only
  // recomputes when the feed or the caller's clock tick changes.
  const day = useMemo(() => resolveTeachingDay(events, now), [events, now]);

  return { ...day, isLoading };
}

/**
 * How far ahead the roster looks when ordering courses by next class.
 *
 * Kept equal to the hero window BY CONSTRUCTION: if these differ, the hero and
 * the roster can disagree about whether a next class exists. A course whose
 * next class falls outside this window sorts into the unscheduled group.
 */
const ROSTER_LOOKAHEAD_DAYS = LOOKAHEAD_DAYS;

export interface CourseNextClasses {
  readonly nextClassByCourse: ReadonlyMap<string, TeachingEntry>;
  readonly isLoading: boolean;
}

/**
 * The soonest upcoming class for each course, keyed by course id.
 *
 * Reuses the same fanned-out calendar feed as everything else, so the roster's
 * idea of "next class" is by construction the same one the dashboard hero and
 * the Calendar page hold.
 */
export function useCourseNextClasses(now?: Date): CourseNextClasses {
  const anchor = useMemo(() => now ?? new Date(), [now]);

  const { from, to } = useMemo(() => {
    const start = new Date(anchor);
    start.setHours(0, 0, 0, 0);
    const end = new Date(start);
    end.setDate(end.getDate() + ROSTER_LOOKAHEAD_DAYS);
    return { from: toIsoDate(start), to: toIsoDate(end) };
  }, [anchor]);

  const { events, isLoading } = useCalendarEvents(from, to);

  const nextClassByCourse = useMemo(() => {
    const nowMs = anchor.getTime();
    const map = new Map<string, TeachingEntry>();

    for (const tagged of events) {
      if (tagged.event.kind !== "meeting") continue;
      const entry = toTeachingEntry(tagged);
      const startMs = new Date(entry.at).getTime();
      const endMs = startMs + (entry.durationMinutes ?? 0) * 60_000;
      // A class already under way is still this course's next class.
      if (endMs < nowMs) continue;

      const existing = map.get(entry.courseId);
      if (!existing || entry.at.localeCompare(existing.at) < 0) {
        map.set(entry.courseId, entry);
      }
    }
    return map;
  }, [events, anchor]);

  return { nextClassByCourse, isLoading };
}

export interface CourseSourceReadiness extends SourceRollup {
  readonly isLoading: boolean;
}

/**
 * Source readiness for one course, rolled up from its documents.
 *
 * Scoped to a single course on purpose: the dashboard hero needs readiness for
 * the ONE course it is about to teach, not for every course on the roster.
 * Fanning documents out across the whole roster would be a large read for
 * information no surface displays.
 */
export function useCourseSourceReadiness(
  courseId: string | null
): CourseSourceReadiness {
  const { data, isLoading } = useDocuments(courseId ?? "");

  return useMemo(() => {
    if (!courseId || !data) {
      return {
        total: 0,
        ready: 0,
        inFlight: 0,
        needsAttention: 0,
        blocking: 0,
        isLoading: Boolean(courseId) && isLoading,
      };
    }
    const rollup = rollUpSources(
      data.map((document) => documentReadiness(document.status))
    );
    return { ...rollup, isLoading: false };
  }, [courseId, data, isLoading]);
}
