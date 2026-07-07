import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { StepReview } from "./step-review";
import { ApiError } from "@/lib/api";
import {
  usePublishSetup,
  useSetupAnalysis,
  useSetupState,
  type SetupState,
} from "@/hooks/use-setup";
import { useCourse } from "@/hooks/use-courses";

// Happy-path spec (P1 T17): the review checklist → publish flow. The e2e/session
// infra is unavailable offline (P0 handoff `role-routing` limitation), so this
// drives `StepReview` against fully-mocked hooks and asserts both branches:
//   1. all steps complete → publish resolves → T027 success screen renders;
//   2. publish rejected 409 SETUP_INCOMPLETE → T028 blocked state lists missing.
vi.mock("@/hooks/use-setup", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/use-setup")>();
  return {
    ...actual,
    useSetupState: vi.fn(),
    useSetupAnalysis: vi.fn(),
    usePublishSetup: vi.fn(),
  };
});

vi.mock("@/hooks/use-courses", () => ({
  useCourse: vi.fn(),
}));

const mockUseSetupState = vi.mocked(useSetupState);
const mockUseSetupAnalysis = vi.mocked(useSetupAnalysis);
const mockUsePublishSetup = vi.mocked(usePublishSetup);
const mockUseCourse = vi.mocked(useCourse);

const COMPLETE_STEPS: SetupState["steps"] = {
  basics: true,
  syllabus: true,
  materials: true,
  schedule: true,
  analyzer_review: true,
  ilo_map: true,
  checkpoints: true,
  score_policy: true,
  class_code: true,
};

function setupState(overrides: Partial<SetupState> = {}): SetupState {
  return {
    setup_status: "in_review",
    context_status: "draft",
    steps: COMPLETE_STEPS,
    missing: [],
    ...overrides,
  };
}

function mockState(state: SetupState) {
  mockUseSetupState.mockReturnValue({
    data: state,
    isLoading: false,
  } as unknown as ReturnType<typeof useSetupState>);
}

function mockAnalysis() {
  mockUseSetupAnalysis.mockReturnValue({
    data: { ready: true, analysis: null },
  } as unknown as ReturnType<typeof useSetupAnalysis>);
}

function mockCourse() {
  mockUseCourse.mockReturnValue({
    data: {
      id: "c1",
      name: "LANG1512",
      description: "English for Academic Purposes",
      semester: "2026 Spring",
      enroll_code: "ABCD2345",
      enroll_code_active: true,
    },
  } as unknown as ReturnType<typeof useCourse>);
}

function renderReview() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <StepReview courseId="c1" onNavigate={vi.fn()} />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  mockAnalysis();
  mockCourse();
});

describe("StepReview", () => {
  it("publishes when every step is complete and shows the success screen", async () => {
    mockState(setupState());
    const mutateAsync = vi.fn().mockResolvedValue(setupState({ setup_status: "published" }));
    mockUsePublishSetup.mockReturnValue({
      mutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof usePublishSetup>);

    renderReview();

    // The checklist summarizes all nine setup steps.
    expect(screen.getByText(messages.teacher.setup.review.checklistTitle)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Publish course/ }));

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledTimes(1);
      // T027 — publish success confirmation.
      expect(
        screen.getByRole("heading", { name: messages.teacher.setup.publishSuccess.title })
      ).toBeTruthy();
    });
  });

  it("shows the blocked missing-source state on a 409 SETUP_INCOMPLETE", async () => {
    mockState(
      setupState({
        steps: { ...COMPLETE_STEPS, schedule: false, checkpoints: false },
        missing: ["schedule", "checkpoints"],
      })
    );
    const mutateAsync = vi
      .fn()
      .mockRejectedValue(new ApiError(409, "incomplete", undefined, "SETUP_INCOMPLETE"));
    mockUsePublishSetup.mockReturnValue({
      mutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof usePublishSetup>);

    renderReview();

    fireEvent.click(screen.getByRole("button", { name: /Publish course/ }));

    await waitFor(() => {
      // T028 — blocked state with the typed gate banner...
      expect(screen.getByText(messages.teacher.setup.missingSource.bannerTitle)).toBeTruthy();
      // ...listing each incomplete step by its label.
      expect(screen.getByText(messages.teacher.setup.steps.schedule)).toBeTruthy();
      expect(screen.getByText(messages.teacher.setup.steps.checkpoints)).toBeTruthy();
    });
  });
});
