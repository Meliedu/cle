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
import { StepDiagnostic } from "./step-diagnostic";
import { usePilotConfig } from "@/hooks/use-pilot-config";
import { useSubmitPhase } from "@/hooks/use-readiness";
import type { PilotConfig } from "@/lib/pilot-config";

vi.mock("@/hooks/use-pilot-config", () => ({
  usePilotConfig: vi.fn(),
}));

vi.mock("@/hooks/use-readiness", () => ({
  useSubmitPhase: vi.fn(),
}));

const mockUsePilotConfig = vi.mocked(usePilotConfig);
const mockUseSubmitPhase = vi.mocked(useSubmitPhase);

function makeConfig(overrides: Partial<PilotConfig> = {}): PilotConfig {
  return {
    id: "cle",
    institution: "HKUST",
    course_family: "LANG",
    terminology: {},
    skill_taxonomy: [],
    confidence_scale: { min: -2, max: 2, labels: {} },
    score_category_defaults: [],
    readiness: [],
    report_cadence: { weekly: true, end_term: true },
    role_rules: {},
    locales: ["en"],
    claim_limits: {},
    ...overrides,
  };
}

function renderStep(onDone = vi.fn(), onBack = vi.fn()) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <StepDiagnostic
        courseId="course-1"
        code="ABCD2345"
        onDone={onDone}
        onBack={onBack}
      />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  mockUseSubmitPhase.mockReturnValue({
    mutateAsync: vi.fn(async () => ({})),
    isPending: false,
    isError: false,
  } as unknown as ReturnType<typeof useSubmitPhase>);
});

describe("StepDiagnostic (S008 — optional)", () => {
  it("shows a skip card when the pilot config has no diagnostic phase", () => {
    mockUsePilotConfig.mockReturnValue({
      config: makeConfig(),
      isLoaded: true,
      isError: false,
    });
    renderStep();
    expect(screen.getByText("No diagnostic for this course")).toBeTruthy();
  });

  it("advances (never blocks) from the skip card via Continue", () => {
    const onDone = vi.fn();
    mockUsePilotConfig.mockReturnValue({
      config: makeConfig(),
      isLoaded: true,
      isError: false,
    });
    renderStep(onDone);
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("renders the config-driven diagnostic when one exists", async () => {
    mockUsePilotConfig.mockReturnValue({
      config: makeConfig({
        readiness: [
          {
            phase: "diagnostic",
            title: "Quick diagnostic",
            intro: "A few questions to place you.",
            questions: [
              {
                id: "d1",
                kind: "single_choice",
                prompt: "Pick one",
                options: ["A", "B"],
              },
            ],
          },
        ],
      }),
      isLoaded: true,
      isError: false,
    });
    renderStep();
    await waitFor(() =>
      expect(screen.getByText("Quick diagnostic")).toBeTruthy()
    );
    expect(screen.getByText("Pick one")).toBeTruthy();
  });
});
