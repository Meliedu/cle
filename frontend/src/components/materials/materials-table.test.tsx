import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it } from "vitest";

import messages from "../../../messages/en.json";
import { MaterialsTable } from "./materials-table";
import type {
  DocumentResponse,
  MaterialsLibrary,
} from "@/hooks/use-documents";
import { ALL_FOLDER, UNASSIGNED_FOLDER } from "./materials-folder-nav";

function makeDoc(overrides: Partial<DocumentResponse> = {}): DocumentResponse {
  return {
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
    ...overrides,
  };
}

const library: MaterialsLibrary = {
  sessions: [
    {
      meeting_id: "m1",
      meeting_index: 1,
      title: "Reading strategies",
      release_state: "released",
      documents: [
        makeDoc({ id: "d1", filename: "week1.pdf", meeting_id: "m1" }),
        makeDoc({
          id: "d2",
          filename: "vocab.docx",
          file_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          meeting_id: "m1",
        }),
      ],
    },
  ],
  unassigned: [
    makeDoc({ id: "d3", filename: "loose-notes.pptx", meeting_id: null }),
  ],
};

function renderTable(folder: string) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <MaterialsTable library={library} folder={folder} />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);

describe("MaterialsTable", () => {
  it("lists every material with its session folder in the all-materials view", () => {
    renderTable(ALL_FOLDER);

    expect(screen.getByText("week1.pdf")).toBeTruthy();
    expect(screen.getByText("vocab.docx")).toBeTruthy();
    expect(screen.getByText("loose-notes.pptx")).toBeTruthy();
    // session-derived label + unassigned bucket both render
    expect(screen.getAllByText("Session 1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Unassigned").length).toBeGreaterThan(0);
  });

  it("filters to the unassigned bucket", () => {
    renderTable(UNASSIGNED_FOLDER);

    expect(screen.getByText("loose-notes.pptx")).toBeTruthy();
    expect(screen.queryByText("week1.pdf")).toBeNull();
  });

  it("filters to a single session folder by meeting id", () => {
    renderTable("m1");

    expect(screen.getByText("week1.pdf")).toBeTruthy();
    expect(screen.getByText("vocab.docx")).toBeTruthy();
    expect(screen.queryByText("loose-notes.pptx")).toBeNull();
  });

  it("shows the empty-folder message when a folder has no files", () => {
    render(
      <NextIntlClientProvider locale="en" messages={messages}>
        <MaterialsTable
          library={{ sessions: [], unassigned: [] }}
          folder={ALL_FOLDER}
        />
      </NextIntlClientProvider>
    );

    expect(screen.getByText("No files in this folder yet.")).toBeTruthy();
  });
});
