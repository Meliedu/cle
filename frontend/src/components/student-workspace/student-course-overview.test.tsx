import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { StudentCourseOverview } from "./student-course-overview";
import {
  useChecklist,
  useNextAction,
  type ChecklistItem,
} from "@/hooks/use-work-items";

vi.mock("@/hooks/use-work-items", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/hooks/use-work-items")>();
  return { ...actual, useChecklist: vi.fn(), useNextAction: vi.fn() };
});

const mockUseChecklist = vi.mocked(useChecklist);
const mockUseNextAction = vi.mocked(useNextAction);

function makeItem(overrides: Partial<ChecklistItem> = {}): ChecklistItem {
  return {
    id: "wi-1",
    course_id: "c1",
    source_kind: "checkpoint",
    source_id: "cp-1",
    title: "Session 1 checkpoint",
    required: true,
    score_bearing: false,
    due_at: "2026-07-10T15:59:00Z",
    close_at: "2026-07-10T15:59:00Z",
    visible_from: null,
    status: "pending",
    ...overrides,
  };
}

function setChecklist(
  data: readonly ChecklistItem[] | undefined,
  extra: Partial<ReturnType<typeof useChecklist>> = {}
) {
  mockUseChecklist.mockReturnValue({
    data,
    isLoading: false,
    isError: false,
    ...extra,
  } as unknown as ReturnType<typeof useChecklist>);
}

function setNextAction(data: ChecklistItem | null) {
  mockUseNextAction.mockReturnValue({
    data,
  } as unknown as ReturnType<typeof useNextAction>);
}

function renderOverview() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <StudentCourseOverview courseId="c1" />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

describe("StudentCourseOverview", () => {
  it("renders the next action and progress from the checklist spine", () => {
    const items = [
      makeItem({ id: "wi-1", status: "completed" }),
      makeItem({ id: "wi-2", status: "pending", title: "Read chapter 3" }),
    ];
    setChecklist(items);
    setNextAction(items[1]);

    renderOverview();

    // next-action headline + start CTA
    expect(screen.getByText("Next up")).toBeTruthy();
    expect(screen.getByText("Read chapter 3")).toBeTruthy();
    expect(screen.getByText("Start")).toBeTruthy();
    // progress: 1 of 2 done => 50%
    expect(screen.getByText("50%")).toBeTruthy();
    expect(screen.getByText("1 of 2 tasks done")).toBeTruthy();
  });

  it("shows the caught-up state when there is no next action", () => {
    setChecklist([makeItem({ status: "completed" })]);
    setNextAction(null);

    renderOverview();

    expect(screen.getByText("You're all caught up")).toBeTruthy();
    expect(screen.getByText("100%")).toBeTruthy();
  });

  it("shows a designed empty state when the course has no work items", () => {
    setChecklist([]);
    setNextAction(null);

    renderOverview();

    expect(screen.getByText("Nothing to do yet")).toBeTruthy();
  });

  it("renders an error banner when the checklist fails to load", () => {
    setChecklist(undefined, { isError: true });
    setNextAction(null);

    renderOverview();

    expect(screen.getByText("We couldn't load your checklist")).toBeTruthy();
  });
});
