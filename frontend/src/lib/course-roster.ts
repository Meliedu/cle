/**
 * Roster ordering and filtering (Plate 02).
 *
 *   Rows are ordered by next class and expose lifecycle, next session, venue,
 *   and the correct action.  […]  Sort by actionable chronology; status must
 *   change the verb: Open, Continue setup, or View.
 *
 * Pure so the ordering rules are testable without a network or a clock.
 */

import type { CourseResponse } from "@/hooks/use-courses";
import type { TeachingEntry } from "@/lib/teaching-day";
import {
  courseActionVerb,
  courseLifecycle,
  type CourseActionVerb,
  type CourseLifecycle,
} from "@/lib/contracts/state";

/** One roster row: a course plus the operational facts a teacher acts on. */
export interface RosterRow {
  readonly course: CourseResponse;
  readonly lifecycle: CourseLifecycle;
  readonly verb: CourseActionVerb;
  /** The next class for this course, or null when none is scheduled. */
  readonly nextClass: TeachingEntry | null;
}

export interface RosterFilters {
  /** Free text over code, name, and description. */
  readonly query: string;
  /** Exact term/semester match, or "" for all. */
  readonly term: string;
  /** Lifecycle filter, or "" for all. */
  readonly status: string;
}

export const EMPTY_FILTERS: RosterFilters = { query: "", term: "", status: "" };

/**
 * Build rows and order them by actionable chronology.
 *
 * Ordering, in priority order:
 *   1. Courses with a next class, soonest first. This is the operational
 *      question a teacher actually asks the roster.
 *   2. Courses with no next class but still active (draft/setup/published),
 *      because they may need work before they can be scheduled.
 *   3. Archived courses last, because nothing is expected of them.
 * Ties break on course code so the order is stable between renders.
 */
export function buildRoster(
  courses: readonly CourseResponse[],
  nextClassByCourse: ReadonlyMap<string, TeachingEntry>
): readonly RosterRow[] {
  const rows: RosterRow[] = courses.map((course) => {
    const lifecycle = courseLifecycle(course);
    return {
      course,
      lifecycle,
      verb: courseActionVerb(lifecycle),
      nextClass: nextClassByCourse.get(course.id) ?? null,
    };
  });

  return rows.sort((a, b) => {
    const aRank = orderRank(a);
    const bRank = orderRank(b);
    if (aRank !== bRank) return aRank - bRank;

    if (a.nextClass && b.nextClass) {
      const byTime = a.nextClass.at.localeCompare(b.nextClass.at);
      if (byTime !== 0) return byTime;
    }

    return label(a.course).localeCompare(label(b.course));
  });
}

function orderRank(row: RosterRow): number {
  if (row.lifecycle === "archived") return 2;
  return row.nextClass ? 0 : 1;
}

function label(course: CourseResponse): string {
  return course.code ?? course.name;
}

/** Apply the three filters. All are AND-ed; an empty value means "any". */
export function filterRoster(
  rows: readonly RosterRow[],
  filters: RosterFilters
): readonly RosterRow[] {
  const query = filters.query.trim().toLowerCase();

  return rows.filter((row) => {
    if (filters.status && row.lifecycle !== filters.status) return false;
    if (filters.term && (row.course.semester ?? "") !== filters.term) {
      return false;
    }
    if (query) {
      const haystack = [
        row.course.code,
        row.course.name,
        row.course.description,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      if (!haystack.includes(query)) return false;
    }
    return true;
  });
}

/** Distinct terms present on the roster, most recent first. */
export function termOptions(
  courses: readonly CourseResponse[]
): readonly string[] {
  const terms = new Set<string>();
  for (const course of courses) {
    if (course.semester) terms.add(course.semester);
  }
  // Descending so the current term sorts to the top of a "2025 Fall" /
  // "2026 Spring" style list.
  return Array.from(terms).sort((a, b) => b.localeCompare(a));
}

/** Lifecycles actually present, in canonical order (not alphabetical). */
export function statusOptions(
  rows: readonly RosterRow[]
): readonly CourseLifecycle[] {
  const order: readonly CourseLifecycle[] = [
    "published",
    "setup",
    "draft",
    "archived",
  ];
  const present = new Set(rows.map((row) => row.lifecycle));
  return order.filter((value) => present.has(value));
}

export function hasActiveFilters(filters: RosterFilters): boolean {
  return Boolean(filters.query || filters.term || filters.status);
}
