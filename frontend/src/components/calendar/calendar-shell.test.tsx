import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { CalendarShell } from "./calendar-shell";
import { useCalendarEvents } from "./use-calendar-events";
import { useUrlState } from "@/hooks/use-url-state";
import type { CourseCalendarEvent } from "./calendar-types";

vi.mock("./use-calendar-events", () => ({ useCalendarEvents: vi.fn() }));
vi.mock("@/hooks/use-url-state", () => ({ useUrlState: vi.fn() }));
vi.mock("./event-detail-drawer", () => ({ EventDetailDrawer: () => null }));

const mockUseEvents = vi.mocked(useCalendarEvents);
const mockUseUrlState = vi.mocked(useUrlState);

function stubUrlState(initial: Record<string, string> = {}) {
  const params = new URLSearchParams(initial);
  const set = vi.fn();
  const setMany = vi.fn();
  mockUseUrlState.mockReturnValue({
    get: (key: string, fallback = "") => params.get(key) ?? fallback,
    set,
    setMany,
    clear: vi.fn(),
    search: params.toString(),
  });
  return { set, setMany };
}

/** A generated release: the case that must carry a provenance line. */
function release(id: string, courseIndex = 0): CourseCalendarEvent {
  return {
    event: {
      id,
      kind: "work_item",
      title: "Vocabulary quiz release",
      at: new Date(2026, 5, 26, 18, 0).toISOString(),
      source_kind: "quiz",
      required: false,
    },
    courseId: `c${courseIndex}`,
    courseCode: `LANG151${courseIndex}`,
    courseName: "A course",
    colorIndex: courseIndex,
  };
}

function meeting(id: string): CourseCalendarEvent {
  return {
    event: {
      id,
      kind: "meeting",
      title: "LANG1512 class",
      at: new Date(2026, 5, 26, 10, 30).toISOString(),
      duration_minutes: 50,
      location: "Room 2502A",
      status: "planned",
    },
    courseId: "c0",
    courseCode: "LANG1512",
    courseName: "A course",
    colorIndex: 0,
  };
}

function stubEvents(
  events: readonly CourseCalendarEvent[],
  courseCount = 1,
  isLoading = false
) {
  mockUseEvents.mockReturnValue({
    events,
    courses: Array.from({ length: courseCount }, (_, index) => ({
      courseId: `c${index}`,
      courseCode: `LANG151${index}`,
      courseName: "A course",
      colorIndex: index,
    })),
    isLoading,
  });
}

function renderShell() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <CalendarShell />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  vi.setSystemTime(new Date(2026, 5, 26, 9, 0));
  stubUrlState();
  stubEvents([]);
});

describe("CalendarShell: controls live in the calendar header (rule 1)", () => {
  it("groups period navigation, Today, and view mode together", () => {
    renderShell();
    // All four controls are siblings inside the grid card header, not
    // scattered across the page.
    const prev = screen.getByRole("button", { name: "Previous period" });
    const header = prev.closest("div")?.parentElement;
    expect(header).toBeTruthy();
    expect(within(header as HTMLElement).getByText("Today")).toBeTruthy();
    expect(within(header as HTMLElement).getByRole("radio", { name: "Month" })).toBeTruthy();
    expect(within(header as HTMLElement).getByRole("radio", { name: "Week" })).toBeTruthy();
  });

  it("meets the 44px target on every navigation control", () => {
    renderShell();
    for (const name of ["Previous period", "Next period"]) {
      const button = screen.getByRole("button", { name });
      expect(button.className).toContain("size-11");
    }
    expect(
      screen.getByRole("button", { name: "Today" }).className
    ).toContain("h-11");
  });
});

describe("CalendarShell: one state owner (rule 2)", () => {
  it("writes the period into URL state, not local state", () => {
    const { set } = stubUrlState();
    renderShell();
    fireEvent.click(screen.getByRole("button", { name: "Next period" }));
    expect(set).toHaveBeenCalledWith("date", expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/));
  });

  it("writes the view mode into URL state", () => {
    const { set } = stubUrlState();
    renderShell();
    fireEvent.click(screen.getByRole("radio", { name: "Week" }));
    expect(set).toHaveBeenCalledWith("view", "week");
    // Month is the default, so it clears the key rather than storing it.
    fireEvent.click(screen.getByRole("radio", { name: "Month" }));
    expect(set).toHaveBeenCalledWith("view", null);
  });

  it("reads the view mode back out of the URL", () => {
    stubUrlState({ view: "week" });
    renderShell();
    expect(
      screen.getByRole("radio", { name: "Week" }).getAttribute("aria-checked")
    ).toBe("true");
  });

  it("clears both date and day in a single navigation on Today", () => {
    const { setMany } = stubUrlState({ date: "2026-08-01", day: "2026-08-05" });
    renderShell();
    fireEvent.click(screen.getByRole("button", { name: "Today" }));
    expect(setMany).toHaveBeenCalledWith({ date: null, day: null });
  });

  it("keeps course filters in the URL", () => {
    const { set } = stubUrlState();
    stubEvents([meeting("m1")], 2);
    renderShell();
    fireEvent.click(screen.getByRole("button", { name: /LANG1510/ }));
    expect(set).toHaveBeenCalledWith("hide", "c0");
  });

  it("hides events for a filtered-out course", () => {
    stubUrlState({ hide: "c0" });
    stubEvents([meeting("m1")], 2);
    renderShell();
    expect(screen.queryByText("LANG1512 class")).toBeNull();
  });
});

describe("CalendarShell: legend is text-first (rule 2)", () => {
  it("spells out the course code and marks a hidden course without color", () => {
    stubUrlState({ hide: "c0" });
    stubEvents([], 2);
    renderShell();

    const chip = screen.getByRole("button", { name: /LANG1510/ });
    expect(chip.getAttribute("aria-pressed")).toBe("false");
    // Struck through as well as dimmed, so state does not rely on the swatch.
    expect(chip.className).toContain("line-through");
  });

  it("shows the legend only when more than one course is present", () => {
    stubEvents([], 1);
    renderShell();
    expect(screen.queryByText("Courses")).toBeNull();
  });
});

describe("CalendarShell: intentional empty state (rule 3)", () => {
  it("still renders the month grid when nothing is scheduled", () => {
    stubEvents([]);
    renderShell();
    // The grid is the calendar's authority over time; it must not vanish.
    expect(screen.getByRole("grid", { name: "Month calendar grid" })).toBeTruthy();
    expect(screen.getByText("Nothing scheduled this month.")).toBeTruthy();
  });

  it("explains what would appear in an empty day agenda", () => {
    stubEvents([]);
    renderShell();
    expect(screen.getByText("No events on this day.")).toBeTruthy();
    expect(
      screen.getByText(
        "Classes, generated releases, and deadlines for this day appear here."
      )
    ).toBeTruthy();
  });

  it("names the source of an auto-generated entry in the agenda", () => {
    stubEvents([release("w1")]);
    renderShell();
    const agenda = screen.getByRole("complementary");
    expect(within(agenda).getByText("Vocabulary quiz release")).toBeTruthy();
    expect(
      within(agenda).getByText("Auto-added from course setup")
    ).toBeTruthy();
  });

  it("gives an authored class no provenance line", () => {
    stubEvents([meeting("m1")]);
    renderShell();
    const agenda = screen.getByRole("complementary");
    expect(
      within(agenda).queryByText("Auto-added from course setup")
    ).toBeNull();
  });

  it("states event type, course, and venue as text in the agenda", () => {
    stubEvents([meeting("m1")]);
    renderShell();
    const agenda = screen.getByRole("complementary");
    expect(
      within(agenda).getByText(/Session · LANG1512 · Room 2502A/)
    ).toBeTruthy();
  });
});
