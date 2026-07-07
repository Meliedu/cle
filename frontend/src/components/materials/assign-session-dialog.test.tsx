import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { AssignSessionDialog } from "./assign-session-dialog";
import { ApiError } from "@/lib/api";
import { useMeetings, type Meeting } from "@/hooks/use-meetings";
import { useAssignMaterial, type DocumentResponse } from "@/hooks/use-documents";

vi.mock("@/hooks/use-meetings", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/use-meetings")>();
  return { ...actual, useMeetings: vi.fn() };
});
vi.mock("@/hooks/use-documents", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/use-documents")>();
  return { ...actual, useAssignMaterial: vi.fn() };
});

const mockUseMeetings = vi.mocked(useMeetings);
const mockUseAssignMaterial = vi.mocked(useAssignMaterial);

function makeMeeting(overrides: Partial<Meeting> = {}): Meeting {
  return {
    id: "m1",
    course_id: "c1",
    module_id: null,
    meeting_index: 1,
    title: "Intro",
    scheduled_at: "2026-01-15T10:30:00Z",
    duration_minutes: 90,
    location: null,
    status: "planned",
    release_state: "released",
    topic_summary: null,
    canvas_event_id: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

const doc: DocumentResponse = {
  id: "d1",
  course_id: "c1",
  uploaded_by: "u1",
  filename: "reading.pdf",
  file_type: "application/pdf",
  file_size: 2048,
  status: "ready",
  page_count: 3,
  word_count: 900,
  meeting_id: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function setAssign(mutateAsync: ReturnType<typeof vi.fn>) {
  mockUseAssignMaterial.mockReturnValue({
    mutateAsync,
    isPending: false,
  } as unknown as ReturnType<typeof useAssignMaterial>);
}

function renderDialog() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <AssignSessionDialog
        open
        onOpenChange={() => {}}
        courseId="c1"
        doc={doc}
      />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  mockUseMeetings.mockReturnValue({
    data: [makeMeeting({ id: "m1", meeting_index: 1, title: "Intro" })],
    isLoading: false,
  } as unknown as ReturnType<typeof useMeetings>);
});

describe("AssignSessionDialog", () => {
  it("PATCHes the chosen session's meeting_id on save", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({ ...doc, meeting_id: "m1" });
    setAssign(mutateAsync);

    renderDialog();

    fireEvent.click(screen.getByRole("radio", { name: "1. Intro" }));
    fireEvent.click(screen.getByRole("button", { name: "Save assignment" }));

    expect(mutateAsync).toHaveBeenCalledWith({
      documentId: "d1",
      meeting_id: "m1",
    });
  });

  it("surfaces MEETING_NOT_FOUND as a warning banner", async () => {
    const mutateAsync = vi
      .fn()
      .mockRejectedValue(
        new ApiError(404, "not found", "detail", "MEETING_NOT_FOUND")
      );
    setAssign(mutateAsync);

    renderDialog();

    fireEvent.click(screen.getByRole("radio", { name: "1. Intro" }));
    fireEvent.click(screen.getByRole("button", { name: "Save assignment" }));

    expect(
      await screen.findByText("That session no longer exists. Refresh and pick another.")
    ).toBeTruthy();
  });
});
