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
import { CourseMemoryView } from "./course-memory-view";
import {
  useMemory,
  useNextTermSuggestions,
  useDecideMemory,
  type MemoryItemResponse,
} from "@/hooks/use-memory";

vi.mock("@/hooks/use-memory", () => ({
  useMemory: vi.fn(),
  useNextTermSuggestions: vi.fn(),
  useDecideMemory: vi.fn(),
}));

const mockUseMemory = vi.mocked(useMemory);
const mockUseSuggestions = vi.mocked(useNextTermSuggestions);
const mockUseDecide = vi.mocked(useDecideMemory);

function makeItem(overrides: Partial<MemoryItemResponse> = {}): MemoryItemResponse {
  return {
    id: "m1",
    course_id: "c1",
    learning_note_id: null,
    kind: "outcome",
    relationship_summary: null,
    action_summary: null,
    outcome_summary: { summary: "Tone drilling improved sustained accuracy" },
    instructor_comment: null,
    carry_forward: false,
    decision: null,
    decided_by: null,
    decided_at: null,
    report_history: [],
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

let decideMutate: ReturnType<typeof vi.fn>;

function renderView() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <CourseMemoryView courseId="c1" />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  decideMutate = vi.fn();
  mockUseSuggestions.mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useNextTermSuggestions>);
  mockUseDecide.mockReturnValue({
    mutate: decideMutate,
    isPending: false,
    isError: false,
  } as unknown as ReturnType<typeof useDecideMemory>);
});

describe("CourseMemoryView", () => {
  it("renders the designed empty state for a course with no memory", () => {
    mockUseMemory.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useMemory>);

    renderView();

    expect(screen.getByText("No course memory yet")).toBeTruthy();
  });

  it("groups items by kind and shows the selected item's summary", () => {
    mockUseMemory.mockReturnValue({
      data: [makeItem()],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useMemory>);

    renderView();

    // Kind group header + the reshaped summary text in the detail panel.
    expect(screen.getByText("Outcomes")).toBeTruthy();
    expect(
      screen.getAllByText(/Tone drilling improved sustained accuracy/i).length
    ).toBeGreaterThan(0);
  });

  it("records an audited decision through a confirm dialog", async () => {
    mockUseMemory.mockReturnValue({
      data: [makeItem()],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useMemory>);

    renderView();

    // The decide control button (exact label — the row badge reads "Not decided").
    fireEvent.click(screen.getByRole("button", { name: "Keep" }));

    // Confirm dialog appears and calls the decide mutation with the choice.
    const confirm = await screen.findByRole("button", { name: "Confirm" });
    fireEvent.click(confirm);

    await waitFor(() => expect(decideMutate).toHaveBeenCalledTimes(1));
    expect(decideMutate.mock.calls[0][0]).toEqual({
      itemId: "m1",
      decision: "keep",
    });
  });
});
