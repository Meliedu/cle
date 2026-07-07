"use client";

import { useMemo } from "react";
import { useLocale, useTranslations } from "next-intl";

import { cn } from "@/lib/utils";

import type { CourseCalendarEvent } from "./calendar-types";
import { eventTime, minutesIntoDay, paletteSlot } from "./calendar-types";
import { buildWeekDays, isSameDay, toIsoDate } from "./calendar-date-math";

/**
 * T008 / S019 — full week grid. A time-gutter on the left, seven day columns,
 * and each event placed as a course-colored block at its start time. The visible
 * hour band auto-expands to fit the earliest/latest event so nothing is clipped.
 * Event blocks are focusable buttons that open the shared event-detail drawer.
 */

interface WeekGridProps {
  readonly anchor: Date;
  readonly today: Date;
  readonly eventsByDay: ReadonlyMap<string, readonly CourseCalendarEvent[]>;
  readonly onOpenEvent: (item: CourseCalendarEvent) => void;
}

const HOUR_HEIGHT = 52; // px per hour row
const DEFAULT_START_HOUR = 8;
const DEFAULT_END_HOUR = 20;
const DEFAULT_EVENT_MINUTES = 45;

/** Duration in minutes for placing a block (meetings carry their own). */
function eventDuration(item: CourseCalendarEvent): number {
  const { event } = item;
  if (event.kind === "meeting" && event.duration_minutes) {
    return event.duration_minutes;
  }
  return DEFAULT_EVENT_MINUTES;
}

export function WeekGrid({ anchor, today, eventsByDay, onOpenEvent }: WeekGridProps) {
  const t = useTranslations("patterns.calendar");
  const locale = useLocale();

  const days = useMemo(() => buildWeekDays(anchor), [anchor]);

  // Auto-expand the visible hour band to include every event in the week.
  const [startHour, endHour] = useMemo(() => {
    let min = DEFAULT_START_HOUR;
    let max = DEFAULT_END_HOUR;
    for (const day of days) {
      for (const item of eventsByDay.get(toIsoDate(day)) ?? []) {
        const startH = Math.floor(minutesIntoDay(item.event.at) / 60);
        const endMinutes = minutesIntoDay(item.event.at) + eventDuration(item);
        min = Math.min(min, startH);
        max = Math.max(max, Math.ceil(endMinutes / 60));
      }
    }
    return [min, Math.min(max, 24)] as const;
  }, [days, eventsByDay]);

  const hours = useMemo(
    () => Array.from({ length: endHour - startHour }, (_, i) => startHour + i),
    [startHour, endHour]
  );
  const gridHeight = (endHour - startHour) * HOUR_HEIGHT;

  return (
    <div className="overflow-x-auto rounded-[var(--radius-2xl)] border border-[var(--color-border)] bg-[var(--color-surface)]">
      <div className="min-w-[640px]">
        {/* Day header row */}
        <div className="grid grid-cols-[56px_repeat(7,1fr)] border-b border-[var(--color-border)]">
          <div aria-hidden="true" />
          {days.map((day) => {
            const isToday = isSameDay(day, today);
            return (
              <div
                key={toIsoDate(day)}
                className={cn(
                  "flex flex-col items-center gap-0.5 py-2 text-center",
                  isToday && "bg-[var(--color-primary-light)]"
                )}
              >
                <span className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                  {day.toLocaleDateString(locale, { weekday: "short" })}
                </span>
                <span
                  className={cn(
                    "flex size-6 items-center justify-center rounded-full text-[13px] font-semibold",
                    isToday
                      ? "bg-[var(--color-primary)] text-[var(--color-text-on-primary)]"
                      : "text-[var(--color-text)]"
                  )}
                >
                  {day.getDate()}
                </span>
              </div>
            );
          })}
        </div>

        {/* Time gutter + day columns */}
        <div
          className="grid grid-cols-[56px_repeat(7,1fr)]"
          style={{ height: gridHeight }}
        >
          {/* Hour labels */}
          <div className="relative">
            {hours.map((hour, i) => (
              <div
                key={hour}
                className="absolute right-2 -translate-y-1/2 text-[10px] font-medium text-[var(--color-text-muted)]"
                style={{ top: i * HOUR_HEIGHT }}
              >
                {`${String(hour).padStart(2, "0")}:00`}
              </div>
            ))}
          </div>

          {days.map((day) => {
            const dayEvents = eventsByDay.get(toIsoDate(day)) ?? [];
            const isToday = isSameDay(day, today);
            return (
              <div
                key={toIsoDate(day)}
                className={cn(
                  "relative border-l border-[var(--color-border)]",
                  isToday && "bg-[var(--color-primary-light)]/40"
                )}
              >
                {/* Hour grid lines */}
                {hours.map((hour, i) => (
                  <div
                    key={hour}
                    aria-hidden="true"
                    className="absolute inset-x-0 border-t border-[var(--color-border)]/60"
                    style={{ top: i * HOUR_HEIGHT }}
                  />
                ))}

                {dayEvents.map((item) => {
                  const top =
                    ((minutesIntoDay(item.event.at) - startHour * 60) / 60) *
                    HOUR_HEIGHT;
                  const height = Math.max(
                    (eventDuration(item) / 60) * HOUR_HEIGHT - 2,
                    22
                  );
                  const slot = paletteSlot(item.colorIndex);
                  return (
                    <button
                      key={item.event.id}
                      type="button"
                      onClick={() => onOpenEvent(item)}
                      aria-label={t("openEvent", { title: item.event.title })}
                      className={cn(
                        "absolute inset-x-1 overflow-hidden rounded-[var(--radius-sm)] border-l-2 px-1.5 py-1 text-left outline-none transition-shadow duration-[var(--duration-fast)]",
                        "hover:shadow-[var(--shadow-sm)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/50 motion-reduce:transition-none",
                        slot.block,
                        slot.border
                      )}
                      style={{ top: Math.max(top, 0), height }}
                    >
                      <span className="block truncate text-[11px] font-semibold text-[var(--color-text)]">
                        {item.event.title}
                      </span>
                      <span className="block truncate text-[10px] text-[var(--color-text-secondary)]">
                        {eventTime(item.event.at, locale)}
                      </span>
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
