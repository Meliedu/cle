"use client";

import { useState } from "react";

import { PageHeader, StateBanner } from "@/components/patterns";
import { MiniCalendar } from "@/components/dashboard/mini-calendar";
import { UpcomingSwarms } from "@/components/dashboard/upcoming-swarms";
import { useDashboardPreviewEvents } from "@/components/dashboard/dashboard-preview-events";

/**
 * Calendar page composition shared by every role lane. Pairs the existing
 * mini-calendar + upcoming feed with an info banner flagging that the full
 * month/week views are still on the way.
 */
export function CalendarView() {
  const events = useDashboardPreviewEvents();
  const [selected, setSelected] = useState<Date | undefined>(new Date());

  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-6 px-6 py-6 md:px-10 md:py-10">
      <PageHeader title="Calendar" />

      <StateBanner
        tone="info"
        title="Full calendar coming soon"
        reason="Month and week views arrive with the course workspace update."
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <MiniCalendar
            events={events}
            selected={selected}
            onSelectDate={setSelected}
          />
        </div>
        <UpcomingSwarms events={events} />
      </div>
    </div>
  );
}
