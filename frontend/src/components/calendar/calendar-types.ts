import type { CalendarEvent } from "@/hooks/use-calendar";

/**
 * Shared vocabulary for the full-calendar surface. The page aggregates every
 * course the signed-in user can see, so each raw `CalendarEvent` is tagged with
 * the course it came from plus a stable color slot for the grid legend.
 */

/** A calendar feed event tagged with its owning course + a legend color slot. */
export interface CourseCalendarEvent {
  readonly event: CalendarEvent;
  readonly courseId: string;
  readonly courseCode: string;
  readonly courseName: string;
  /** Index into `COURSE_PALETTE` (assigned by course order, cycled). */
  readonly colorIndex: number;
}

/** One legend entry: a course + its assigned color slot + a toggle state. */
export interface CalendarLegendCourse {
  readonly courseId: string;
  readonly courseCode: string;
  readonly courseName: string;
  readonly colorIndex: number;
}

/** Which grid the calendar is showing. */
export type CalendarViewMode = "month" | "week";

/**
 * Token-driven color slots for per-course event treatment. Cycled by course
 * order so a stable course always reads the same hue across month + week grids
 * and the legend. Every value references a `tokens.css` custom property — no raw
 * hex. `dot`/`block`/`text`/`border` are Tailwind arbitrary-value class strings.
 */
export interface CoursePaletteSlot {
  /** Small filled dot on a month cell. */
  readonly dot: string;
  /** Soft tinted background for a week/detail event block. */
  readonly block: string;
  /** Left accent bar / border for an event block. */
  readonly border: string;
  /** Legend swatch background. */
  readonly swatch: string;
}

export const COURSE_PALETTE: readonly CoursePaletteSlot[] = [
  {
    dot: "bg-[var(--color-primary)]",
    block: "bg-[var(--color-primary-light)]",
    border: "border-l-[var(--color-primary)]",
    swatch: "bg-[var(--color-primary)]",
  },
  {
    dot: "bg-[var(--color-accent)]",
    block: "bg-[var(--color-accent-light)]",
    border: "border-l-[var(--color-accent)]",
    swatch: "bg-[var(--color-accent)]",
  },
  {
    dot: "bg-[var(--color-coral)]",
    block: "bg-[var(--color-coral-soft)]",
    border: "border-l-[var(--color-coral)]",
    swatch: "bg-[var(--color-coral)]",
  },
  {
    dot: "bg-[var(--color-olive)]",
    block: "bg-[var(--color-primary-light)]",
    border: "border-l-[var(--color-olive)]",
    swatch: "bg-[var(--color-olive)]",
  },
  {
    dot: "bg-[var(--color-gold)]",
    block: "bg-[var(--color-cream)]",
    border: "border-l-[var(--color-gold)]",
    swatch: "bg-[var(--color-gold)]",
  },
];

/** Palette slot for a color index (cycles safely for any course count). */
export function paletteSlot(colorIndex: number): CoursePaletteSlot {
  return COURSE_PALETTE[colorIndex % COURSE_PALETTE.length];
}

/** Local `HH:mm` for an event's ISO `at`, respecting the caller's locale. */
export function eventTime(at: string, locale: string): string {
  return new Date(at).toLocaleTimeString(locale, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Minutes-since-midnight for an event's start (used to place week blocks). */
export function minutesIntoDay(at: string): number {
  const d = new Date(at);
  return d.getHours() * 60 + d.getMinutes();
}
