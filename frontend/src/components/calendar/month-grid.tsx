"use client";

import { useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useLocale, useTranslations } from "next-intl";

import { cn } from "@/lib/utils";

import type { CourseCalendarEvent } from "./calendar-types";
import { paletteSlot } from "./calendar-types";
import {
  addDays,
  buildMonthMatrix,
  isSameDay,
  isSameMonth,
  startOfWeek,
  toIsoDate,
} from "./calendar-date-math";

/**
 * T007 / S018 — full month grid. Renders whole Monday→Sunday weeks for the
 * anchor month, dimming spill-over days. Each cell carries up to a few
 * course-colored dots summarising that day's events; selecting a day surfaces
 * its full event list in the sidebar. The grid is keyboard-navigable: arrow keys
 * move a roving focus between days, Enter/Space selects, Home/End jump to the
 * week's edges.
 */

interface MonthGridProps {
  readonly anchor: Date;
  readonly today: Date;
  readonly selected: Date;
  readonly eventsByDay: ReadonlyMap<string, readonly CourseCalendarEvent[]>;
  readonly onSelectDate: (date: Date) => void;
}

const MAX_DOTS = 4;

export function MonthGrid({
  anchor,
  today,
  selected,
  eventsByDay,
  onSelectDate,
}: MonthGridProps) {
  const t = useTranslations("patterns.calendar");
  const locale = useLocale();

  const matrix = useMemo(() => buildMonthMatrix(anchor), [anchor]);
  const [focused, setFocused] = useState<Date>(selected);
  const cellRefs = useRef<Map<string, HTMLButtonElement>>(new Map());

  // Weekday header labels (Mon→Sun) derived from the locale, no hardcoded copy.
  const weekdayLabels = useMemo(() => {
    const weekStart = startOfWeek(new Date());
    const fmt = new Intl.DateTimeFormat(locale, { weekday: "short" });
    return Array.from({ length: 7 }, (_, i) => fmt.format(addDays(weekStart, i)));
  }, [locale]);

  const firstCell = matrix[0][0];
  const lastWeek = matrix[matrix.length - 1];
  const lastCell = lastWeek[lastWeek.length - 1];

  function focusDate(next: Date): void {
    // Clamp to the visible matrix so focus never escapes the rendered grid.
    if (next < firstCell || next > lastCell) return;
    setFocused(next);
    const el = cellRefs.current.get(toIsoDate(next));
    el?.focus();
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, day: Date): void {
    switch (event.key) {
      case "ArrowLeft":
        event.preventDefault();
        focusDate(addDays(day, -1));
        break;
      case "ArrowRight":
        event.preventDefault();
        focusDate(addDays(day, 1));
        break;
      case "ArrowUp":
        event.preventDefault();
        focusDate(addDays(day, -7));
        break;
      case "ArrowDown":
        event.preventDefault();
        focusDate(addDays(day, 7));
        break;
      case "Home":
        event.preventDefault();
        focusDate(startOfWeek(day));
        break;
      case "End":
        event.preventDefault();
        focusDate(addDays(startOfWeek(day), 6));
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        onSelectDate(day);
        break;
      default:
        break;
    }
  }

  return (
    <div className="rounded-[var(--radius-2xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-3 sm:p-4">
      <div
        role="grid"
        aria-label={t("monthGridLabel")}
        className="grid grid-cols-7 gap-1"
      >
        {weekdayLabels.map((label) => (
          <div
            key={label}
            role="columnheader"
            className="pb-2 text-center text-[11px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]"
          >
            {label}
          </div>
        ))}

        {matrix.flat().map((day) => {
          const iso = toIsoDate(day);
          const dayEvents = eventsByDay.get(iso) ?? [];
          const inMonth = isSameMonth(day, anchor);
          const isToday = isSameDay(day, today);
          const isSelected = isSameDay(day, selected);
          const isFocusTarget = isSameDay(day, focused);

          return (
            <button
              key={iso}
              type="button"
              role="gridcell"
              ref={(el) => {
                if (el) cellRefs.current.set(iso, el);
                else cellRefs.current.delete(iso);
              }}
              tabIndex={isFocusTarget ? 0 : -1}
              aria-selected={isSelected}
              aria-label={new Date(day).toLocaleDateString(locale, {
                weekday: "long",
                day: "numeric",
                month: "long",
              })}
              onClick={() => {
                setFocused(day);
                onSelectDate(day);
              }}
              onKeyDown={(e) => onKeyDown(e, day)}
              className={cn(
                "flex min-h-[64px] flex-col items-stretch gap-1 rounded-[var(--radius-md)] border border-transparent p-1.5 text-left transition-colors duration-[var(--duration-fast)] outline-none",
                "hover:bg-[var(--color-surface-hover)] focus-visible:border-[var(--color-primary)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none",
                isSelected && "bg-[var(--color-primary-light)]",
                !inMonth && "opacity-40"
              )}
            >
              <span
                className={cn(
                  "flex size-6 items-center justify-center self-start rounded-full text-[12px] font-semibold",
                  isToday
                    ? "bg-[var(--color-primary)] text-[var(--color-text-on-primary)]"
                    : "text-[var(--color-text)]"
                )}
              >
                {day.getDate()}
              </span>

              {dayEvents.length > 0 ? (
                <span className="mt-auto flex flex-wrap items-center gap-1">
                  {dayEvents.slice(0, MAX_DOTS).map((item, i) => (
                    <span
                      key={`${item.event.id}-${i}`}
                      aria-hidden="true"
                      className={cn(
                        "size-1.5 rounded-full",
                        paletteSlot(item.colorIndex).dot
                      )}
                    />
                  ))}
                  {dayEvents.length > MAX_DOTS ? (
                    <span className="text-[10px] font-medium text-[var(--color-text-muted)]">
                      {t("more", { count: dayEvents.length - MAX_DOTS })}
                    </span>
                  ) : null}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}
