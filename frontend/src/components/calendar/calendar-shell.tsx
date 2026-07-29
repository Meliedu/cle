"use client";

import { useCallback, useMemo } from "react";
import { useLocale, useTranslations } from "next-intl";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { useUrlState } from "@/hooks/use-url-state";

import type {
  CalendarLegendCourse,
  CalendarViewMode,
  CourseCalendarEvent,
} from "./calendar-types";
import { paletteSlot } from "./calendar-types";
import { useCalendarEvents } from "./use-calendar-events";
import { MonthGrid } from "./month-grid";
import { WeekGrid } from "./week-grid";
import { CalendarDaySidebar } from "./calendar-day-sidebar";
import { EventDetailDrawer } from "./event-detail-drawer";
import {
  addMonths,
  addWeeks,
  buildWeekDays,
  monthRange,
  startOfDay,
  toIsoDate,
  weekRange,
} from "./calendar-date-math";

/**
 * The single temporal authority (Plate 03).
 *
 * Three things the handoff requires, and where they live:
 *
 *   1. "Navigation and view mode sit in the calendar header with course legend
 *      directly above the grid." Period nav, Today, and Month/Week are inside
 *      the grid card's own header; the legend sits between the page header and
 *      the card.
 *   2. "Use one calendar state owner for date, view, and filters; do not mirror
 *      independent copies on Dashboard." Date, view, selection, and hidden
 *      courses all live in the URL (`useUrlState`), so this component is the
 *      only writer and the dashboard is a read-only consumer of the same feed.
 *   3. "Render an intentional empty state." A month with no events still
 *      renders its month. Only the agenda says the day is clear; the grid
 *      never disappears, because a calendar that vanishes when empty stops
 *      being an authority over time.
 */

/**
 * URL keys this surface owns, including the open-event key. Listing every
 * key it writes is what lets a future reset clear the view completely rather
 * than leaving a stale `event` behind.
 */
export const CALENDAR_URL_KEYS = ["view", "date", "day", "hide", "event"] as const;

interface CalendarShellProps {
  /** Right-aligned action for the page header (e.g. "Add event"). */
  readonly actions?: React.ReactNode;
}

export function CalendarShell({ actions }: CalendarShellProps) {
  const t = useTranslations("patterns.calendar");
  const locale = useLocale();
  const url = useUrlState();

  const today = useMemo(() => startOfDay(new Date()), []);

  // ---- state, owned entirely by the URL -----------------------------------
  const view: CalendarViewMode = url.get("view") === "week" ? "week" : "month";
  const anchor = parseDate(url.get("date"), today);
  const selected = parseDate(url.get("day"), today);
  const hidden = useMemo<ReadonlySet<string>>(() => {
    const raw = url.get("hide");
    return new Set(raw ? raw.split(",").filter(Boolean) : []);
  }, [url]);

  const { from, to } = useMemo(
    () => (view === "month" ? monthRange(anchor) : weekRange(anchor)),
    [view, anchor]
  );

  const { events, courses, isLoading } = useCalendarEvents(from, to);

  const visibleEvents = useMemo(
    () => events.filter((item) => !hidden.has(item.courseId)),
    [events, hidden]
  );

  const eventsByDay = useMemo(() => {
    const map = new Map<string, CourseCalendarEvent[]>();
    for (const item of visibleEvents) {
      const iso = toIsoDate(new Date(item.event.at));
      const bucket = map.get(iso);
      if (bucket) bucket.push(item);
      else map.set(iso, [item]);
    }
    return map;
  }, [visibleEvents]);

  const selectedDayEvents = eventsByDay.get(toIsoDate(selected)) ?? [];

  // ---- writers -------------------------------------------------------------
  const shift = useCallback(
    (direction: -1 | 1) => {
      const next =
        view === "month"
          ? addMonths(anchor, direction)
          : addWeeks(anchor, direction);
      url.set("date", toIsoDate(next));
    },
    [anchor, url, view]
  );

  const goToday = useCallback(() => {
    url.setMany({ date: null, day: null });
  }, [url]);

  const setView = useCallback(
    (mode: CalendarViewMode) => {
      url.set("view", mode === "month" ? null : mode);
    },
    [url]
  );

  const selectDate = useCallback(
    (date: Date) => {
      url.set("day", toIsoDate(date));
    },
    [url]
  );

  const toggleCourse = useCallback(
    (courseId: string) => {
      const next = new Set(hidden);
      if (next.has(courseId)) next.delete(courseId);
      else next.add(courseId);
      url.set("hide", next.size ? Array.from(next).join(",") : null);
    },
    [hidden, url]
  );

  const showAllCourses = useCallback(() => url.set("hide", null), [url]);

  const periodLabel =
    view === "month"
      ? anchor.toLocaleDateString(locale, { month: "long", year: "numeric" })
      : formatWeekLabel(anchor, locale);

  return (
    <div className="flex flex-col gap-5">
      {actions ? (
        <div className="flex justify-end lg:hidden">{actions}</div>
      ) : null}

      {/* Legend sits directly above the grid, not scattered in a toolbar. */}
      {courses.length > 1 ? (
        <CourseLegend
          courses={courses}
          hidden={hidden}
          onToggle={toggleCourse}
          onShowAll={showAllCourses}
        />
      ) : null}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
        <section className="min-w-0 overflow-hidden rounded-[var(--radius-2xl)] border border-[var(--color-border)] bg-[var(--color-surface)]">
          {/* Navigation + view mode, inside the calendar header. */}
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] px-4 py-3">
            <div className="flex items-center gap-1">
              <NavButton label={t("prev")} onClick={() => shift(-1)}>
                <ChevronLeft aria-hidden="true" className="size-4" />
              </NavButton>
              <button
                type="button"
                onClick={goToday}
                className="h-11 rounded-[var(--radius-md)] border border-[var(--color-border)] px-3 text-[13px] font-medium text-[var(--color-text)] outline-none transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none"
              >
                {t("today")}
              </button>
              <NavButton label={t("next")} onClick={() => shift(1)}>
                <ChevronRight aria-hidden="true" className="size-4" />
              </NavButton>
            </div>

            <h2
              aria-live="polite"
              className="order-last w-full text-center text-[17px] font-semibold tracking-tight text-[var(--color-text)] sm:order-none sm:w-auto"
            >
              {periodLabel}
            </h2>

            <div
              role="tablist"
              aria-label={t("viewLabel")}
              className="inline-flex items-center gap-1 rounded-[var(--radius-lg)] border border-[var(--color-border)] p-1"
            >
              {(["month", "week"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  role="tab"
                  aria-selected={view === mode}
                  onClick={() => setView(mode)}
                  className={cn(
                    "h-11 rounded-[var(--radius-md)] px-4 text-[13px] font-medium outline-none transition-colors duration-[var(--duration-fast)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none",
                    view === mode
                      ? "bg-[var(--color-primary)] text-[var(--color-text-on-primary)]"
                      : "text-[var(--color-text-secondary)] hover:text-[var(--color-text)]"
                  )}
                >
                  {t(`view.${mode}`)}
                </button>
              ))}
            </div>
          </div>

          {/*
            The grid always renders. An empty month is a real month, and hiding
            it would break the calendar's job as the authority over time.
          */}
          {isLoading ? (
            <Skeleton className="m-4 h-[520px] rounded-[var(--radius-xl)]" />
          ) : view === "month" ? (
            <MonthGrid
              anchor={anchor}
              today={today}
              selected={selected}
              eventsByDay={eventsByDay}
              onSelectDate={selectDate}
            />
          ) : (
            <WeekGrid
              anchor={anchor}
              today={today}
              eventsByDay={eventsByDay}
              onOpenEvent={(item) => selectDate(new Date(item.event.at))}
            />
          )}

          {!isLoading && visibleEvents.length === 0 ? (
            <p className="border-t border-[var(--color-border)] px-4 py-3 text-[13px] text-[var(--color-text-muted)]">
              {view === "month" ? t("monthEmpty") : t("weekEmpty")}
            </p>
          ) : null}
        </section>

        <CalendarDaySidebar
          selected={selected}
          events={selectedDayEvents}
          onOpenEvent={(item) => url.set("event", item.event.id)}
        />
      </div>

      <EventDetailDrawer
        selected={
          visibleEvents.find((item) => item.event.id === url.get("event")) ??
          null
        }
        onClose={() => url.set("event", null)}
      />
    </div>
  );
}

interface NavButtonProps {
  readonly label: string;
  readonly onClick: () => void;
  readonly children: React.ReactNode;
}

function NavButton({ label, onClick, children }: NavButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="flex size-11 items-center justify-center rounded-[var(--radius-md)] border border-[var(--color-border)] text-[var(--color-text-secondary)] outline-none transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none"
    >
      {children}
    </button>
  );
}

interface CourseLegendProps {
  readonly courses: readonly CalendarLegendCourse[];
  readonly hidden: ReadonlySet<string>;
  readonly onToggle: (courseId: string) => void;
  readonly onShowAll: () => void;
}

/**
 * Course legend.
 *
 * Color here is supplementary (Plate 03, rule 2): the course code is always
 * spelled out, and a hidden course is struck through as well as dimmed, so the
 * filter state does not depend on perceiving the swatch.
 */
function CourseLegend({
  courses,
  hidden,
  onToggle,
  onShowAll,
}: CourseLegendProps) {
  const t = useTranslations("patterns.calendar");
  const shown = courses.length - hidden.size;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--color-text-muted)]">
        {t("legend.label")}
      </span>
      {courses.map((course) => {
        const isHidden = hidden.has(course.courseId);
        return (
          <button
            key={course.courseId}
            type="button"
            aria-pressed={!isHidden}
            onClick={() => onToggle(course.courseId)}
            className={cn(
              "inline-flex h-11 items-center gap-1.5 rounded-[var(--radius-pill)] px-3.5 text-[13px] font-medium outline-none transition-colors duration-[var(--duration-fast)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none",
              isHidden
                ? "text-[var(--color-text-muted)] line-through hover:bg-[var(--color-surface-hover)]"
                : "text-[var(--color-text)] hover:bg-[var(--color-surface-hover)]"
            )}
          >
            <span
              aria-hidden="true"
              className={cn(
                "size-2 shrink-0 rounded-full",
                paletteSlot(course.colorIndex).swatch,
                isHidden && "opacity-30"
              )}
            />
            {course.courseCode}
          </button>
        );
      })}
      {hidden.size > 0 ? (
        <button
          type="button"
          onClick={onShowAll}
          className="ml-1 inline-flex h-11 items-center rounded-[var(--radius-md)] px-2 text-[13px] font-medium text-[var(--color-primary-hover)] underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40"
        >
          {t("showAll")}
          <span className="sr-only">
            {" "}
            {t("filterHint", { shown, total: courses.length })}
          </span>
        </button>
      ) : null}
    </div>
  );
}

/** Parse a `YYYY-MM-DD` URL value, falling back when absent or malformed. */
function parseDate(value: string, fallback: Date): Date {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return fallback;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(year, month - 1, day);
  return Number.isNaN(parsed.getTime()) ? fallback : startOfDay(parsed);
}

/** "22 – 28 June 2026" style label for the visible week. */
function formatWeekLabel(anchor: Date, locale: string): string {
  const days = buildWeekDays(anchor);
  const first = days[0];
  const last = days[days.length - 1];
  const sameMonth = first.getMonth() === last.getMonth();
  const dayFmt = new Intl.DateTimeFormat(locale, { day: "numeric" });
  const fullFmt = new Intl.DateTimeFormat(locale, {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  return sameMonth
    ? `${dayFmt.format(first)} – ${fullFmt.format(last)}`
    : `${fullFmt.format(first)} – ${fullFmt.format(last)}`;
}
