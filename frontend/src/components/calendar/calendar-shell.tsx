"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { CalendarX2, ChevronLeft, ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/patterns";

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
  isSameDay,
  monthRange,
  startOfDay,
  toIsoDate,
  weekRange,
} from "./calendar-date-math";

/**
 * The full-calendar surface shared by both role lanes. Owns the view mode
 * (month/week), the visible period anchor, the selected day, and the open event.
 * Fans the merged feed (meetings + assignments + work_items, Decision 5) across
 * every course via `useCalendarEvents`, lets the user toggle courses on/off in
 * the legend, and drives the month/week grids + day agenda + event drawer.
 */
export function CalendarShell() {
  const t = useTranslations("patterns.calendar");
  const locale = useLocale();

  const today = useMemo(() => startOfDay(new Date()), []);
  const [view, setView] = useState<CalendarViewMode>("month");
  const [anchor, setAnchor] = useState<Date>(today);
  const [selected, setSelected] = useState<Date>(today);
  const [openEvent, setOpenEvent] = useState<CourseCalendarEvent | null>(null);
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());

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

  function shift(direction: -1 | 1): void {
    setAnchor((prev) =>
      view === "month" ? addMonths(prev, direction) : addWeeks(prev, direction)
    );
  }

  function goToday(): void {
    setAnchor(today);
    setSelected(today);
  }

  function toggleCourse(courseId: string): void {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(courseId)) next.delete(courseId);
      else next.add(courseId);
      return next;
    });
  }

  const periodLabel =
    view === "month"
      ? anchor.toLocaleDateString(locale, { month: "long", year: "numeric" })
      : formatWeekLabel(anchor, locale);

  return (
    <div className="flex flex-col gap-4">
      <Toolbar
        periodLabel={periodLabel}
        view={view}
        onPrev={() => shift(-1)}
        onNext={() => shift(1)}
        onToday={goToday}
        onView={setView}
        t={t}
      />

      {courses.length > 1 ? (
        <CourseLegend
          courses={courses}
          hidden={hidden}
          onToggle={toggleCourse}
          t={t}
        />
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="min-w-0">
          {isLoading ? (
            <Skeleton className="h-[520px] rounded-[var(--radius-2xl)]" />
          ) : events.length === 0 ? (
            <EmptyState
              icon={CalendarX2}
              title={t("empty.title")}
              reason={t("empty.reason")}
              className="rounded-[var(--radius-2xl)] border border-[var(--color-border)] bg-[var(--color-surface)]"
            />
          ) : view === "month" ? (
            <MonthGrid
              anchor={anchor}
              today={today}
              selected={selected}
              eventsByDay={eventsByDay}
              onSelectDate={setSelected}
            />
          ) : (
            <WeekGrid
              anchor={anchor}
              today={today}
              eventsByDay={eventsByDay}
              onOpenEvent={setOpenEvent}
            />
          )}
        </div>

        <CalendarDaySidebar
          selected={selected}
          events={selectedDayEvents}
          onOpenEvent={setOpenEvent}
        />
      </div>

      <EventDetailDrawer selected={openEvent} onClose={() => setOpenEvent(null)} />
    </div>
  );
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

interface ToolbarProps {
  readonly periodLabel: string;
  readonly view: CalendarViewMode;
  readonly onPrev: () => void;
  readonly onNext: () => void;
  readonly onToday: () => void;
  readonly onView: (view: CalendarViewMode) => void;
  readonly t: ReturnType<typeof useTranslations>;
}

function Toolbar({
  periodLabel,
  view,
  onPrev,
  onNext,
  onToday,
  onView,
  t,
}: ToolbarProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <Button size="icon-sm" variant="outline" onClick={onPrev} aria-label={t("prev")}>
          <ChevronLeft />
        </Button>
        <Button size="icon-sm" variant="outline" onClick={onNext} aria-label={t("next")}>
          <ChevronRight />
        </Button>
        <Button size="sm" variant="ghost" onClick={onToday}>
          {t("today")}
        </Button>
        <span className="ml-1 text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
          {periodLabel}
        </span>
      </div>

      <div
        role="tablist"
        aria-label={t("viewLabel")}
        className="inline-flex items-center gap-1 rounded-[var(--radius-pill)] border border-[var(--color-border)] bg-[var(--color-surface)] p-1"
      >
        {(["month", "week"] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            role="tab"
            aria-selected={view === mode}
            onClick={() => onView(mode)}
            className={cn(
              "rounded-[var(--radius-pill)] px-3 py-1 text-[12px] font-semibold transition-colors duration-[var(--duration-fast)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none",
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
  );
}

interface CourseLegendProps {
  readonly courses: readonly CalendarLegendCourse[];
  readonly hidden: ReadonlySet<string>;
  readonly onToggle: (courseId: string) => void;
  readonly t: ReturnType<typeof useTranslations>;
}

function CourseLegend({ courses, hidden, onToggle, t }: CourseLegendProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-[11px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
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
              "inline-flex items-center gap-1.5 rounded-[var(--radius-pill)] border px-2.5 py-1 text-[12px] font-medium transition-colors duration-[var(--duration-fast)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none",
              isHidden
                ? "border-[var(--color-border)] bg-transparent text-[var(--color-text-muted)] line-through"
                : "border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)]"
            )}
          >
            <span
              aria-hidden="true"
              className={cn(
                "size-2 rounded-full",
                paletteSlot(course.colorIndex).swatch,
                isHidden && "opacity-40"
              )}
            />
            {course.courseCode}
          </button>
        );
      })}
    </div>
  );
}
