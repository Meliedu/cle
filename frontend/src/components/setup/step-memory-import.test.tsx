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
import { StepMemoryImport } from "./step-memory-import";
import { ApiError } from "@/lib/api";
import {
  useImportMemory,
  useNextTermSuggestions,
  type NextTermSuggestion,
} from "@/hooks/use-memory";

vi.mock("@/hooks/use-memory", () => ({
  useNextTermSuggestions: vi.fn(),
  useImportMemory: vi.fn(),
}));

const mockUseSuggestions = vi.mocked(useNextTermSuggestions);
const mockUseImport = vi.mocked(useImportMemory);

function makeSuggestion(
  overrides: Partial<NextTermSuggestion> = {}
): NextTermSuggestion {
  return {
    id: "s1",
    course_id: "c2",
    learning_note_id: null,
    kind: "action",
    relationship_summary: null,
    action_summary: { summary: "Add a tone-contrast warm-up in week 2" },
    outcome_summary: null,
    instructor_comment: null,
    carry_forward: true,
    decision: "carry_forward",
    decided_by: "i1",
    decided_at: "2026-01-01T00:00:00Z",
    report_history: [],
    created_at: "2026-01-01T00:00:00Z",
    source_course_id: "prev1",
    source_course_code: "LANG1512",
    source_course_name: "English for Academic Purposes (2025 Fall)",
    ...overrides,
  };
}

let importMutate: ReturnType<typeof vi.fn>;

function renderStep(onSkip = vi.fn()) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <StepMemoryImport courseId="c2" onSkip={onSkip} />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  importMutate = vi.fn();
  mockUseImport.mockReturnValue({
    mutate: importMutate,
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof useImportMemory>);
});

describe("StepMemoryImport", () => {
  it("shows the skippable empty state when there is no prior-term memory", () => {
    mockUseSuggestions.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useNextTermSuggestions>);

    renderStep();

    expect(screen.getByText("No prior-term memory to import")).toBeTruthy();
    expect(
      screen.getAllByRole("button", { name: /Skip for now/i }).length
    ).toBeGreaterThan(0);
  });

  it("gates import behind a selection and passes the chosen ids", async () => {
    mockUseSuggestions.mockReturnValue({
      data: [makeSuggestion()],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useNextTermSuggestions>);

    renderStep();

    // Nothing selected → the import button is disabled (the gate).
    const importButton = screen.getByRole("button", { name: /Import selected/i });
    expect(importButton).toHaveProperty("disabled", true);

    // Select the suggestion, then import — the mutation carries the id.
    fireEvent.click(screen.getByRole("checkbox"));
    expect(importButton).toHaveProperty("disabled", false);
    fireEvent.click(importButton);

    await waitFor(() => expect(importMutate).toHaveBeenCalledTimes(1));
    expect(importMutate.mock.calls[0][0]).toEqual({ item_ids: ["s1"] });
  });

  it("surfaces a MEMORY_UNDECIDED 409 as a banner", () => {
    mockUseSuggestions.mockReturnValue({
      data: [makeSuggestion()],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useNextTermSuggestions>);
    mockUseImport.mockReturnValue({
      mutate: importMutate,
      isPending: false,
      isError: true,
      error: new ApiError(409, "Conflict", undefined, "MEMORY_UNDECIDED"),
    } as unknown as ReturnType<typeof useImportMemory>);

    renderStep();

    expect(
      screen.getByText(/no longer marked to carry forward/i)
    ).toBeTruthy();
  });
});
