"use client";

import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { DayPicker } from "react-day-picker";
import type { DashboardPreviewEvent } from "@/components/dashboard/dashboard-preview-events";

interface MiniCalendarProps {
  readonly events: readonly DashboardPreviewEvent[];
  readonly selected?: Date;
  readonly onSelectDate?: (date: Date | undefined) => void;
}

function isoForDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function MiniCalendar({ events, selected, onSelectDate }: MiniCalendarProps) {
  const [month, setMonth] = useState<Date>(() => selected ?? new Date());

  const eventDateSet = useMemo(
    () => new Set(events.map((e) => e.date)),
    [events]
  );

  const hasEvent = (d: Date): boolean => eventDateSet.has(isoForDate(d));

  return (
    <section className="rounded-[var(--radius-2xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <DayPicker
        mode="single"
        selected={selected}
        onSelect={onSelectDate}
        month={month}
        onMonthChange={setMonth}
        weekStartsOn={1}
        showOutsideDays
        classNames={{ root: "meli-day-picker" }}
        components={{
          Chevron: ({ orientation, disabled }) =>
            orientation === "left" ? (
              <ChevronLeft
                aria-hidden="true"
                className={disabled ? "opacity-40" : ""}
                size={16}
                strokeWidth={1.85}
              />
            ) : (
              <ChevronRight
                aria-hidden="true"
                className={disabled ? "opacity-40" : ""}
                size={16}
                strokeWidth={1.85}
              />
            ),
        }}
        modifiers={{ hasEvent }}
        modifiersClassNames={{ hasEvent: "meli-has-event" }}
      />
    </section>
  );
}
