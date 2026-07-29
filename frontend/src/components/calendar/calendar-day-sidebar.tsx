"use client";

import { useLocale, useTranslations } from "next-intl";
import { ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";
import { toTeachingEntry } from "@/lib/teaching-day";

import type { CourseCalendarEvent } from "./calendar-types";
import { eventTime, paletteSlot } from "./calendar-types";

/**
 * The selected-day agenda.
 *
 * Plate 03 makes two demands this component answers:
 *
 *   rule 2  "Color is supplementary; event type, title, time, course, and
 *            provenance must be available as text."
 *   rule 3  "Render an intentional empty state; auto-generated entries must
 *            identify their source course/setup rule."
 *
 * So every row spells out its time, type, course code, and, for anything the
 * course setup generated rather than a human authoring it, a provenance line.
 * The empty state explains what would appear here rather than just saying no.
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
    <aside
      aria-label={heading}
      className="rounded-[var(--radius-2xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5"
    >
      <h2 className="text-[17px] font-semibold tracking-tight text-[var(--color-text)]">
        {heading}
      </h2>

      {events.length === 0 ? (
        <div className="mt-4 border-t border-[var(--color-border)] pt-4">
          <p className="text-[14px] font-medium text-[var(--color-text-secondary)]">
            {t("day.empty")}
          </p>
          <p className="mt-1 text-[13px] leading-relaxed text-[var(--color-text-muted)]">
            {t("dayEmptyReason")}
          </p>
        </div>
      ) : (
        <ul className="mt-4 border-t border-[var(--color-border)]">
          {events.map((item) => {
            const slot = paletteSlot(item.colorIndex);
            const entry = toTeachingEntry(item);
            const kindLabel =
              item.event.kind === "work_item"
                ? t(`source.${item.event.source_kind}`)
                : t(`kind.${item.event.kind}`);

            return (
              <li
                key={item.event.id}
                className="border-b border-[var(--color-border)]"
              >
                <button
                  type="button"
                  onClick={() => onOpenEvent(item)}
                  aria-label={t("openEvent", { title: item.event.title })}
                  className={cn(
                    "group flex min-h-[68px] w-full items-start gap-3 rounded-[var(--radius-md)] px-2 py-3 text-left outline-none transition-colors duration-[var(--duration-fast)]",
                    "hover:bg-[var(--color-surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none"
                  )}
                >
                  <span className="mt-0.5 w-12 shrink-0 text-[13px] font-medium tabular-nums text-[var(--color-text-secondary)]">
                    {eventTime(item.event.at, locale)}
                  </span>

                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span
                        aria-hidden="true"
                        className={cn(
                          "size-2 shrink-0 rounded-full",
                          slot.swatch
                        )}
                      />
                      <span className="truncate text-[14px] font-semibold text-[var(--color-text)]">
                        {item.event.title}
                      </span>
                    </span>
                    <span className="mt-0.5 block truncate text-[13px] text-[var(--color-text-muted)]">
                      {[kindLabel, item.courseCode, entry.location]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                    {entry.provenance ? (
                      <span className="mt-0.5 block truncate text-[12px] text-[var(--color-text-muted)]">
                        {entry.provenance}
                      </span>
                    ) : null}
                  </span>

                  <ChevronRight
                    aria-hidden="true"
                    className="mt-1 size-4 shrink-0 text-[var(--color-text-muted)] transition-transform duration-[var(--duration-fast)] group-hover:translate-x-0.5 motion-reduce:transition-none motion-reduce:group-hover:translate-x-0"
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
