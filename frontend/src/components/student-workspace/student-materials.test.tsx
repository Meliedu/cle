import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { StudentMaterials } from "./student-materials";
import {
  useMaterials,
  useMaterialPreview,
  type DocumentResponse,
  type MaterialsLibrary,
} from "@/hooks/use-documents";

vi.mock("@/hooks/use-documents", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/hooks/use-documents")>();
  return { ...actual, useMaterials: vi.fn(), useMaterialPreview: vi.fn() };
});

const mockUseMaterials = vi.mocked(useMaterials);
const mockUseMaterialPreview = vi.mocked(useMaterialPreview);

function makeDoc(overrides: Partial<DocumentResponse> = {}): DocumentResponse {
  return {
    id: "d1",
    course_id: "c1",
    uploaded_by: "t1",
    filename: "Week 1 reading.pdf",
    file_type: "application/pdf",
    file_size: 1024,
    status: "ready",
    page_count: 5,
    word_count: 900,
    meeting_id: "m1",
    created_at: "2026-07-01T00:00:00Z",
    updated_at: "2026-07-01T00:00:00Z",
    ...overrides,
  };
}

function setMaterials(
  data: MaterialsLibrary | undefined,
  extra: Partial<ReturnType<typeof useMaterials>> = {}
) {
  mockUseMaterials.mockReturnValue({
    data,
    isLoading: false,
    isError: false,
    ...extra,
  } as unknown as ReturnType<typeof useMaterials>);
}

beforeEach(() => {
  vi.clearAllMocks();
  // Reader stays closed in these tests; preview never enabled.
  mockUseMaterialPreview.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useMaterialPreview>);
});
afterEach(cleanup);

function renderMaterials() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <StudentMaterials courseId="c1" />
    </NextIntlClientProvider>
  );
}

describe("StudentMaterials", () => {
  it("renders session folders with their documents", () => {
    setMaterials({
      sessions: [
        {
          meeting_id: "m1",
          meeting_index: 1,
          title: "Session 1",
          release_state: "released",
          documents: [
            makeDoc({ id: "d1", filename: "Week 1 reading.pdf" }),
            makeDoc({ id: "d2", filename: "Citing sources.pdf" }),
          ],
        },
      ],
      unassigned: [],
    });

    const { container } = renderMaterials();

    expect(screen.getByText("Session 1")).toBeTruthy();
    expect(screen.getByText("Week 1 reading.pdf")).toBeTruthy();
    expect(screen.getByText("Citing sources.pdf")).toBeTruthy();
    // release chip renders with the "success" tone for a released folder
    expect(container.querySelector('[data-tone="success"]')).toBeTruthy();
  });

  it("renders the designed no-materials state when the library is empty", () => {
    setMaterials({ sessions: [], unassigned: [] });
    renderMaterials();
    expect(screen.getByText("No materials published yet")).toBeTruthy();
  });

  it("renders an error banner when materials fail to load", () => {
    setMaterials(undefined, { isError: true });
    renderMaterials();
    expect(screen.getByText("We couldn't load your materials")).toBeTruthy();
  });
});
