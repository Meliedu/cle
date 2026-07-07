/**
 * Pure date helpers for the full month/week calendar grids (F8). No React, no
 * locale strings — just the arithmetic the grids and the API window depend on.
 * Kept side-effect free and framework-agnostic so the month matrix math can be
 * unit-tested in isolation (the calendar's trickiest bit).
 *
 * Weeks start on Monday (`weekStartsOn = 1`) to match the existing
 * `MiniCalendar` (`react-day-picker weekStartsOn={1}`).
 */

/** ISO days are 0=Sun..6=Sat; our grid weeks start Monday. */
const WEEK_START = 1;
const DAYS_IN_WEEK = 7;

/** Local `yyyy-mm-dd` for a date (calendar day, not UTC). */
export function toIsoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** Midnight of the given calendar day (new instance — never mutates input). */
export function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

/** True when both dates fall on the same calendar day. */
export function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/** True when `d` sits in the same month/year as `anchor`. */
export function isSameMonth(d: Date, anchor: Date): boolean {
  return (
    d.getFullYear() === anchor.getFullYear() &&
    d.getMonth() === anchor.getMonth()
  );
}

/** `d` shifted by `n` calendar days (n may be negative). */
export function addDays(d: Date, n: number): Date {
  const next = startOfDay(d);
  next.setDate(next.getDate() + n);
  return next;
}

/** `d` shifted by `n` weeks. */
export function addWeeks(d: Date, n: number): Date {
  return addDays(d, n * DAYS_IN_WEEK);
}

/**
 * `d` shifted by `n` months, clamped to the last valid day of the target month
 * (e.g. Jan 31 + 1 month → Feb 28/29, never spilling into March).
 */
export function addMonths(d: Date, n: number): Date {
  const target = new Date(d.getFullYear(), d.getMonth() + n, 1);
  const lastDay = new Date(
    target.getFullYear(),
    target.getMonth() + 1,
    0
  ).getDate();
  target.setDate(Math.min(d.getDate(), lastDay));
  return target;
}

/** Monday of the week containing `d`. */
export function startOfWeek(d: Date): Date {
  const start = startOfDay(d);
  const diff = (start.getDay() - WEEK_START + DAYS_IN_WEEK) % DAYS_IN_WEEK;
  return addDays(start, -diff);
}

/** First calendar day of `d`'s month. */
export function startOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

/** Last calendar day of `d`'s month. */
export function endOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth() + 1, 0);
}

/** The seven days (Mon→Sun) of the week containing `anchor`. */
export function buildWeekDays(anchor: Date): readonly Date[] {
  const start = startOfWeek(anchor);
  return Array.from({ length: DAYS_IN_WEEK }, (_, i) => addDays(start, i));
}

/**
 * The month grid as full Monday→Sunday weeks covering every day of `anchor`'s
 * month (leading/trailing days spill from the adjacent months so every row has
 * exactly seven cells). Returns whole weeks — 4, 5, or 6 rows depending on the
 * month.
 */
export function buildMonthMatrix(anchor: Date): readonly (readonly Date[])[] {
  const firstCell = startOfWeek(startOfMonth(anchor));
  const lastOfMonth = endOfMonth(anchor);
  const weeks: Date[][] = [];

  let cursor = firstCell;
  // Emit whole weeks until we've covered the final day of the month.
  do {
    const week = Array.from({ length: DAYS_IN_WEEK }, (_, i) =>
      addDays(cursor, i)
    );
    weeks.push(week);
    cursor = addDays(cursor, DAYS_IN_WEEK);
  } while (cursor <= lastOfMonth);

  return weeks;
}

/** Half-open `[from, to)` ISO-date window spanning the visible month matrix. */
export function monthRange(anchor: Date): { readonly from: string; readonly to: string } {
  const matrix = buildMonthMatrix(anchor);
  const firstCell = matrix[0][0];
  const lastWeek = matrix[matrix.length - 1];
  const lastCell = lastWeek[lastWeek.length - 1];
  return { from: toIsoDate(firstCell), to: toIsoDate(addDays(lastCell, 1)) };
}

/** Half-open `[from, to)` ISO-date window spanning the visible week. */
export function weekRange(anchor: Date): { readonly from: string; readonly to: string } {
  const days = buildWeekDays(anchor);
  const first = days[0];
  const last = days[days.length - 1];
  return { from: toIsoDate(first), to: toIsoDate(addDays(last, 1)) };
}
