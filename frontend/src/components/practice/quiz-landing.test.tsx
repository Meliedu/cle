import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { QuizLanding } from "./quiz-landing";
import type { QuizDetailResponse } from "@/hooks/use-quizzes";

function makeQuiz(
  overrides: Partial<QuizDetailResponse> = {}
): QuizDetailResponse {
  return {
    id: "quiz-1",
    course_id: "course-1",
    title: "Unit 3 Assessment",
    description: "Covers chapters 5–7.",
    quiz_type: "practice",
    assessment_purpose: "graded",
    is_published: true,
    questions: [],
    created_at: "2026-07-01T00:00:00Z",
    score_bearing: true,
    score_category_id: "cat-1",
    points: 20,
    grading_mode: "auto",
    late_rule: "reject_late",
    due_at: "2026-07-10T15:30:00Z",
    close_at: "2026-07-12T23:59:00Z",
    ...overrides,
  };
}

function renderLanding(quiz: QuizDetailResponse, categoryName: string | null) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <QuizLanding
        quiz={quiz}
        courseId="course-1"
        questionCount={5}
        categoryName={categoryName}
        onStart={vi.fn()}
      />
    </NextIntlClientProvider>
  );
}

afterEach(() => cleanup());

describe("QuizLanding — score-bearing disclosure (S050)", () => {
  it("shows the score-bearing disclosure with points, category, and late rule BEFORE start", () => {
    renderLanding(makeQuiz(), "Quizzes");

    // The disclosure banner is the headline of the landing.
    expect(
      screen.getByText("This quiz counts toward your grade")
    ).toBeTruthy();

    // Details table surfaces the publish-settings fields.
    expect(screen.getByText("Quiz details")).toBeTruthy();
    expect(screen.getByText("Points")).toBeTruthy();
    expect(screen.getByText("20")).toBeTruthy();
    expect(screen.getByText("Quizzes")).toBeTruthy(); // resolved category name
    expect(screen.getByText("Not accepted after close")).toBeTruthy();
    expect(screen.getByText("Due")).toBeTruthy();
    expect(screen.getByText("Closes")).toBeTruthy();

    // Start is gated behind reading the disclosure — it's a distinct action.
    expect(screen.getByRole("button", { name: "Start quiz" })).toBeTruthy();
  });

  it("falls back to 'Not set' for absent fields", () => {
    renderLanding(
      makeQuiz({ points: null, late_rule: null, due_at: null }),
      null
    );
    // points + category + late + due all unresolved → multiple 'Not set'.
    expect(screen.getAllByText("Not set").length).toBeGreaterThanOrEqual(3);
  });

  it("hides the details table and shows a not-graded note when not score-bearing", () => {
    renderLanding(makeQuiz({ score_bearing: false }), null);

    expect(
      screen.getByText("This quiz isn't score-bearing")
    ).toBeTruthy();
    // No score details table for a non-graded quiz.
    expect(screen.queryByText("Quiz details")).toBeNull();
  });
});
