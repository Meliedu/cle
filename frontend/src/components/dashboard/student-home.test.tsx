import { cleanup, render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { StudentHome } from "./student-home";
import { useCourses } from "@/hooks/use-courses";
import { useUser } from "@/hooks/use-auth";
import { useLearningPath } from "@/hooks/use-learning-path";
import { useTeachingDay } from "@/hooks/use-teaching-day";
import type { ChecklistItem } from "@/hooks/use-work-items";
import type { LearningAction } from "@/lib/learning-path";

vi.mock("@/hooks/use-courses", () => ({ useCourses: vi.fn() }));
vi.mock("@/hooks/use-auth", () => ({ useUser: vi.fn() }));
vi.mock("@/hooks/use-learning-path", () => ({ useLearningPath: vi.fn() }));
vi.mock("@/hooks/use-teaching-day", () => ({ useTeachingDay: vi.fn() }));

const mockUseCourses = vi.mocked(useCourses);
const mockUseUser = vi.mocked(useUser);
const mockUsePath = vi.mocked(useLearningPath);
const mockUseDay = vi.mocked(useTeachingDay);

function item(overrides: Partial<ChecklistItem> = {}): ChecklistItem {
  return {
    id: "w1",
    course_id: "c1",
    source_kind: "checkpoint",
    source_id: "cp1",
    title: "Session 4 checkpoint",
    required: true,
    score_bearing: false,
    due_at: new Date(2026, 5, 26, 16, 20).toISOString(),
    close_at: null,
    visible_from: null,
    status: "in_progress",
    ...overrides,
  };
}

function action(
  overrides: Partial<ChecklistItem> = {},
  availability: LearningAction["availability"] = { state: "available", reason: null },
  work: LearningAction["work"] = "in_progress"
): LearningAction {
  return {
    item: item(overrides),
    courseId: "c1",
    courseCode: "LANG1512",
    courseName: "English for Academic Purposes",
    work,
    availability,
  };
}

function stubPath(
  next: LearningAction | null,
  rest: readonly LearningAction[] = []
) {
  mockUsePath.mockReturnValue({
    next,
    rest,
    all: next ? [next, ...rest] : rest,
    isLoading: false,
  });
}

function renderHome() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <StudentHome />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  mockUseUser.mockReturnValue({
    user: { firstName: "Hana", fullName: "Hana Lee" },
  } as unknown as ReturnType<typeof useUser>);
  mockUseCourses.mockReturnValue({
    data: [
      { id: "c1", name: "English for Academic Purposes", code: "LANG1512" },
      { id: "c2", name: "Chinese V", code: "LANG1515" },
    ],
    isLoading: false,
  } as unknown as ReturnType<typeof useCourses>);
  mockUseDay.mockReturnValue({
    next: null,
    laterToday: [],
    afterThis: [],
    isLoading: false,
  });
  stubPath(action());
});

describe("StudentHome: one recoverable next action (Student 01, note 01)", () => {
  it("shows saved progress, source, due time, and a resume action", () => {
    renderHome();

    const hero = screen.getByRole("region", { name: /session 4 checkpoint/i });
    expect(within(hero).getByText("Session 4 checkpoint")).toBeTruthy();
    expect(
      within(hero).getByText("LANG1512 · English for Academic Purposes")
    ).toBeTruthy();
    // Saved state is said in words, not implied by a ring or a colour.
    expect(within(hero).getByText("Saved")).toBeTruthy();
    expect(within(hero).getByText("Checkpoint")).toBeTruthy();
    // Format is locale-driven; assert the parts, not the ordering.
    expect(within(hero).getByText(/^Due .*Jun.*26/)).toBeTruthy();
  });

  it("uses Resume for saved work and Start for unstarted work", () => {
    renderHome();
    expect(screen.getByRole("link", { name: /resume/i })).toBeTruthy();

    cleanup();
    stubPath(action({ status: "pending" }, undefined, "not_started"));
    renderHome();
    expect(screen.getByRole("link", { name: /start/i })).toBeTruthy();
  });

  it("routes the resume action into the owning course", () => {
    renderHome();
    expect(
      screen.getByRole("link", { name: /resume/i }).getAttribute("href")
    ).toBe("/student/courses/c1/checkpoints");
  });

  it("exposes exactly one dominant action", () => {
    stubPath(action(), [action({ id: "w2", title: "Practice 2" })]);
    renderHome();
    expect(document.querySelectorAll('[data-slot="button"]')).toHaveLength(1);
  });

  it("treats an empty checklist as a good outcome, not an error", () => {
    stubPath(null, []);
    renderHome();
    expect(screen.getByText("You are all caught up")).toBeTruthy();
    expect(document.querySelectorAll('[data-slot="button"]')).toHaveLength(0);
  });
});

describe("StudentHome: locked work explains its dependency (Student 02, note 03)", () => {
  it("states the unlock reason as text beside the row", () => {
    stubPath(action(), [
      action(
        { id: "w2", title: "Practice 2" },
        { state: "scheduled", reason: "Unlocks after the Session 4 checkpoint" },
        "not_started"
      ),
    ]);
    renderHome();

    expect(
      screen.getByText(/Unlocks after the Session 4 checkpoint/)
    ).toBeTruthy();
    expect(screen.getByText("Scheduled")).toBeTruthy();
  });

  it("does not link a blocked row to a destination it cannot open", () => {
    stubPath(action(), [
      action(
        { id: "w2", title: "Practice 2" },
        { state: "closed", reason: "Closed 24 Jun" },
        "not_started"
      ),
    ]);
    renderHome();

    const queue = screen.getByRole("region", { name: /later today/i });
    const links = within(queue).queryAllByRole("link");
    expect(links).toHaveLength(0);
    // The row is still present and still explains itself.
    expect(within(queue).getByText("Practice 2")).toBeTruthy();
    expect(within(queue).getByText(/Closed 24 Jun/)).toBeTruthy();
  });

  it("links a row that is genuinely open", () => {
    stubPath(action(), [
      action({ id: "w2", title: "Practice 2", source_kind: "material" }, undefined, "not_started"),
    ]);
    renderHome();
    const queue = screen.getByRole("region", { name: /later today/i });
    expect(
      within(queue).getByRole("link").getAttribute("href")
    ).toBe("/student/courses/c1/materials");
  });

  it("distinguishes submitted and reviewed from work still to do", () => {
    stubPath(action(), [
      action({ id: "w2", title: "Quiz 1" }, undefined, "submitted"),
      action({ id: "w3", title: "Quiz 0" }, undefined, "reviewed"),
    ]);
    renderHome();
    expect(screen.getByText("Submitted")).toBeTruthy();
    expect(screen.getByText("Reviewed")).toBeTruthy();
  });
});

describe("StudentHome: the rail owns time only (Student 01, note 03)", () => {
  it("names the boundary between calendar and course path", () => {
    renderHome();
    const rail = screen.getByRole("complementary");
    expect(
      within(rail).getByText(/Calendar remains the source of time/)
    ).toBeTruthy();
    expect(
      within(rail).getByRole("link", { name: /view full calendar/i }).getAttribute("href")
    ).toBe("/student/calendar");
  });

  it("offers no teacher-only management destination", () => {
    renderHome();
    for (const forbidden of [/setup/i, /students/i, /enrollment/i]) {
      const links = screen
        .getAllByRole("link")
        .filter((link) => forbidden.test(link.getAttribute("href") ?? ""));
      expect(links).toHaveLength(0);
    }
  });
});
