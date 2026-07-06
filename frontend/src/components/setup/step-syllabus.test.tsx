import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { StepSyllabus } from "./step-syllabus";
import {
  useApplySyllabusImport,
  useSyllabusImports,
  type SyllabusImport,
} from "@/hooks/use-syllabus";
import { useSetStep } from "@/hooks/use-setup";

vi.mock("@/hooks/use-syllabus", () => ({
  useSyllabusImports: vi.fn(),
  useApplySyllabusImport: vi.fn(),
}));

vi.mock("@/hooks/use-setup", () => ({
  useSetStep: vi.fn(),
}));

// The upload card is exercised in its own suite; stub it so this suite stays
// focused on the step's parse/apply state machine and flag flipping.
vi.mock("@/components/documents/syllabus-upload-card", () => ({
  SyllabusUploadCard: () => <div data-testid="syllabus-upload-card" />,
}));

const mockUseImports = vi.mocked(useSyllabusImports);
const mockUseApply = vi.mocked(useApplySyllabusImport);
const mockUseSetStep = vi.mocked(useSetStep);

function makeImport(overrides: Partial<SyllabusImport> = {}): SyllabusImport {
  return {
    id: "imp1",
    course_id: "c1",
    document_id: "d1",
    parsed_payload: { meetings: [{}, {}], objectives: [{}] },
    status: "parsed",
    error_message: null,
    applied_at: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderStep(onComplete = vi.fn()) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <StepSyllabus courseId="c1" onComplete={onComplete} />
    </NextIntlClientProvider>
  );
}

let applyMutate: ReturnType<typeof vi.fn>;
let setStepMutate: ReturnType<typeof vi.fn>;

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  applyMutate = vi.fn(async () => makeImport({ status: "applied" }));
  setStepMutate = vi.fn(async () => ({}));
  mockUseImports.mockReturnValue({ data: [], isLoading: false } as unknown as ReturnType<
    typeof useSyllabusImports
  >);
  mockUseApply.mockReturnValue({
    mutateAsync: applyMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useApplySyllabusImport>);
  mockUseSetStep.mockReturnValue({
    mutateAsync: setStepMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useSetStep>);
});

describe("StepSyllabus", () => {
  it("embeds the existing upload card and shows the empty state with no imports", () => {
    renderStep();
    expect(screen.getByTestId("syllabus-upload-card")).toBeTruthy();
    expect(screen.getByText(/No syllabus uploaded yet/i)).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: /^Continue$/i }) as HTMLButtonElement)
        .disabled
    ).toBe(true);
  });

  it("reflects a still-parsing import", () => {
    mockUseImports.mockReturnValue({
      data: [makeImport({ status: "pending", parsed_payload: {} })],
      isLoading: false,
    } as unknown as ReturnType<typeof useSyllabusImports>);
    renderStep();
    expect(screen.getByText(/Parsing your syllabus/i)).toBeTruthy();
  });

  it("offers apply for a parsed import and calls the apply mutation", async () => {
    mockUseImports.mockReturnValue({
      data: [makeImport({ status: "parsed" })],
      isLoading: false,
    } as unknown as ReturnType<typeof useSyllabusImports>);
    renderStep();
    // Parse-summary chips render the detected counts.
    expect(screen.getByText(/2 sessions/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Apply syllabus/i }));
    await waitFor(() => expect(applyMutate).toHaveBeenCalledTimes(1));
  });

  it("enables continue once an import is applied and flips the flag", async () => {
    const onComplete = vi.fn();
    mockUseImports.mockReturnValue({
      data: [makeImport({ status: "applied", applied_at: "2026-01-02T00:00:00Z" })],
      isLoading: false,
    } as unknown as ReturnType<typeof useSyllabusImports>);
    renderStep(onComplete);
    expect(screen.getByText(/Syllabus applied/i)).toBeTruthy();
    const continueBtn = screen.getByRole("button", { name: /^Continue$/i });
    expect((continueBtn as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(continueBtn);
    await waitFor(() =>
      expect(setStepMutate).toHaveBeenCalledWith({ step: "syllabus", done: true })
    );
    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
  });

  it("lets the teacher skip, flipping the flag without an applied import", async () => {
    const onComplete = vi.fn();
    renderStep(onComplete);
    fireEvent.click(screen.getByRole("button", { name: /Skip for now/i }));
    await waitFor(() =>
      expect(setStepMutate).toHaveBeenCalledWith({ step: "syllabus", done: true })
    );
    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
  });
});
