import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { StudentScores } from "./student-scores";
import { useMyScores, type StudentScoreRecord } from "@/hooks/use-scores";

vi.mock("@/hooks/use-scores", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/use-scores")>();
  return { ...actual, useMyScores: vi.fn() };
});

const mockUseMyScores = vi.mocked(useMyScores);

function setScores(
  data: StudentScoreRecord | null | undefined,
  extra: Partial<ReturnType<typeof useMyScores>> = {}
) {
  mockUseMyScores.mockReturnValue({
    data,
    isLoading: false,
    isError: false,
    ...extra,
  } as unknown as ReturnType<typeof useMyScores>);
}

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

function renderScores() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <StudentScores courseId="c1" />
    </NextIntlClientProvider>
  );
}

const RECORD: StudentScoreRecord = {
  user_id: "u1",
  full_name: "Sam Student",
  email: "sam@connect.ust.hk",
  categories: [
    {
      category_id: "cat1",
      category_name: "Quizzes",
      weight: 40,
      points_pool: 20,
      earned_points: 8,
      possible_points: 10,
      artifacts: [
        {
          kind: "quiz",
          artifact_id: "q1",
          title: "Unit 1 quiz",
          category_id: "cat1",
          points: 10,
          score_pct: 80,
          earned_points: 8,
          submitted: true,
        },
      ],
    },
  ],
};

describe("StudentScores", () => {
  it("renders per-category rollup with per-artifact earned/possible", () => {
    setScores(RECORD);
    renderScores();

    expect(screen.getByText("Quizzes")).toBeTruthy();
    expect(screen.getByText("40% of grade")).toBeTruthy();
    expect(screen.getByText("Unit 1 quiz")).toBeTruthy();
    // earned/possible appears on both the category total and the artifact row
    expect(screen.getAllByText("8 / 10 pts").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Submitted")).toBeTruthy();
    expect(screen.getByText("80%")).toBeTruthy();
  });

  it("renders the designed no-scores state when the record is null", () => {
    setScores(null);
    renderScores();
    expect(screen.getByText("No scores yet")).toBeTruthy();
  });

  it("renders an error banner when the record fails to load", () => {
    setScores(undefined, { isError: true });
    renderScores();
    expect(screen.getByText("We couldn't load your record")).toBeTruthy();
  });
});
