import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { StepClassCode } from "./step-class-code";
import {
  useCourse,
  useDeactivateEnrollCode,
  useRotateEnrollCode,
  type CourseResponse,
} from "@/hooks/use-courses";
import { useSetStep } from "@/hooks/use-setup";

vi.mock("@/hooks/use-courses", () => ({
  useCourse: vi.fn(),
  useRotateEnrollCode: vi.fn(),
  useDeactivateEnrollCode: vi.fn(),
}));

vi.mock("@/hooks/use-setup", () => ({
  useSetStep: vi.fn(),
}));

const mockUseCourse = vi.mocked(useCourse);
const mockUseRotate = vi.mocked(useRotateEnrollCode);
const mockUseDeactivate = vi.mocked(useDeactivateEnrollCode);
const mockUseSetStep = vi.mocked(useSetStep);

function makeCourse(overrides: Partial<CourseResponse> = {}): CourseResponse {
  return {
    id: "c1",
    name: "LANG1511",
    code: "LANG1511",
    description: null,
    language: "zh",
    semester: null,
    instructor_id: "i1",
    enroll_code: "ABCD2345",
    enroll_code_active: true,
    settings: {},
    setup_status: "draft",
    setup_checklist: {},
    join_mode: "code",
    context_status: "draft",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderStep(onComplete = vi.fn()) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <StepClassCode courseId="c1" onComplete={onComplete} />
    </NextIntlClientProvider>
  );
}

let rotateMutate: ReturnType<typeof vi.fn>;
let deactivateMutate: ReturnType<typeof vi.fn>;
let setStepMutate: ReturnType<typeof vi.fn>;

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  rotateMutate = vi.fn(async () => makeCourse({ enroll_code: "WXYZ9876" }));
  deactivateMutate = vi.fn(async () => makeCourse({ enroll_code_active: false }));
  setStepMutate = vi.fn(async () => ({}));
  mockUseCourse.mockReturnValue({
    data: makeCourse(),
    isLoading: false,
  } as unknown as ReturnType<typeof useCourse>);
  mockUseRotate.mockReturnValue({
    mutateAsync: rotateMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useRotateEnrollCode>);
  mockUseDeactivate.mockReturnValue({
    mutateAsync: deactivateMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useDeactivateEnrollCode>);
  mockUseSetStep.mockReturnValue({
    mutateAsync: setStepMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useSetStep>);
});

describe("StepClassCode", () => {
  it("hides the code by default and reveals it on click", () => {
    renderStep();
    // The raw code is not shown until revealed.
    expect(screen.queryByText("ABCD2345")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Reveal code/i }));
    expect(screen.getByText("ABCD2345")).toBeTruthy();
  });

  it("shows the Active badge when joining is enabled", () => {
    renderStep();
    expect(screen.getByText(/^Active$/)).toBeTruthy();
  });

  it("rotates the code through the rotate endpoint", async () => {
    renderStep();
    fireEvent.click(screen.getByRole("button", { name: /New code/i }));
    await waitFor(() => expect(rotateMutate).toHaveBeenCalledTimes(1));
  });

  it("deactivates join access through the deactivate endpoint", async () => {
    renderStep();
    fireEvent.click(screen.getByRole("button", { name: /Deactivate join access/i }));
    await waitFor(() => expect(deactivateMutate).toHaveBeenCalledTimes(1));
  });

  it("offers reactivate (not deactivate) when the code is inactive", () => {
    mockUseCourse.mockReturnValue({
      data: makeCourse({ enroll_code_active: false }),
      isLoading: false,
    } as unknown as ReturnType<typeof useCourse>);
    renderStep();
    expect(screen.getByText(/^Inactive$/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Reactivate with new code/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Deactivate join access/i })).toBeNull();
  });

  it("flips the class_code flag when Continue is pressed", async () => {
    const onComplete = vi.fn();
    renderStep(onComplete);
    fireEvent.click(screen.getByRole("button", { name: /^Continue$/i }));
    await waitFor(() =>
      expect(setStepMutate).toHaveBeenCalledWith({ step: "class_code", done: true })
    );
    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
  });
});
