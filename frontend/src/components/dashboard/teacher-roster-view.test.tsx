import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { TeacherRosterView } from "./teacher-roster-view";
import { useCourses, type CourseResponse } from "@/hooks/use-courses";
import { useCourseNextClasses } from "@/hooks/use-teaching-day";
import { useUrlState } from "@/hooks/use-url-state";
import type { TeachingEntry } from "@/lib/teaching-day";

vi.mock("@/hooks/use-courses", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/use-courses")>(
    "@/hooks/use-courses"
  );
  return { ...actual, useCourses: vi.fn() };
});
vi.mock("@/hooks/use-teaching-day", () => ({
  useCourseNextClasses: vi.fn(),
}));
vi.mock("@/hooks/use-url-state", () => ({ useUrlState: vi.fn() }));
vi.mock("@/components/course/create-course-dialog", () => ({
  CreateCourseDialog: () => null,
}));

const mockUseCourses = vi.mocked(useCourses);
const mockUseNextClasses = vi.mocked(useCourseNextClasses);
const mockUseUrlState = vi.mocked(useUrlState);

/** In-memory stand-in for the query string, so filters behave as in the app. */
function stubUrlState(initial: Record<string, string> = {}) {
  const params = new URLSearchParams(initial);
  const set = vi.fn((key: string, value: string | null) => {
    if (value === null || value === "") params.delete(key);
    else params.set(key, value);
  });
  const clear = vi.fn((keys: readonly string[]) => {
    for (const key of keys) params.delete(key);
  });
  mockUseUrlState.mockReturnValue({
    get: (key: string, fallback = "") => params.get(key) ?? fallback,
    set,
    setMany: vi.fn(),
    clear,
    search: params.toString(),
  });
  return { set, clear, params };
}

function course(
  id: string,
  overrides: Partial<CourseResponse> = {}
): CourseResponse {
  return {
    id,
    name: `Course ${id}`,
    code: id.toUpperCase(),
    description: null,
    language: "english",
    semester: "2026 Spring",
    instructor_id: "u1",
    enroll_code: "ABC",
    enroll_code_active: true,
    settings: {},
    setup_status: "published",
    setup_checklist: {},
    join_mode: "open",
    context_status: "approved",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  } as CourseResponse;
}

function nextClass(courseId: string, at: string): TeachingEntry {
  return {
    id: `${courseId}:meeting:x`,
    kind: "class",
    title: "Session 4 · Reading",
    at,
    courseId,
    courseCode: courseId.toUpperCase(),
    courseName: `Course ${courseId}`,
    colorIndex: 0,
    location: "Room 2502A",
    durationMinutes: 50,
    provenance: null,
  };
}

function stubCourses(list: readonly CourseResponse[]) {
  mockUseCourses.mockReturnValue({
    data: list,
    isLoading: false,
  } as unknown as ReturnType<typeof useCourses>);
}

function stubSchedule(map: Map<string, TeachingEntry> = new Map()) {
  mockUseNextClasses.mockReturnValue({
    nextClassByCourse: map,
    isLoading: false,
  });
}

function renderRoster() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <TeacherRosterView />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  stubUrlState();
  stubCourses([course("lang1512"), course("mgmt4240")]);
  stubSchedule(
    new Map([["lang1512", nextClass("lang1512", "2026-06-27T10:30:00Z")]])
  );
});

describe("TeacherRosterView: one bounded control row (Plate 02, rule 1)", () => {
  it("puts search, term, and status together", () => {
    renderRoster();
    expect(screen.getByLabelText("Search courses")).toBeTruthy();
    expect(screen.getByLabelText("Term")).toBeTruthy();
    expect(screen.getByLabelText("Status")).toBeTruthy();
  });

  it("writes each filter into URL state, not local state", () => {
    const { set } = stubUrlState();
    renderRoster();

    fireEvent.change(screen.getByLabelText("Search courses"), {
      target: { value: "lang" },
    });
    expect(set).toHaveBeenCalledWith("q", "lang");

    fireEvent.change(screen.getByLabelText("Term"), {
      target: { value: "2026 Spring" },
    });
    expect(set).toHaveBeenCalledWith("term", "2026 Spring");
  });

  it("reads its initial filter values back out of the URL", () => {
    stubUrlState({ q: "mgmt" });
    renderRoster();
    expect(screen.queryByText("LANG1512")).toBeNull();
    expect(screen.getByText("MGMT4240")).toBeTruthy();
  });

  it("offers only the statuses actually present on the roster", () => {
    renderRoster();
    const options = within(screen.getByLabelText("Status")).getAllByRole(
      "option"
    );
    expect(options.map((o) => o.textContent)).toEqual([
      "All status",
      "Published",
    ]);
  });

  it("carries the active filters into the course link so Back restores them", () => {
    stubUrlState({ q: "lang" });
    renderRoster();
    const link = screen.getByRole("link", { name: /^Open course:/ });
    expect(link.getAttribute("href")).toBe(
      "/teacher/courses/lang1512?from=q%3Dlang"
    );
  });
});

describe("TeacherRosterView: rows are operational (Plate 02, rule 2)", () => {
  it("orders by next class and features the soonest", () => {
    stubCourses([course("later"), course("sooner")]);
    stubSchedule(
      new Map([
        ["later", nextClass("later", "2026-06-29T10:00:00Z")],
        ["sooner", nextClass("sooner", "2026-06-27T10:00:00Z")],
      ])
    );
    renderRoster();

    const items = screen.getAllByRole("listitem");
    expect(within(items[0]).getByText("SOONER")).toBeTruthy();
    // Only the featured row gets the filled button; the rest are text links.
    expect(document.querySelectorAll('[data-slot="button"]')).toHaveLength(2);
    expect(within(items[0]).getByText("Next to teach")).toBeTruthy();
    expect(within(items[1]).getByText("Next session")).toBeTruthy();
  });

  it("exposes lifecycle, next session, and venue on the row", () => {
    renderRoster();
    const row = screen.getAllByRole("listitem")[0];
    expect(within(row).getByText("Published")).toBeTruthy();
    expect(within(row).getByText("Session 4 · Reading")).toBeTruthy();
    expect(within(row).getByText(/Room 2502A/)).toBeTruthy();
  });

  it("changes the verb with status", () => {
    stubCourses([
      course("published"),
      course("insetup", {
        setup_status: "in_progress",
        context_status: "pending",
      }),
      course("archived", { setup_status: "archived" }),
    ]);
    stubSchedule();
    renderRoster();

    expect(screen.getByRole("link", { name: /^Open course:/ })).toBeTruthy();
    expect(screen.getByRole("link", { name: /^Continue setup:/ })).toBeTruthy();
    expect(screen.getByRole("link", { name: /^View course:/ })).toBeTruthy();
  });

  it("sends an incomplete course to setup and a published one to overview", () => {
    stubCourses([
      course("published"),
      course("insetup", {
        setup_status: "in_progress",
        context_status: "pending",
      }),
    ]);
    stubSchedule();
    renderRoster();

    expect(
      screen.getByRole("link", { name: /^Open course:/ }).getAttribute("href")
    ).toBe("/teacher/courses/published");
    expect(
      screen.getByRole("link", { name: /^Continue setup:/ }).getAttribute("href")
    ).toBe("/teacher/courses/insetup/setup");
  });

  it("says so in words when a course has no class scheduled", () => {
    stubCourses([course("a")]);
    stubSchedule();
    renderRoster();
    expect(screen.getByText("Not scheduled yet")).toBeTruthy();
  });

  it("does not feature a row that has no class scheduled", () => {
    stubCourses([course("a")]);
    stubSchedule();
    renderRoster();
    // No featured row means no filled button in the list; only the header
    // "Create course" button remains.
    const primaries = document.querySelectorAll('[data-slot="button"]');
    expect(primaries).toHaveLength(1);
    expect(primaries[0].textContent).toContain("Create course");
  });
});

describe("TeacherRosterView: empty states", () => {
  it("distinguishes an empty roster from an over-filtered one", () => {
    stubCourses([]);
    stubSchedule();
    renderRoster();
    expect(screen.getByText("No courses yet")).toBeTruthy();
  });

  it("offers a way back when filters exclude everything", () => {
    stubUrlState({ q: "nothing-matches" });
    renderRoster();
    expect(screen.getByText("No courses match these filters")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Clear filters" })).toBeTruthy();
  });

  it("clears every filter key it owns", () => {
    const { clear } = stubUrlState({ q: "nope" });
    renderRoster();
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(clear).toHaveBeenCalledWith(["q", "term", "status"]);
  });
});
