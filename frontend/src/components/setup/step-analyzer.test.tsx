import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { StepAnalyzer } from "./step-analyzer";
import {
  useAnalyzeSetup,
  useSetStep,
  useSetupAnalysis,
  type SetupAnalysis,
} from "@/hooks/use-setup";

vi.mock("@/hooks/use-setup", () => ({
  useAnalyzeSetup: vi.fn(),
  useSetStep: vi.fn(),
  useSetupAnalysis: vi.fn(),
}));

const mockUseAnalyzeSetup = vi.mocked(useAnalyzeSetup);
const mockUseSetStep = vi.mocked(useSetStep);
const mockUseSetupAnalysis = vi.mocked(useSetupAnalysis);

function readyAnalysis(hasMissing: boolean): SetupAnalysis {
  return {
    ready: true,
    analysis: {
      course_id: "c1",
      counts: { documents: 3, meetings: 2, objectives: 4 },
      missing_sources: hasMissing
        ? [
            {
              kind: "session_without_material",
              id: "m1",
              label: "Week 1 — Introductions",
            },
          ]
        : [],
      has_missing_sources: hasMissing,
    },
  };
}

function renderStep(props: Partial<Parameters<typeof StepAnalyzer>[0]> = {}) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <StepAnalyzer courseId="c1" {...props} />
    </NextIntlClientProvider>
  );
}

let analyzeMutate: ReturnType<typeof vi.fn>;
let setStepMutate: ReturnType<typeof vi.fn>;

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  analyzeMutate = vi.fn(async () => undefined);
  setStepMutate = vi.fn(async () => ({}));
  mockUseAnalyzeSetup.mockReturnValue({
    mutateAsync: analyzeMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useAnalyzeSetup>);
  mockUseSetStep.mockReturnValue({
    mutateAsync: setStepMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useSetStep>);
  // Default: no prior analysis result.
  mockUseSetupAnalysis.mockReturnValue({
    data: { ready: false, analysis: null },
    isLoading: false,
  } as unknown as ReturnType<typeof useSetupAnalysis>);
});

describe("StepAnalyzer", () => {
  it("triggers the analyze job and shows the running state when Run analysis is pressed", async () => {
    renderStep();
    expect(screen.getByRole("button", { name: /Run analysis/i })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Run analysis/i }));
    await waitFor(() => expect(analyzeMutate).toHaveBeenCalledTimes(1));
    expect(screen.getByText(/Analyzing your course/i)).toBeTruthy();
  });

  it("renders the course map counts and a missing-source warning with a fix link", () => {
    mockUseSetupAnalysis.mockReturnValue({
      data: readyAnalysis(true),
      isLoading: false,
    } as unknown as ReturnType<typeof useSetupAnalysis>);
    const onNavigate = vi.fn();
    renderStep({ onNavigate });

    // Counts from the analysis result.
    expect(screen.getByText("3")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("4")).toBeTruthy();
    // Missing-source warning + the flagged item.
    expect(screen.getByText(/needs a source/i)).toBeTruthy();
    expect(screen.getByText(/Week 1 — Introductions/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /^Fix$/i }));
    expect(onNavigate).toHaveBeenCalledWith("materials");
  });

  it("flips the analyzer_review flag on Continue even with missing sources", async () => {
    mockUseSetupAnalysis.mockReturnValue({
      data: readyAnalysis(true),
      isLoading: false,
    } as unknown as ReturnType<typeof useSetupAnalysis>);
    const onComplete = vi.fn();
    renderStep({ onComplete });

    fireEvent.click(screen.getByRole("button", { name: /^Continue$/i }));
    await waitFor(() =>
      expect(setStepMutate).toHaveBeenCalledWith({ step: "analyzer_review", done: true })
    );
    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
  });
});
