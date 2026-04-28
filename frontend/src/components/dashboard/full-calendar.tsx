"use client";

import { useMemo, useState } from "react";
import { format, isSameDay, parseISO } from "date-fns";
import { ChevronLeft, ChevronRight, Clock } from "lucide-react";
import { DayPicker } from "react-day-picker";
import { cn } from "@/lib/utils";
import type { DashboardPreviewEvent } from "@/components/dashboard/dashboard-preview-events";

interface FullCalendarProps {
  readonly events: readonly DashboardPreviewEvent[];
}

function isoForDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

const KIND_LABEL: Record<DashboardPreviewEvent["kind"], string> = {
  todo: "Task",
  swarm: "Swarm",
  session: "Live session",
};

const TONE_CLASSES: Record<DashboardPreviewEvent["color"], string> = {
  honey: "bg-[var(--color-primary)]",
  coral: "bg-[oklch(70%_0.13_35)]",
  salt: "bg-[var(--color-accent)]",
};

export function FullCalendar({ events }: FullCalendarProps) {
  const [month, setMonth] = useState<Date>(() => new Date());
  const [selected, setSelected] = useState<Date>(() => new Date());

  const eventDateSet = useMemo(
    () => new Set(events.map((e) => e.date)),
    [events]
  );
  const hasEvent = (d: Date): boolean => eventDateSet.has(isoForDate(d));

  const dayEvents = useMemo(
    () => events.filter((e) => isSameDay(parseISO(e.date), selected)),
    [events, selected]
  );

  const goToday = () => {
    const now = new Date();
    setMonth(now);
    setSelected(now);
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,3fr)]">
      {/* Calendar surface */}
      <section className="rounded-[var(--radius-2xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 md:p-6">
        <div className="mb-3 flex items-center justify-between">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
            Calendar
          </p>
          <button
            type="button"
            onClick={goToday}
            className="rounded-[var(--radius-pill)] border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1 text-[11px] font-semibold text-[var(--color-text-secondary)] transition-colors duration-[var(--duration-fast)] hover:border-[var(--color-border-hover)] hover:text-[var(--color-text)]"
          >
            Today
          </button>
        </div>

        <DayPicker
          mode="single"
          selected={selected}
          onSelect={(d) => d && setSelected(d)}
          month={month}
          onMonthChange={setMonth}
          weekStartsOn={1}
          showOutsideDays
          classNames={{ root: "meli-day-picker meli-day-picker--large" }}
          components={{
            Chevron: ({ orientation, disabled }) =>
              orientation === "left" ? (
                <ChevronLeft
                  aria-hidden="true"
                  className={disabled ? "opacity-40" : ""}
                  size={18}
                  strokeWidth={1.85}
                />
              ) : (
                <ChevronRight
                  aria-hidden="true"
                  className={disabled ? "opacity-40" : ""}
                  size={18}
                  strokeWidth={1.85}
                />
              ),
          }}
          modifiers={{ hasEvent }}
          modifiersClassNames={{ hasEvent: "meli-has-event" }}
        />
      </section>

      {/* Day drill-down drawer */}
      <aside className="rounded-[var(--radius-2xl)] border border-[var(--color-border)] bg-[var(--color-surface)]">
        <header className="border-b border-[var(--color-border)]/80 px-5 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
            {format(selected, "EEEE")}
          </p>
          <h2 className="mt-1 text-[18px] font-semibold tracking-tight text-[var(--color-text)]">
            {format(selected, "d MMM yyyy")}
          </h2>
        </header>

        {dayEvents.length === 0 ? (
          <div className="flex items-center justify-center px-5 py-12 text-center text-[13px] text-[var(--color-text-muted)]">
            Nothing scheduled for this day.
          </div>
        ) : (
          <ul className="divide-y divide-[var(--color-border)]/70">
            {dayEvents.map((event) => (
              <li key={event.id} className="px-5 py-4">
                <div className="mb-1 flex items-center gap-2">
                  <span
                    className={cn(
                      "size-1.5 rounded-full",
                      TONE_CLASSES[event.color]
                    )}
                    aria-hidden="true"
                  />
                  <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
                    {KIND_LABEL[event.kind]}
                  </span>
                </div>
                <p className="text-[14px] font-semibold leading-snug text-[var(--color-text)]">
                  {event.title}
                </p>
                {event.subtitle ? (
                  <p className="mt-1 inline-flex items-center gap-1 text-[12px] text-[var(--color-text-muted)]">
                    <Clock className="size-3" strokeWidth={1.85} />
                    {event.subtitle}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </aside>
    </div>
  );
}
