import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { StepReadinessSummary } from "./step-readiness-summary";
import {
  useReadinessSummary,
  type ReadinessSummary,
} from "@/hooks/use-readiness";

vi.mock("@/hooks/use-readiness", () => ({
  useReadinessSummary: vi.fn(),
}));

const mockUseReadinessSummary = vi.mocked(useReadinessSummary);

const CLAIM_LIMIT =
  "This is guidance to help you get oriented, not a placement decision.";

function makeSummary(overrides: Partial<ReadinessSummary> = {}): ReadinessSummary {
  return {
    completed_phases: ["eligibility_survey", "ready_check", "recommendation"],
    recommendation: {
      level_hint: "intermediate",
      confidence_average: 0.5,
      claim_limit: CLAIM_LIMIT,
    },
    answers: {},
    ...overrides,
  };
}

function stubSummary(ret: Partial<ReturnType<typeof useReadinessSummary>>): void {
  mockUseReadinessSummary.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    ...ret,
  } as unknown as ReturnType<typeof useReadinessSummary>);
}

function renderStep(onJoin = vi.fn(), onBack = vi.fn()) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <StepReadinessSummary
        courseId="course-1"
        code="ABCD2345"
        onJoin={onJoin}
        onBack={onBack}
      />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

describe("StepReadinessSummary (S011)", () => {
  it("assembles the completed phases into the recap", () => {
    stubSummary({ data: makeSummary() });
    renderStep();
    expect(screen.getByText("Eligibility survey")).toBeTruthy();
    expect(screen.getByText("Ready check")).toBeTruthy();
    expect(screen.getByText("Recommendation")).toBeTruthy();
  });

  it("repeats the claim-limit copy VERBATIM near the join CTA", () => {
    stubSummary({ data: makeSummary() });
    renderStep();
    expect(screen.getByText(CLAIM_LIMIT)).toBeTruthy();
    const banner = screen.getByText(CLAIM_LIMIT).closest("[data-tone]");
    expect(banner?.getAttribute("data-tone")).toBe("info");
  });

  it("triggers the terminal join on the CTA", () => {
    const onJoin = vi.fn();
    stubSummary({ data: makeSummary() });
    renderStep(onJoin);
    fireEvent.click(screen.getByRole("button", { name: "Join course" }));
    expect(onJoin).toHaveBeenCalledTimes(1);
  });

  it("handles an empty readiness set gracefully", () => {
    stubSummary({
      data: makeSummary({ completed_phases: [], recommendation: null }),
    });
    renderStep();
    expect(
      screen.getByText("No readiness steps were required for this course.")
    ).toBeTruthy();
    // Still offers the join CTA.
    expect(screen.getByRole("button", { name: "Join course" })).toBeTruthy();
  });

  it("shows an error state when the summary fails to load", () => {
    stubSummary({ isError: true });
    renderStep();
    expect(screen.getByText("We couldn't load your summary")).toBeTruthy();
  });
});
