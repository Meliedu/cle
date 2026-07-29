import { cleanup, render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { CourseOverview } from "./course-overview";
import { useCourse, type CourseResponse } from "@/hooks/use-courses";
import { useMeetings } from "@/hooks/use-meetings";
import { useDocuments } from "@/hooks/use-documents";
import { useRoster } from "@/hooks/use-enrollment";
import { useCalendar } from "@/hooks/use-calendar";
import type { CalendarEvent } from "@/hooks/use-calendar";

vi.mock("@/hooks/use-courses", () => ({ useCourse: vi.fn() }));
vi.mock("@/hooks/use-meetings", () => ({ useMeetings: vi.fn() }));
vi.mock("@/hooks/use-documents", () => ({ useDocuments: vi.fn() }));
vi.mock("@/hooks/use-enrollment", () => ({ useRoster: vi.fn() }));
vi.mock("@/hooks/use-calendar", () => ({ useCalendar: vi.fn() }));
vi.mock("@/hooks/use-memory", () => ({
  useMemorySummary: vi.fn(() => ({
    data: undefined,
    isLoading: false,
    isError: false,
  })),
}));

const mockUseCourse = vi.mocked(useCourse);
const mockUseMeetings = vi.mocked(useMeetings);
const mockUseDocuments = vi.mocked(useDocuments);
const mockUseRoster = vi.mocked(useRoster);
const mockUseCalendar = vi.mocked(useCalendar);

const NOW = new Date(2026, 5, 26, 9, 0);

function makeCourse(overrides: Partial<CourseResponse> = {}): CourseResponse {
  return {
    id: "c1",
    name: "English for Academic Purposes",
    code: "LANG1512",
    description: null,
    language: "en",
    semester: "2026 Spring",
    instructor_id: "i1",
    enroll_code: "ABCD2345",
    enroll_code_active: true,
    settings: {},
    setup_status: "published",
    setup_checklist: {},
    join_mode: "code",
    context_status: "approved",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function meetingEvent(hour: number, day = 26): CalendarEvent {
  return {
    id: `m-${day}-${hour}`,
    kind: "meeting",
    title: "Session 4 · Reading",
    at: new Date(2026, 5, day, hour, 30).toISOString(),
    duration_minutes: 50,
    location: "Room 2502A",
    status: "planned",
  };
}

function releaseEvent(day: number): CalendarEvent {
  return {
    id: `w-${day}`,
    kind: "work_item",
    title: "Practice 2 release",
    at: new Date(2026, 5, day, 18, 0).toISOString(),
    source_kind: "practice",
    required: false,
  };
}

function stub(options: {
  course?: Partial<CourseResponse>;
  events?: readonly CalendarEvent[];
  documents?: readonly { status: string }[];
  students?: number;
  meetings?: number;
} = {}) {
  mockUseCourse.mockReturnValue({
    data: makeCourse(options.course),
  } as unknown as ReturnType<typeof useCourse>);
  mockUseCalendar.mockReturnValue({
    data: options.events ?? [],
    isLoading: false,
  } as unknown as ReturnType<typeof useCalendar>);
  mockUseMeetings.mockReturnValue({
    data: Array.from({ length: options.meetings ?? 0 }, (_, i) => ({ id: `m${i}` })),
    isLoading: false,
  } as unknown as ReturnType<typeof useMeetings>);
  mockUseRoster.mockReturnValue({
    data: Array.from({ length: options.students ?? 0 }, (_, i) => ({
      id: `s${i}`,
      role: "student",
    })),
    isLoading: false,
  } as unknown as ReturnType<typeof useRoster>);
  mockUseDocuments.mockReturnValue({
    data: options.documents ?? [],
    isLoading: false,
  } as unknown as ReturnType<typeof useDocuments>);
}

function renderOverview() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <CourseOverview courseId="c1" />
    </NextIntlClientProvider>
  );
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(NOW);
  stub();
});

describe("CourseOverview: the next session is the hero (Plate 04, rule 3)", () => {
  it("leads with the next session, not a grid of counters", () => {
    stub({ events: [meetingEvent(10)] });
    renderOverview();

    const hero = screen.getByRole("region", { name: /session 4/i });
    expect(within(hero).getByText("Session 4 · Reading")).toBeTruthy();
    expect(within(hero).getByText("Room 2502A")).toBeTruthy();
    expect(within(hero).getByText(/Next teaching today at 10:30/)).toBeTruthy();
  });

  it("routes the dominant action into Sessions", () => {
    stub({ events: [meetingEvent(10)] });
    renderOverview();
    expect(
      screen
        .getByRole("link", { name: /open session 4/i })
        .getAttribute("href")
    ).toBe("/teacher/courses/c1/sessions");
  });

  it("states source readiness on the hero as text", () => {
    stub({
      events: [meetingEvent(10)],
      documents: [{ status: "completed" }, { status: "completed" }, { status: "failed" }],
    });
    renderOverview();
    expect(screen.getByText("2 of 3 sources ready")).toBeTruthy();
  });

  it("renders an intentional state when nothing is scheduled", () => {
    stub({ events: [] });
    renderOverview();
    expect(screen.getByText("No class scheduled yet")).toBeTruthy();
  });
});

describe("CourseOverview: Setup is gated by lifecycle (Plate 04, rule 3)", () => {
  it("offers Continue setup only while the course is incomplete", () => {
    stub({
      course: { setup_status: "in_progress", context_status: "pending" },
      events: [meetingEvent(10)],
    });
    renderOverview();

    expect(screen.getByText("Finish setting up this course")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Continue setup" }).getAttribute("href")
    ).toBe("/teacher/courses/c1/setup");
  });

  it("exposes no Setup destination once the course is published", () => {
    stub({ events: [meetingEvent(10)] });
    renderOverview();

    expect(screen.queryByText("Finish setting up this course")).toBeNull();
    const setupLinks = screen
      .getAllByRole("link")
      .filter((link) => link.getAttribute("href")?.includes("/setup"));
    expect(setupLinks).toHaveLength(0);
  });

  it("shows no draft banner competing with the hero", () => {
    stub({
      course: { setup_status: "in_progress", context_status: "pending" },
    });
    renderOverview();
    // The old banner copy is gone; setup is the hero, not an alert above it.
    expect(screen.queryByText("This course is still in setup")).toBeNull();
  });
});

describe("CourseOverview: right rail holds decision-changing context (rule 4)", () => {
  it("shows readiness, enrollment, and source health", () => {
    stub({
      events: [meetingEvent(10)],
      students: 28,
      meetings: 12,
      documents: [{ status: "completed" }, { status: "completed" }],
    });
    renderOverview();

    const rail = screen.getByRole("region", { name: /ready for the next class/i });
    expect(within(rail).getByText("28")).toBeTruthy();
    expect(within(rail).getByText("learners enrolled")).toBeTruthy();
    expect(within(rail).getByText("12")).toBeTruthy();
    expect(within(rail).getByText("2 / 2")).toBeTruthy();
  });

  it("says readiness needs attention when a source is not ready", () => {
    stub({
      events: [meetingEvent(10)],
      documents: [{ status: "completed" }, { status: "failed" }],
    });
    renderOverview();
    expect(
      screen.getByText("Needs attention before the next class")
    ).toBeTruthy();
  });

  it("removes the Quick links card entirely", () => {
    stub({ events: [meetingEvent(10)] });
    renderOverview();
    expect(screen.queryByText("Quick links")).toBeNull();
    expect(screen.queryByText("View schedule")).toBeNull();
    expect(screen.queryByText("Open setup")).toBeNull();
  });

  it("moves course access to Students and says so", () => {
    stub({ events: [meetingEvent(10)] });
    renderOverview();

    // The class code no longer appears on Overview at all.
    expect(screen.queryByText("ABCD2345")).toBeNull();
    expect(screen.queryByText("Course access")).toBeNull();
    expect(
      screen.getByText("Course access is managed under Students, not Overview.")
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: /manage students/i }).getAttribute("href")
    ).toBe("/teacher/courses/c1/students");
  });
});

describe("CourseOverview: one ordered weekly sequence", () => {
  it("lists each item once, with its provenance", () => {
    stub({ events: [meetingEvent(10), releaseEvent(27)] });
    renderOverview();

    const week = screen.getByRole("region", { name: /this week/i });
    expect(within(week).getByText("Practice 2 release")).toBeTruthy();
    expect(
      within(week).getByText(/Auto-added from course setup/)
    ).toBeTruthy();
    // The hero session is not repeated in the sequence below it.
    expect(within(week).queryByText("Session 4 · Reading")).toBeNull();
  });

  it("renders an intentional empty week", () => {
    stub({ events: [meetingEvent(10)] });
    renderOverview();
    expect(
      screen.getByText("Nothing scheduled in the next seven days.")
    ).toBeTruthy();
  });
});
