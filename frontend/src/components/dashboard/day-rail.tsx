"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { ArrowRight, ChevronLeft, ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";
import { paletteSlot } from "@/components/calendar/calendar-types";
import {
  addWeeks,
  buildWeekDays,
  isSameDay,
  startOfDay,
} from "@/components/calendar/calendar-date-math";
import type { TeachingEntry } from "@/lib/teaching-day";

interface DayRailProps {
  readonly today: Date;
  /** Anchor day the strip highlights: the day of the next class. */
  readonly focus: Date;
  readonly entries: readonly TeachingEntry[];
  /** Whether a class was resolved, which changes the agenda heading. */
  readonly hasClass: boolean;
  readonly calendarHref: string;
}

/**
 * The dashboard's right rail: a compact day strip plus a read-only agenda.
 *
 * Plate 01, rule 2 is explicit about the boundary this component must respect:
 *
 *   A compact day rail explains what follows while full calendar ownership
 *   remains on Calendar. […] dashboard renders contextual read-only agenda,
 *   not a second calendar editor.
 *
 * So: the strip pages through weeks for orientation only, nothing here mutates
 * an event, there is no view switcher, no course filter, and no "add event".
 * The closing line and the link both point at Calendar as the owner.
 */
export function DayRail({
  today,
  focus,
  entries,
  hasClass,
  calendarHref,
}: DayRailProps) {
  const t = useTranslations("teacher.home");
  const locale = useLocale();

  const [weekOffset, setWeekOffset] = useState(0);
  const anchor = useMemo(
    () => addWeeks(startOfDay(focus), weekOffset),
    [focus, weekOffset]
  );
  const days = useMemo(() => buildWeekDays(anchor), [anchor]);

  const monthLabel = anchor.toLocaleDateString(locale, {
    month: "long",
    year: "numeric",
  });
  // The heading and the sr-only caption must describe the week actually shown.
  // Derived from `focus`, they stayed on the focus day while the strip below
  // paged, so prev/next appeared to do nothing to anyone reading the heading,
  // and the caption described a week no longer on screen.
  const focusLabel = focus.toLocaleDateString(locale, {
    day: "numeric",
    weekday: "long",
  });
  const weekLabel =
    weekOffset === 0
      ? focusLabel
      : t("rail.weekOf", {
          date: anchor.toLocaleDateString(locale, {
            day: "numeric",
            month: "long",
          }),
        });

  return (
    <aside
      aria-labelledby="day-rail-title"
      className="flex flex-col gap-6 lg:border-l lg:border-[var(--color-border)] lg:pl-8"
    >
      <div>
        <p className="text-[12px] font-medium uppercase tracking-[0.1em] text-[var(--color-text-muted)]">
          {monthLabel}
        </p>

        <div className="mt-1 flex items-center justify-between gap-2">
          <h2
            id="day-rail-title"
            className="text-[24px] font-semibold tracking-[-0.02em] text-[var(--color-text)]"
          >
            {weekLabel}
          </h2>
          <div className="flex items-center gap-1">
            <StripButton
              label={t("rail.prevWeek")}
              onClick={() => setWeekOffset((value) => value - 1)}
            >
              <ChevronLeft aria-hidden="true" className="size-4" />
            </StripButton>
            <StripButton
              label={t("rail.nextWeek")}
              onClick={() => setWeekOffset((value) => value + 1)}
            >
              <ChevronRight aria-hidden="true" className="size-4" />
            </StripButton>
          </div>
        </div>

        {/* Orientation strip. Read-only: these are not controls, so they are
            not focusable and do not claim a keyboard stop. */}
        <table className="mt-4 w-full border-separate border-spacing-y-2">
          <caption className="sr-only">{weekLabel}</caption>
          <thead>
            <tr>
              {days.map((day) => (
                <th
                  key={`head-${day.toISOString()}`}
                  scope="col"
                  className="text-[11px] font-medium uppercase text-[var(--color-text-muted)]"
                >
                  {day.toLocaleDateString(locale, { weekday: "narrow" })}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              {days.map((day) => {
                const isFocus = isSameDay(day, focus);
                const isToday = isSameDay(day, today);
                return (
                  <td key={day.toISOString()} className="text-center">
                    <span
                      className={cn(
                        "mx-auto flex size-8 items-center justify-center rounded-full text-[13px] tabular-nums",
                        isFocus
                          ? "bg-[var(--color-primary)] font-semibold text-[var(--color-text-on-primary)]"
                          : isToday
                            ? "font-semibold text-[var(--color-primary-hover)] ring-1 ring-[var(--color-primary)]/40"
                            : "text-[var(--color-text-secondary)]"
                      )}
                    >
                      {day.getDate()}
                    </span>
                  </td>
                );
              })}
            </tr>
          </tbody>
        </table>
      </div>

      <div>
        <h3 className="text-[13px] font-semibold uppercase tracking-[0.1em] text-[var(--color-text-muted)]">
          {hasClass ? t("rail.agendaTitle") : t("rail.agendaTitleNoClass")}
        </h3>

        {entries.length === 0 ? (
          <p className="mt-3 border-t border-[var(--color-border)] pt-4 text-[14px] text-[var(--color-text-muted)]">
            {t("rail.agendaEmpty")}
          </p>
        ) : (
          <ul className="mt-3 border-t border-[var(--color-border)]">
            {entries.map((entry) => (
              <li
                key={entry.id}
                className="flex gap-4 border-b border-[var(--color-border)] py-3.5"
              >
                <time
                  dateTime={entry.at}
                  className="w-12 shrink-0 text-[13px] font-medium tabular-nums text-[var(--color-text-secondary)]"
                >
                  {new Date(entry.at).toLocaleTimeString(locale, {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </time>
                <div className="min-w-0">
                  <p className="flex items-center gap-2 text-[14px] font-medium text-[var(--color-text)]">
                    <span
                      aria-hidden="true"
                      className={cn(
                        "size-1.5 shrink-0 rounded-full",
                        paletteSlot(entry.colorIndex).dot
                      )}
                    />
                    <span className="truncate">{entry.title}</span>
                  </p>
                  <p className="mt-0.5 text-[13px] text-[var(--color-text-muted)]">
                    {[entry.courseCode, entry.location, entry.provenance]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <p className="max-w-[38ch] text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          {t("rail.note")}
        </p>
        <Link
          href={calendarHref}
          className="mt-4 inline-flex h-11 items-center gap-1.5 rounded-[var(--radius-md)] text-[14px] font-medium text-[var(--color-text)] underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40"
        >
          {t("rail.viewCalendar")}
          <ArrowRight aria-hidden="true" className="size-4" />
        </Link>
      </div>
    </aside>
  );
}

interface StripButtonProps {
  readonly label: string;
  readonly onClick: () => void;
  readonly children: React.ReactNode;
}

function StripButton({ label, onClick, children }: StripButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="flex size-11 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-text-muted)] outline-none transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none"
    >
      {children}
    </button>
  );
}
