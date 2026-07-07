import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { CourseInsightsView } from "./course-insights-view";
import {
  useCourseInsights,
  useSignal,
  useEvidenceSource,
  type CourseInsights,
} from "@/hooks/use-insights";
import { useCourseSignals } from "./use-teacher-signals";

vi.mock("@/hooks/use-insights", () => ({
  useCourseInsights: vi.fn(),
  useSignal: vi.fn(),
  useEvidenceSource: vi.fn(),
}));
vi.mock("./use-teacher-signals", () => ({ useCourseSignals: vi.fn() }));

const mockUseCourseInsights = vi.mocked(useCourseInsights);
const mockUseCourseSignals = vi.mocked(useCourseSignals);
const mockUseSignal = vi.mocked(useSignal);
const mockUseEvidenceSource = vi.mocked(useEvidenceSource);

function insights(overrides: Partial<CourseInsights> = {}): CourseInsights {
  return {
    course_id: "c1",
    has_evidence: true,
    cohort_mastery: {
      concept_count: 8,
      concepts_with_evidence: 5,
      avg_mastery: 0.62,
      weak_student_signals: 3,
    },
    alerts: { info: 2, warning: 1, critical: 1, total: 4 },
    review_queue: { open_alerts: 4, pending_notes: 2, total: 6 },
    ...overrides,
  };
}

function renderView() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <CourseInsightsView courseId="c1" />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  mockUseCourseSignals.mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useCourseSignals>);
  mockUseSignal.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useSignal>);
  mockUseEvidenceSource.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useEvidenceSource>);
});

describe("CourseInsightsView", () => {
  it("renders the designed empty state for an evidence-free course", () => {
    mockUseCourseInsights.mockReturnValue({
      data: insights({ has_evidence: false }),
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCourseInsights>);

    renderView();

    expect(screen.getByText("No evidence yet")).toBeTruthy();
    // Summary cards must NOT render when there is no evidence.
    expect(screen.queryByText("Cohort mastery")).toBeNull();
  });

  it("reshapes the payload into mastery, alert-severity, and review-queue cards", () => {
    mockUseCourseInsights.mockReturnValue({
      data: insights(),
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCourseInsights>);

    renderView();

    expect(screen.getByText("Cohort mastery")).toBeTruthy();
    // avg_mastery 0.62 → 62%
    expect(screen.getByText("62%")).toBeTruthy();
    // concepts_with_evidence 5 of 8
    expect(screen.getByText("5 of 8")).toBeTruthy();
    expect(screen.getByText("Signals to check")).toBeTruthy();
    expect(screen.getByText("Review queue")).toBeTruthy();
    expect(screen.queryByText("No evidence yet")).toBeNull();
  });

  it("surfaces a load-error banner when the read fails", () => {
    mockUseCourseInsights.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as unknown as ReturnType<typeof useCourseInsights>);

    renderView();

    expect(screen.getByText("We couldn't load these insights")).toBeTruthy();
  });
});
