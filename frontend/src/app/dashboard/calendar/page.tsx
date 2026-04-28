"use client";

// TODO(task-12): replace with useCalendarEvents after calendar page is rebuilt
import { useLegacyCalendarEvents } from "@/hooks/use-calendar-events";
import { FullCalendar } from "@/components/dashboard/full-calendar";

export default function CalendarPage() {
  // TODO(task-12): replace with useCalendarEvents after calendar page is rebuilt
  const events = useLegacyCalendarEvents();

  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-6 px-6 py-6 md:gap-8 md:px-10 md:py-10">
      <header className="flex flex-col gap-2 border-b border-[var(--color-border)]/70 pb-6">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Overview
        </p>
        <h1 className="text-[clamp(1.75rem,1.3rem+1vw,2.25rem)] font-semibold leading-[1.1] tracking-tight text-[var(--color-text)]">
          Calendar
        </h1>
        <p className="max-w-[52ch] text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
          Your personal to-dos with due dates and upcoming course events in one
          view. Click any day to see what&rsquo;s on.
        </p>
      </header>

      <FullCalendar events={events} />
    </div>
  );
}
