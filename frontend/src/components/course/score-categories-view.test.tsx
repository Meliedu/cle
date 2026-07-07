import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { ScoreCategoriesView } from "./score-categories-view";
import { useScoreCategories, type ScoreCategory } from "@/hooks/use-setup";

vi.mock("@/hooks/use-setup", () => ({
  useScoreCategories: vi.fn(),
}));

const mockUseScoreCategories = vi.mocked(useScoreCategories);

function makeCategory(overrides: Partial<ScoreCategory> = {}): ScoreCategory {
  return {
    id: "s1",
    course_id: "c1",
    name: "Checkpoints",
    weight: 40,
    points_pool: null,
    sort: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderView() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ScoreCategoriesView courseId="c1" />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  mockUseScoreCategories.mockReturnValue({
    data: [
      makeCategory(),
      makeCategory({ id: "s2", name: "Practice", weight: null, sort: 1 }),
    ],
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useScoreCategories>);
});

describe("ScoreCategoriesView", () => {
  it("renders the score categories with weight and status", () => {
    renderView();
    expect(screen.getByText("Checkpoints")).toBeTruthy();
    expect(screen.getByText("40%")).toBeTruthy();
    // A graded category counts toward the record.
    expect(screen.getByText(/Counts toward record/i)).toBeTruthy();
  });

  it("marks a null-weight category as practice only", () => {
    renderView();
    expect(screen.getByText(/Practice only/i)).toBeTruthy();
  });

  it("links to the setup score-policy step to edit", () => {
    renderView();
    const link = screen.getByRole("link", { name: /Edit in setup/i });
    expect(link.getAttribute("href")).toBe(
      "/teacher/courses/c1/setup?step=score_policy"
    );
  });

  it("renders the empty state when there are no categories", () => {
    mockUseScoreCategories.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useScoreCategories>);
    renderView();
    expect(screen.getByText(/No score categories yet/i)).toBeTruthy();
  });
});
