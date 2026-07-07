import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { AssessmentQuizList } from "./assessment-quiz-list";
import {
  PRACTICE_CONFIG,
  filterByPurpose,
} from "./assessment-config";
import { useQuizzes, type QuizResponse } from "@/hooks/use-quizzes";

// The generate dialog pulls in auth / document-selection hooks; stub it so the
// list renders in isolation.
vi.mock("./generate-quiz-dialog", () => ({
  GenerateQuizDialog: () => null,
}));

vi.mock("@/hooks/use-quizzes", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/use-quizzes")>();
  return { ...actual, useQuizzes: vi.fn() };
});

const mockUseQuizzes = vi.mocked(useQuizzes);

function makeQuiz(overrides: Partial<QuizResponse> = {}): QuizResponse {
  return {
    id: "q1",
    course_id: "c1",
    title: "Vocabulary recall",
    description: null,
    quiz_type: "practice",
    purpose: "after_class",
    assessment_purpose: "practice",
    folder_id: null,
    is_published: false,
    question_count: 5,
    created_at: "2026-07-08T00:00:00Z",
    score_bearing: false,
    score_category_id: null,
    points: null,
    grading_mode: null,
    late_rule: null,
    due_at: null,
    close_at: null,
    ...overrides,
  };
}

function renderList() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <AssessmentQuizList courseId="c1" config={PRACTICE_CONFIG} />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

describe("filterByPurpose", () => {
  it("splits quizzes by assessment_purpose", () => {
    const quizzes = [
      makeQuiz({ id: "a", assessment_purpose: "practice" }),
      makeQuiz({ id: "b", assessment_purpose: "graded" }),
    ];
    expect(filterByPurpose(quizzes, "practice").map((q) => q.id)).toEqual(["a"]);
    expect(filterByPurpose(quizzes, "graded").map((q) => q.id)).toEqual(["b"]);
    expect(filterByPurpose(undefined, "practice")).toEqual([]);
  });
});

describe("AssessmentQuizList", () => {
  it("shows the designed empty state when there are no practice quizzes", () => {
    mockUseQuizzes.mockReturnValue({
      data: [makeQuiz({ assessment_purpose: "graded" })],
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useQuizzes>);

    renderList();
    expect(screen.getByText("No practice yet")).toBeTruthy();
  });

  it("renders a card with question count for a practice quiz", () => {
    mockUseQuizzes.mockReturnValue({
      data: [makeQuiz({ title: "Vocabulary recall", question_count: 5 })],
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useQuizzes>);

    renderList();
    expect(screen.getByText("Vocabulary recall")).toBeTruthy();
    expect(screen.getByText("5 questions")).toBeTruthy();
  });
});
