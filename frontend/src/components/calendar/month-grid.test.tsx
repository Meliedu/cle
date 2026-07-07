import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { MonthGrid } from "./month-grid";
import { toIsoDate } from "./calendar-date-math";
import type { CourseCalendarEvent } from "./calendar-types";
import type { CalendarMeetingEvent } from "@/hooks/use-calendar";

function meetingEvent(id: string, at: string): CourseCalendarEvent {
  const event: CalendarMeetingEvent = {
    id,
    kind: "meeting",
    title: `Session ${id}`,
    at,
    duration_minutes: 90,
    location: "Room 1",
    status: "planned",
  };
  return {
    event,
    courseId: "c1",
    courseCode: "LANG1512",
    courseName: "Academic English",
    colorIndex: 0,
  };
}

function renderGrid(onSelectDate = vi.fn()) {
  const anchor = new Date(2026, 5, 15); // June 2026
  const today = new Date(2026, 5, 26);
  const selected = new Date(2026, 5, 15);
  const eventsByDay = new Map<string, readonly CourseCalendarEvent[]>([
    [
      toIsoDate(new Date(2026, 5, 15)),
      [
        meetingEvent("a", "2026-06-15T10:00:00Z"),
        meetingEvent("b", "2026-06-15T12:00:00Z"),
      ],
    ],
  ]);
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <MonthGrid
        anchor={anchor}
        today={today}
        selected={selected}
        eventsByDay={eventsByDay}
        onSelectDate={onSelectDate}
      />
    </NextIntlClientProvider>
  );
  return { onSelectDate };
}

afterEach(cleanup);

describe("MonthGrid", () => {
  it("renders a labelled month grid with 7 weekday column headers", () => {
    renderGrid();
    expect(screen.getByRole("grid", { name: "Month calendar grid" })).toBeTruthy();
    expect(screen.getAllByRole("columnheader")).toHaveLength(7);
  });

  it("renders whole weeks including the first and last of June", () => {
    renderGrid();
    const cells = screen.getAllByRole("gridcell");
    // Whole weeks: cell count is divisible by 7.
    expect(cells.length % 7).toBe(0);
    expect(screen.getByRole("gridcell", { name: "Monday, June 1" })).toBeTruthy();
    expect(screen.getByRole("gridcell", { name: "Tuesday, June 30" })).toBeTruthy();
  });

  it("marks the selected day with aria-selected", () => {
    renderGrid();
    const selectedCell = screen.getByRole("gridcell", {
      name: "Monday, June 15",
    });
    expect(selectedCell.getAttribute("aria-selected")).toBe("true");
  });

  it("fires onSelectDate when a day is clicked", () => {
    const { onSelectDate } = renderGrid();
    fireEvent.click(screen.getByRole("gridcell", { name: "Friday, June 26" }));
    expect(onSelectDate).toHaveBeenCalledTimes(1);
    expect(toIsoDate(onSelectDate.mock.calls[0][0])).toBe("2026-06-26");
  });

  it("moves roving focus with ArrowRight and selects with Enter", () => {
    const { onSelectDate } = renderGrid();
    const start = screen.getByRole("gridcell", { name: "Monday, June 15" });
    fireEvent.keyDown(start, { key: "ArrowRight" });
    const next = screen.getByRole("gridcell", { name: "Tuesday, June 16" });
    expect(next.getAttribute("tabindex")).toBe("0");
    fireEvent.keyDown(next, { key: "Enter" });
    expect(toIsoDate(onSelectDate.mock.calls[0][0])).toBe("2026-06-16");
  });
});
