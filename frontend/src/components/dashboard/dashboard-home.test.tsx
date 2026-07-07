import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { DashboardHome } from "./dashboard-home";
import { useCourses } from "@/hooks/use-courses";
import { useNextAction, type ChecklistItem } from "@/hooks/use-work-items";

// Isolate the next-action behaviour: stub the network-backed hooks and the
// sibling panels so only DashboardHome's next-action slot is under test.
vi.mock("@/hooks/use-courses", () => ({ useCourses: vi.fn() }));
vi.mock("@/hooks/use-work-items", () => ({ useNextAction: vi.fn() }));
vi.mock("@/components/dashboard/dashboard-preview-events", () => ({
  useDashboardPreviewEvents: () => [],
}));
vi.mock("@/components/dashboard/welcome-hero", () => ({
  WelcomeHero: () => <div data-testid="welcome-hero" />,
}));
vi.mock("@/components/dashboard/todo-list", () => ({
  TodoList: () => <div data-testid="todo-list" />,
}));
vi.mock("@/components/dashboard/mini-calendar", () => ({
  MiniCalendar: () => <div data-testid="mini-calendar" />,
}));
vi.mock("@/components/dashboard/upcoming-swarms", () => ({
  UpcomingSwarms: () => <div data-testid="upcoming-swarms" />,
}));
vi.mock("@/components/dashboard/recent-courses", () => ({
  RecentCourses: () => <div data-testid="recent-courses" />,
}));

const mockUseCourses = vi.mocked(useCourses);
const mockUseNextAction = vi.mocked(useNextAction);

function stubCourses(courses: Array<{ id: string; updated_at: string }>) {
  mockUseCourses.mockReturnValue({
    data: courses,
    isLoading: false,
  } as unknown as ReturnType<typeof useCourses>);
}

function stubNextAction(
  value: Partial<ReturnType<typeof useNextAction>>
): void {
  mockUseNextAction.mockReturnValue({
    data: undefined,
    isLoading: false,
    isSuccess: false,
    ...value,
  } as unknown as ReturnType<typeof useNextAction>);
}

function renderDashboard() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <DashboardHome />
    </NextIntlClientProvider>
  );
}

const checkpointItem: ChecklistItem = {
  id: "wi-1",
  course_id: "course-1",
  source_kind: "checkpoint",
  source_id: "cp-1",
  title: "Lecture 3 checkpoint",
  required: true,
  score_bearing: false,
  due_at: "2026-07-10T09:00:00Z",
  close_at: "2026-07-10T09:00:00Z",
  visible_from: null,
  status: "pending",
};

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

describe("DashboardHome next-action slot", () => {
  it("renders the soonest work item with its source, due date, and a course link", () => {
    stubCourses([{ id: "course-1", updated_at: "2026-07-01T00:00:00Z" }]);
    stubNextAction({ data: checkpointItem, isSuccess: true });

    renderDashboard();

    expect(screen.getByText("Your next step")).toBeTruthy();
    expect(screen.getByText("Lecture 3 checkpoint")).toBeTruthy();
    expect(screen.getByText("Checkpoint")).toBeTruthy();

    const link = screen.getByRole("link", { name: /open/i });
    expect(link.getAttribute("href")).toBe(
      "/student/courses/course-1/checkpoints"
    );
  });

  it("picks the most recently updated course to read the next action from", () => {
    stubCourses([
      { id: "older", updated_at: "2026-06-01T00:00:00Z" },
      { id: "newest", updated_at: "2026-07-05T00:00:00Z" },
    ]);
    stubNextAction({ data: null, isSuccess: true });

    renderDashboard();

    expect(mockUseNextAction).toHaveBeenCalledWith("newest");
  });

  it("shows the all-caught-up state when there is no next action", () => {
    stubCourses([{ id: "course-1", updated_at: "2026-07-01T00:00:00Z" }]);
    stubNextAction({ data: null, isSuccess: true });

    renderDashboard();

    expect(screen.getByText("You're all caught up")).toBeTruthy();
    expect(screen.queryByText("Your next step")).toBeNull();
  });

  it("renders no next-action card when the user has no courses", () => {
    stubCourses([]);
    stubNextAction({ data: undefined, isSuccess: false });

    renderDashboard();

    expect(screen.queryByText("Your next step")).toBeNull();
    expect(screen.queryByText("You're all caught up")).toBeNull();
    // Query stays disabled with no course id.
    expect(mockUseNextAction).toHaveBeenCalledWith("");
  });

  it("renders nothing in the slot for a caller the spine doesn't serve (error)", () => {
    stubCourses([{ id: "course-1", updated_at: "2026-07-01T00:00:00Z" }]);
    stubNextAction({ data: undefined, isSuccess: false });

    renderDashboard();

    expect(screen.queryByText("Your next step")).toBeNull();
    expect(screen.queryByText("You're all caught up")).toBeNull();
  });
});
