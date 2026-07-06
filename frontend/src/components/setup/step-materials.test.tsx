import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { StepMaterials } from "./step-materials";
import { useDocuments, type DocumentResponse } from "@/hooks/use-documents";
import { useSetStep } from "@/hooks/use-setup";

vi.mock("@/hooks/use-documents", () => ({
  useDocuments: vi.fn(),
}));

vi.mock("@/hooks/use-setup", () => ({
  useSetStep: vi.fn(),
}));

// The upload zone has its own suite; stub it so this suite focuses on the
// processing list and the `materials` flag gate.
vi.mock("@/components/documents/upload-zone", () => ({
  UploadZone: () => <div data-testid="upload-zone" />,
}));

const mockUseDocuments = vi.mocked(useDocuments);
const mockUseSetStep = vi.mocked(useSetStep);

function makeDoc(overrides: Partial<DocumentResponse> = {}): DocumentResponse {
  return {
    id: "doc1",
    course_id: "c1",
    uploaded_by: "u1",
    filename: "Week 1 Reading.pdf",
    file_type: "pdf",
    file_size: 1024,
    status: "completed",
    page_count: 3,
    word_count: 900,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderStep(onComplete = vi.fn()) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <StepMaterials courseId="c1" onComplete={onComplete} />
    </NextIntlClientProvider>
  );
}

let setStepMutate: ReturnType<typeof vi.fn>;

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  setStepMutate = vi.fn(async () => ({}));
  mockUseDocuments.mockReturnValue({ data: [], isLoading: false } as unknown as ReturnType<
    typeof useDocuments
  >);
  mockUseSetStep.mockReturnValue({
    mutateAsync: setStepMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useSetStep>);
});

describe("StepMaterials", () => {
  it("embeds the upload zone and shows the empty state with continue disabled", () => {
    renderStep();
    expect(screen.getByTestId("upload-zone")).toBeTruthy();
    expect(screen.getByText(/No materials uploaded yet/i)).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: /^Continue$/i }) as HTMLButtonElement)
        .disabled
    ).toBe(true);
  });

  it("shows per-document processing state and keeps continue gated while all are pending", () => {
    mockUseDocuments.mockReturnValue({
      data: [makeDoc({ status: "processing" })],
      isLoading: false,
    } as unknown as ReturnType<typeof useDocuments>);
    renderStep();
    expect(screen.getByText(/Week 1 Reading\.pdf/i)).toBeTruthy();
    expect(screen.getByText(/^Processing$/)).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: /^Continue$/i }) as HTMLButtonElement)
        .disabled
    ).toBe(true);
  });

  it("enables continue once a document is ready and flips the flag", async () => {
    const onComplete = vi.fn();
    mockUseDocuments.mockReturnValue({
      data: [makeDoc({ status: "completed" })],
      isLoading: false,
    } as unknown as ReturnType<typeof useDocuments>);
    renderStep(onComplete);
    expect(screen.getByText(/^Ready$/)).toBeTruthy();
    const continueBtn = screen.getByRole("button", { name: /^Continue$/i });
    expect((continueBtn as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(continueBtn);
    await waitFor(() =>
      expect(setStepMutate).toHaveBeenCalledWith({ step: "materials", done: true })
    );
    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
  });

  it("lets the teacher skip, flipping the flag without a ready document", async () => {
    const onComplete = vi.fn();
    renderStep(onComplete);
    fireEvent.click(screen.getByRole("button", { name: /Skip for now/i }));
    await waitFor(() =>
      expect(setStepMutate).toHaveBeenCalledWith({ step: "materials", done: true })
    );
    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
  });
});
