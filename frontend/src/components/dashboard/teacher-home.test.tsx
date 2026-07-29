import { cleanup, render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { TeacherHome } from "./teacher-home";
import { useCourses } from "@/hooks/use-courses";
import { useUser } from "@/hooks/use-auth";
import {
  useCourseSourceReadiness,
  useTeachingDay,
} from "@/hooks/use-teaching-day";
import type { TeachingEntry } from "@/lib/teaching-day";

vi.mock("@/hooks/use-courses", () => ({ useCourses: vi.fn() }));
vi.mock("@/hooks/use-auth", () => ({ useUser: vi.fn() }));
vi.mock("@/hooks/use-teaching-day", () => ({
  useTeachingDay: vi.fn(),
  useCourseSourceReadiness: vi.fn(),
}));

const mockUseCourses = vi.mocked(useCourses);
const mockUseUser = vi.mocked(useUser);
const mockUseTeachingDay = vi.mocked(useTeachingDay);
const mockUseSources = vi.mocked(useCourseSourceReadiness);

function entry(overrides: Partial<TeachingEntry> = {}): TeachingEntry {
  return {
    id: "c1:meeting:m1",
    kind: "class",
    title: "Session 4 · Reading",
    at: new Date(2026, 5, 26, 10, 30).toISOString(),
    courseId: "c1",
    courseCode: "LANG1512",
    courseName: "English for Academic Purposes",
    colorIndex: 0,
    location: "Room 2502A",
    durationMinutes: 50,
    provenance: null,
    ...overrides,
  };
}

function stubDay(
  overrides: Partial<ReturnType<typeof useTeachingDay>> = {}
): void {
  mockUseTeachingDay.mockReturnValue({
    next: {
      entry: entry(),
      minutesUntil: 18,
      isToday: true,
      inProgress: false,
    },
    laterToday: [],
    afterThis: [],
    isLoading: false,
    ...overrides,
  });
}

function stubSources(
  overrides: Partial<ReturnType<typeof useCourseSourceReadiness>> = {}
): void {
  mockUseSources.mockReturnValue({
    total: 3,
    ready: 3,
    inFlight: 0,
    needsAttention: 0,
    blocking: 0,
    isLoading: false,
    ...overrides,
  });
}

function renderHome() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <TeacherHome />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  mockUseUser.mockReturnValue({
    user: { firstName: "Dev", fullName: "Dev Teacher" },
  } as unknown as ReturnType<typeof useUser>);
  mockUseCourses.mockReturnValue({
    data: [
      { id: "c1", name: "English for Academic Purposes", code: "LANG1512", updated_at: "2026-06-24T00:00:00Z", setup_status: "published", context_status: "approved" },
      { id: "c2", name: "Academic Speaking", code: "LANG1520", updated_at: "2026-06-20T00:00:00Z", setup_status: "published", context_status: "approved" },
    ],
    isLoading: false,
  } as unknown as ReturnType<typeof useCourses>);
  stubDay();
  stubSources();
});

describe("TeacherHome: the next teaching action is dominant (Plate 01)", () => {
  it("makes the next session the dominant object with time, room, and readiness", () => {
    renderHome();

    const hero = screen.getByRole("region", { name: /session 4/i });
    expect(within(hero).getByText("Session 4 · Reading")).toBeTruthy();
    expect(
      within(hero).getByText(/LANG1512 · English for Academic Purposes/)
    ).toBeTruthy();
    expect(within(hero).getByText("Room 2502A")).toBeTruthy();
    expect(within(hero).getByText("Source readiness")).toBeTruthy();
    expect(within(hero).getByText("3 / 3 ready")).toBeTruthy();
  });

  it("states how long until the class in words", () => {
    renderHome();
    expect(screen.getByText("Next teaching in 18 minutes")).toBeTruthy();
  });

  it("says 'Teaching now' once the class has started", () => {
    stubDay({
      next: {
        entry: entry(),
        minutesUntil: -5,
        isToday: true,
        inProgress: true,
      },
    });
    renderHome();
    expect(screen.getByText("Teaching now")).toBeTruthy();
  });

  it("exposes exactly one dominant action on the whole surface (rule 3)", () => {
    stubDay({
      laterToday: [
        entry({
          id: "c2:work_item:w1",
          kind: "generated_release",
          title: "Practice 2 release",
          provenance: "Auto-added from course setup",
        }),
      ],
      afterThis: [entry({ id: "c2:meeting:m2", title: "Session 3" })],
    });
    renderHome();

    // Every filled/primary control is a `data-slot="button"`. Exactly one may
    // exist: the hero CTA. Everything else is a text link or a quiet chip.
    const primaries = document.querySelectorAll('[data-slot="button"]');
    expect(primaries).toHaveLength(1);
    expect(primaries[0].textContent).toContain("Open Session 4 · Reading");
  });

  it("routes the dominant action into the course's Sessions destination", () => {
    renderHome();
    const cta = screen.getByRole("link", { name: /open session 4/i });
    expect(cta.getAttribute("href")).toBe("/teacher/courses/c1/sessions");
  });

  it("reads source readiness only for the course being taught", () => {
    renderHome();
    expect(mockUseSources).toHaveBeenCalledWith("c1");
  });

  it("names what needs attention rather than relying on color", () => {
    stubSources({ total: 3, ready: 1, inFlight: 1, needsAttention: 1 });
    renderHome();
    expect(screen.getByText("1 source needs attention")).toBeTruthy();
  });

  it("says so in words when a course has no sources yet", () => {
    stubSources({ total: 0, ready: 0, inFlight: 0, needsAttention: 0 });
    renderHome();
    expect(screen.getByText("No sources yet")).toBeTruthy();
    expect(screen.queryByText(/\d+ \/ \d+ ready/)).toBeNull();
  });
});

describe("TeacherHome: subordinate regions", () => {
  it("names the source of an auto-generated later-today entry", () => {
    stubDay({
      laterToday: [
        entry({
          id: "c2:work_item:w1",
          kind: "generated_release",
          title: "Practice 2 release",
          location: null,
          provenance: "Auto-added from course setup",
        }),
      ],
    });
    renderHome();

    expect(screen.getByText("Practice 2 release")).toBeTruthy();
    expect(
      screen.getByText(/Auto-added from course setup/)
    ).toBeTruthy();
    // Type is stated as text, not carried by color alone.
    expect(screen.getByText("Release")).toBeTruthy();
  });

  it("renders an intentional empty state when nothing else is scheduled", () => {
    renderHome();
    expect(screen.getByText("Nothing else scheduled today.")).toBeTruthy();
  });

  it("keeps the roster compact and defers the full list to Courses", () => {
    renderHome();
    const roster = screen.getByRole("region", { name: /teaching roster/i });
    expect(within(roster).getByText("LANG1512")).toBeTruthy();
    expect(within(roster).getByText("LANG1520")).toBeTruthy();
  });
});

describe("TeacherHome: the day rail is read-only (Plate 01, rule 2)", () => {
  it("offers no event editing, view switch, or add-event affordance", () => {
    stubDay({ afterThis: [entry({ id: "c2:meeting:m2", title: "Session 3" })] });
    renderHome();

    const rail = screen.getByRole("complementary");
    expect(within(rail).queryByRole("button", { name: /add/i })).toBeNull();
    expect(within(rail).queryByRole("tab")).toBeNull();
    // Only the week-paging controls are buttons in the rail.
    const buttons = within(rail).getAllByRole("button");
    expect(buttons.map((b) => b.getAttribute("aria-label"))).toEqual([
      "Previous week",
      "Next week",
    ]);
  });

  it("names Calendar as the owner of time and links to it", () => {
    renderHome();
    const rail = screen.getByRole("complementary");
    expect(
      within(rail).getByText(/Calendar remains the source of time/)
    ).toBeTruthy();
    const link = within(rail).getByRole("link", { name: /view full calendar/i });
    expect(link.getAttribute("href")).toBe("/teacher/calendar");
  });
});

describe("TeacherHome: no class ahead", () => {
  it("renders an intentional empty hero, not a broken one", () => {
    stubDay({ next: null, laterToday: [], afterThis: [] });
    renderHome();

    expect(screen.getByText("No class scheduled ahead")).toBeTruthy();
    // No dominant action exists when there is nothing to open.
    expect(document.querySelectorAll('[data-slot="button"]')).toHaveLength(0);
    expect(
      screen.getByRole("link", { name: /go to courses/i }).getAttribute("href")
    ).toBe("/teacher/courses");
  });

  it("does not query source readiness when there is no class", () => {
    stubDay({ next: null });
    renderHome();
    expect(mockUseSources).toHaveBeenCalledWith(null);
  });
});
