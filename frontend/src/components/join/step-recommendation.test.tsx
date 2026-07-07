import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { StepRecommendation } from "./step-recommendation";
import { useSubmitPhase } from "@/hooks/use-readiness";

vi.mock("@/hooks/use-readiness", () => ({
  useSubmitPhase: vi.fn(),
}));

const mockUseSubmitPhase = vi.mocked(useSubmitPhase);

// The exact copy the backend returns from `pilot.claim_limits['recommendation']`.
// The component MUST render this string verbatim — it is the trust boundary.
const CLAIM_LIMIT =
  "This is guidance to help you get oriented, not a placement decision.";

let mutate: ReturnType<typeof vi.fn>;

function stubSubmit(
  ret: Partial<ReturnType<typeof useSubmitPhase>> = {}
): void {
  mockUseSubmitPhase.mockReturnValue({
    mutate,
    isPending: false,
    isError: false,
    data: undefined,
    ...ret,
  } as unknown as ReturnType<typeof useSubmitPhase>);
}

function renderStep(onContinue = vi.fn(), onBack = vi.fn()) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <StepRecommendation
        courseId="course-1"
        code="ABCD2345"
        onContinue={onContinue}
        onBack={onBack}
      />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  mutate = vi.fn();
});

describe("StepRecommendation (S009)", () => {
  it("computes the recommendation on entry (POST recommendation, empty answers)", () => {
    stubSubmit({ isPending: true });
    renderStep();
    expect(mutate).toHaveBeenCalledWith({
      phase: "recommendation",
      answers: {},
    });
  });

  it("renders the claim-limit copy VERBATIM and prominently", async () => {
    stubSubmit({
      data: {
        phase: "recommendation",
        status: "completed",
        answers: {},
        result: {
          level_hint: "intermediate",
          confidence_average: 0.5,
          claim_limit: CLAIM_LIMIT,
        },
      } as unknown as ReturnType<typeof useSubmitPhase>["data"],
    });
    renderStep();

    // Verbatim claim-limit text is present in the DOM.
    expect(screen.getByText(CLAIM_LIMIT)).toBeTruthy();
    // And it sits in an info status banner (the prominent surface), not buried.
    const banner = screen.getByText(CLAIM_LIMIT).closest("[data-tone]");
    expect(banner?.getAttribute("data-tone")).toBe("info");
    // The coarse level hint is shown too.
    expect(screen.getByText("Intermediate level")).toBeTruthy();
  });

  it("shows a waiting state while the recommendation computes", () => {
    stubSubmit({ isPending: true });
    renderStep();
    expect(screen.getByText("Preparing your recommendation")).toBeTruthy();
  });

  it("advances to the deep preview on continue", () => {
    const onContinue = vi.fn();
    stubSubmit({
      data: {
        phase: "recommendation",
        status: "completed",
        answers: {},
        result: { level_hint: "foundation", claim_limit: CLAIM_LIMIT },
      } as unknown as ReturnType<typeof useSubmitPhase>["data"],
    });
    renderStep(onContinue);
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  it("offers a retry on error", async () => {
    stubSubmit({ isError: true });
    renderStep();
    expect(
      screen.getByText("We couldn't prepare your recommendation")
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    // Once on mount + once on retry.
    await waitFor(() => expect(mutate).toHaveBeenCalledTimes(2));
  });
});
