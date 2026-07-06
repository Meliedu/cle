import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../../../../../messages/en.json";
import { SetupWizard } from "./setup-wizard";
import { useSetupState, type SetupState } from "@/hooks/use-setup";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/teacher/courses/c1/setup",
  useSearchParams: () => new URLSearchParams(""),
}));

vi.mock("@/components/setup/step-basics", () => ({
  StepBasics: () => <div data-testid="step-basics">basics-content</div>,
}));

vi.mock("@/components/setup/step-syllabus", () => ({
  StepSyllabus: () => <div data-testid="step-syllabus">syllabus-content</div>,
}));

vi.mock("@/components/setup/step-materials", () => ({
  StepMaterials: () => <div data-testid="step-materials">materials-content</div>,
}));

vi.mock("@/hooks/use-setup", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/use-setup")>();
  return { ...actual, useSetupState: vi.fn() };
});

const mockUseSetupState = vi.mocked(useSetupState);

const STATE: SetupState = {
  setup_status: "in_review",
  context_status: "draft",
  steps: { basics: true, syllabus: false },
  missing: ["syllabus"],
};

function renderWizard() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <SetupWizard courseId="c1" />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("SetupWizard", () => {
  it("renders every setup step on the rail and shows the active step's content", () => {
    mockUseSetupState.mockReturnValue({
      data: STATE,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useSetupState>);

    renderWizard();

    // 9 SETUP_STEP_KEYS → 9 rail items.
    expect(screen.getAllByRole("listitem")).toHaveLength(9);
    // basics is complete; with no ?step the first incomplete (syllabus) is current.
    expect(
      screen.getByRole("listitem", { name: /Basics/ }).getAttribute("data-status")
    ).toBe("complete");
    expect(
      screen.getByRole("listitem", { name: /Syllabus/ }).getAttribute("data-status")
    ).toBe("current");
  });

  it("shows the basics step content when basics is the active step", () => {
    mockUseSetupState.mockReturnValue({
      data: { ...STATE, steps: {}, missing: [] },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useSetupState>);

    renderWizard();

    expect(
      screen.getByRole("listitem", { name: /Basics/ }).getAttribute("data-status")
    ).toBe("current");
    expect(screen.getByTestId("step-basics")).toBeTruthy();
  });

  it("renders a loading skeleton while setup state resolves", () => {
    mockUseSetupState.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useSetupState>);

    const { container } = renderWizard();
    // No rail while loading — only skeleton placeholders.
    expect(screen.queryByRole("list")).toBeNull();
    expect(container.querySelector('[class*="animate-pulse"]')).toBeTruthy();
  });
});
