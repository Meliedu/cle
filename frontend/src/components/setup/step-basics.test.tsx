import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { StepBasics } from "./step-basics";
import { useCourse, useUpdateCourse } from "@/hooks/use-courses";
import { useSetStep } from "@/hooks/use-setup";

vi.mock("@/hooks/use-courses", () => ({
  useCourse: vi.fn(),
  useUpdateCourse: vi.fn(),
}));

vi.mock("@/hooks/use-setup", () => ({
  useSetStep: vi.fn(),
}));

const mockUseCourse = vi.mocked(useCourse);
const mockUseUpdateCourse = vi.mocked(useUpdateCourse);
const mockUseSetStep = vi.mocked(useSetStep);

const COURSE = {
  id: "c1",
  name: "English for Academic Purposes",
  code: "LANG1512",
  description: "Intro course",
  language: "English",
  semester: "2024 Spring",
  instructor_id: "u1",
  enroll_code: "ABCD2345",
  settings: {},
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function renderStep(onComplete = vi.fn()) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <StepBasics courseId="c1" onComplete={onComplete} />
    </NextIntlClientProvider>
  );
}

function wrap(node: ReactNode) {
  return (
    <NextIntlClientProvider locale="en" messages={messages}>
      {node}
    </NextIntlClientProvider>
  );
}

let updateMutate: ReturnType<typeof vi.fn>;
let setStepMutate: ReturnType<typeof vi.fn>;

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  updateMutate = vi.fn(async () => COURSE);
  setStepMutate = vi.fn(async () => ({}));
  mockUseCourse.mockReturnValue({ data: COURSE, isLoading: false } as ReturnType<
    typeof useCourse
  >);
  mockUseUpdateCourse.mockReturnValue({
    mutateAsync: updateMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useUpdateCourse>);
  mockUseSetStep.mockReturnValue({
    mutateAsync: setStepMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useSetStep>);
});

describe("StepBasics", () => {
  it("hydrates the form from the loaded course", () => {
    renderStep();
    expect((screen.getByLabelText(/Course name/i) as HTMLInputElement).value).toBe(
      "English for Academic Purposes"
    );
    expect((screen.getByLabelText(/Course code/i) as HTMLInputElement).value).toBe(
      "LANG1512"
    );
    expect((screen.getByLabelText(/Term/i) as HTMLInputElement).value).toBe(
      "2024 Spring"
    );
  });

  it("blocks saving with an empty name and does not call the mutations", async () => {
    renderStep();
    fireEvent.change(screen.getByLabelText(/Course name/i), {
      target: { value: "  " },
    });
    fireEvent.click(screen.getByRole("button", { name: /Save & continue/i }));

    expect(await screen.findByText(/Course name is required/i)).toBeTruthy();
    expect(updateMutate).not.toHaveBeenCalled();
    expect(setStepMutate).not.toHaveBeenCalled();
  });

  it("saves the course, flips the basics flag, then advances", async () => {
    const onComplete = vi.fn();
    renderStep(onComplete);
    fireEvent.change(screen.getByLabelText(/Course name/i), {
      target: { value: "Mandarin I" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Save & continue/i }));

    await waitFor(() => expect(updateMutate).toHaveBeenCalledTimes(1));
    expect(updateMutate).toHaveBeenCalledWith(
      expect.objectContaining({ name: "Mandarin I", code: "LANG1512" })
    );
    await waitFor(() =>
      expect(setStepMutate).toHaveBeenCalledWith({ step: "basics", done: true })
    );
    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
  });

  it("renders the live preview from the current field values", () => {
    renderStep();
    const { getByText } = screen;
    expect(getByText("LANG1512")).toBeTruthy();
    expect(getByText(/What students will see/i)).toBeTruthy();
  });

  it("mounts inside an intl provider without throwing", () => {
    expect(() => render(wrap(<StepBasics courseId="c1" />))).not.toThrow();
  });
});
