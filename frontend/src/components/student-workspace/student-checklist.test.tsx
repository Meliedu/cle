import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { StudentChecklist } from "./student-checklist";
import { useChecklist, type ChecklistItem } from "@/hooks/use-work-items";

vi.mock("@/hooks/use-work-items", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/hooks/use-work-items")>();
  return { ...actual, useChecklist: vi.fn() };
});

const mockUseChecklist = vi.mocked(useChecklist);

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

function renderChecklist() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <StudentChecklist courseId="c1" />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

describe("StudentChecklist", () => {
  it("groups items into to-do / missed / completed with one status chip each", () => {
    setChecklist([
      makeItem({ id: "wi-1", status: "pending", title: "Open checkpoint" }),
      makeItem({
        id: "wi-2",
        status: "completed",
        title: "Done practice",
        source_kind: "practice",
      }),
      makeItem({
        id: "wi-3",
        status: "missed",
        title: "Missed quiz",
        source_kind: "quiz",
      }),
    ]);

    renderChecklist();

    // group headings
    expect(screen.getByText("To do", { selector: "h3" })).toBeTruthy();
    expect(screen.getByText("Missed", { selector: "h3" })).toBeTruthy();
    expect(screen.getByText("Completed", { selector: "h3" })).toBeTruthy();
    // item titles
    expect(screen.getByText("Open checkpoint")).toBeTruthy();
    expect(screen.getByText("Done practice")).toBeTruthy();
    expect(screen.getByText("Missed quiz")).toBeTruthy();
    // status chips (localized)
    expect(screen.getByText("Completed", { selector: "span" })).toBeTruthy();
  });

  it("renders a designed empty state when the checklist is clear", () => {
    setChecklist([]);
    renderChecklist();
    expect(screen.getByText("Your checklist is clear")).toBeTruthy();
  });

  it("renders an error banner when the checklist fails", () => {
    setChecklist(undefined, { isError: true });
    renderChecklist();
    expect(screen.getByText("We couldn't load your checklist")).toBeTruthy();
  });
});
