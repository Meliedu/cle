import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { EffectivenessTracker } from "./effectiveness-tracker";
import {
  useEffectiveness,
  type Effectiveness,
  type OutcomeStatusCounts,
} from "@/hooks/use-insights";

vi.mock("@/hooks/use-insights", () => ({ useEffectiveness: vi.fn() }));

const mockUseEffectiveness = vi.mocked(useEffectiveness);

function counts(overrides: Partial<OutcomeStatusCounts> = {}): OutcomeStatusCounts {
  return {
    pending: 0,
    completed: 0,
    improved: 0,
    persistent: 0,
    resolved: 0,
    needs_review: 0,
    carried_forward: 0,
    ...overrides,
  };
}

function effectiveness(overrides: Partial<Effectiveness> = {}): Effectiveness {
  return {
    course_id: "c1",
    has_evidence: true,
    total: 10,
    by_status: counts({ improved: 6, persistent: 3, resolved: 1 }),
    by_action_type: [
      {
        action_type: "revisit_checkpoint",
        total: 7,
        by_status: counts({ improved: 5, persistent: 2 }),
      },
    ],
    ...overrides,
  };
}

function renderTracker() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <EffectivenessTracker courseId="c1" />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("EffectivenessTracker", () => {
  it("renders the designed no-evidence state when there are no outcomes", () => {
    mockUseEffectiveness.mockReturnValue({
      data: effectiveness({ has_evidence: false, total: 0 }),
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useEffectiveness>);

    renderTracker();

    expect(screen.getByText("No follow-up outcomes yet")).toBeTruthy();
  });

  it("reshapes outcome_checks into an improved-vs-persistent breakdown by status", () => {
    mockUseEffectiveness.mockReturnValue({
      data: effectiveness(),
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useEffectiveness>);

    renderTracker();

    expect(screen.getByText("Improved")).toBeTruthy();
    expect(screen.getByText("Still persisting")).toBeTruthy();
    // improved bucket count 6 is surfaced
    expect(screen.getByText("6")).toBeTruthy();
    // by-action-type breakdown labels the follow-up type
    expect(screen.getByText("Revisit checkpoint")).toBeTruthy();
    expect(screen.getByText("By follow-up type")).toBeTruthy();
  });

  it("surfaces a load-error banner when the read fails", () => {
    mockUseEffectiveness.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as unknown as ReturnType<typeof useEffectiveness>);

    renderTracker();

    expect(screen.getByText("We couldn't load effectiveness")).toBeTruthy();
  });
});
