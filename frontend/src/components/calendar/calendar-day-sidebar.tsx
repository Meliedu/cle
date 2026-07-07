"use client";

import { useLocale, useTranslations } from "next-intl";
import { ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";

import type { CourseCalendarEvent } from "./calendar-types";
import { eventTime, paletteSlot } from "./calendar-types";

/**
 * The right-hand day agenda beside the month/week grid. Lists every event on the
 * selected day (course-colored, time-ordered) as a row that opens the shared
 * event-detail drawer. Honest empty state when the day is clear.
 */

interface CalendarDaySidebarProps {
  readonly selected: Date;
  readonly events: readonly CourseCalendarEvent[];
  readonly onOpenEvent: (item: CourseCalendarEvent) => void;
}

export function CalendarDaySidebar({
  selected,
  events,
  onOpenEvent,
}: CalendarDaySidebarProps) {
  const t = useTranslations("patterns.calendar");
  const locale = useLocale();

  const heading = selected.toLocaleDateString(locale, {
    weekday: "long",
    day: "numeric",
    month: "long",
  });

  return (
    <aside className="rounded-[var(--radius-2xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <h2 className="text-[14px] font-semibold tracking-tight text-[var(--color-text)]">
        {heading}
      </h2>

      {events.length === 0 ? (
        <p className="mt-4 text-[13px] text-[var(--color-text-muted)]">
          {t("day.empty")}
        </p>
      ) : (
        <ul className="mt-3 space-y-2">
          {events.map((item) => {
            const slot = paletteSlot(item.colorIndex);
            const kindLabel =
              item.event.kind === "work_item"
                ? t(`source.${item.event.source_kind}`)
                : t(`kind.${item.event.kind}`);
            return (
              <li key={item.event.id}>
                <button
                  type="button"
                  onClick={() => onOpenEvent(item)}
                  className={cn(
                    "group flex w-full items-center gap-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2.5 text-left outline-none transition-colors duration-[var(--duration-fast)]",
                    "hover:border-[var(--color-border-hover)] hover:bg-[var(--color-surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none"
                  )}
                >
                  <span
                    aria-hidden="true"
                    className={cn("mt-1 h-8 w-1 shrink-0 rounded-full", slot.swatch)}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className="text-[12px] font-medium text-[var(--color-text-secondary)]">
                        {eventTime(item.event.at, locale)}
                      </span>
                      <span className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                        {kindLabel}
                      </span>
                    </span>
                    <span className="mt-0.5 block truncate text-[13px] font-semibold text-[var(--color-text)]">
                      {item.event.title}
                    </span>
                    <span className="block truncate text-[11px] text-[var(--color-text-muted)]">
                      {item.courseCode}
                    </span>
                  </span>
                  <ChevronRight
                    aria-hidden="true"
                    className="size-4 shrink-0 text-[var(--color-text-muted)] transition-transform duration-[var(--duration-fast)] group-hover:translate-x-0.5 motion-reduce:transition-none"
                  />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
