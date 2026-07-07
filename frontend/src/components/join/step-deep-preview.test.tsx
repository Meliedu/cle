import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { StepDeepPreview } from "./step-deep-preview";
import { useCoursePreview, type CoursePreview } from "@/hooks/use-readiness";
import { ApiError } from "@/lib/api";

vi.mock("@/hooks/use-readiness", () => ({
  useCoursePreview: vi.fn(),
}));

const mockUseCoursePreview = vi.mocked(useCoursePreview);

function makePreview(overrides: Partial<CoursePreview> = {}): CoursePreview {
  return {
    id: "course-1",
    name: "LANG1511",
    code: "ABCD2345",
    language: "zh",
    description: "An academic Chinese course.",
    is_open: true,
    join_mode: "code",
    depth: "deep",
    detail: { sessions: 12, objectives: 6 },
    ...overrides,
  };
}

function stubPreview(ret: Partial<ReturnType<typeof useCoursePreview>>): void {
  mockUseCoursePreview.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    ...ret,
  } as unknown as ReturnType<typeof useCoursePreview>);
}

function renderStep(onContinue = vi.fn(), onBack = vi.fn()) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <StepDeepPreview
        courseId="course-1"
        code="ABCD2345"
        onContinue={onContinue}
        onBack={onBack}
      />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

describe("StepDeepPreview (S010)", () => {
  it("requests the deep preview with the resolved course id + code", () => {
    stubPreview({ data: makePreview() });
    renderStep();
    expect(mockUseCoursePreview).toHaveBeenCalledWith(
      "course-1",
      "ABCD2345",
      "deep"
    );
  });

  it("renders session + objective counts when the course is open", () => {
    stubPreview({ data: makePreview() });
    renderStep();
    expect(screen.getByText("Sessions")).toBeTruthy();
    expect(screen.getByText("12")).toBeTruthy();
    expect(screen.getByText("Objectives")).toBeTruthy();
    expect(screen.getByText("6")).toBeTruthy();
  });

  it("shows the not-open state when the gate returns SETUP_NOT_OPEN (409)", () => {
    stubPreview({
      isError: true,
      error: new ApiError(409, "not open", "not open", "SETUP_NOT_OPEN"),
    });
    renderStep();
    expect(screen.getByText("Not open for joining yet")).toBeTruthy();
    // The teaser counts are NOT shown when blocked.
    expect(screen.queryByText("Sessions")).toBeNull();
  });

  it("still lets the student continue when blocked (never dead-ends)", () => {
    const onContinue = vi.fn();
    stubPreview({
      isError: true,
      error: new ApiError(409, "not open", "not open", "SETUP_NOT_OPEN"),
    });
    renderStep(onContinue);
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  it("advances to the summary on continue when open", () => {
    const onContinue = vi.fn();
    stubPreview({ data: makePreview() });
    renderStep(onContinue);
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onContinue).toHaveBeenCalledTimes(1);
  });
});
