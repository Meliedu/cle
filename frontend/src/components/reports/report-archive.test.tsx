import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { ReportArchive } from "./report-archive";
import { useReports, type ReportResponse } from "@/hooks/use-reports";

vi.mock("@/hooks/use-reports", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/use-reports")>();
  return { ...actual, useReports: vi.fn() };
});

const mockUseReports = vi.mocked(useReports);

function makeReport(overrides: Partial<ReportResponse> = {}): ReportResponse {
  return {
    id: "r1",
    course_id: "c1",
    audience: "teacher",
    user_id: null,
    period: "weekly",
    period_start: "2026-06-16T00:00:00Z",
    period_end: "2026-06-22T00:00:00Z",
    body: null,
    evidence_refs: ["e1"],
    status: "draft",
    reviewed_by: null,
    reviewed_at: null,
    sent_at: null,
    export_history: [],
    created_at: "2026-06-22T00:00:00Z",
    updated_at: "2026-06-22T00:00:00Z",
    ...overrides,
  };
}

function renderArchive() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ReportArchive courseId="c1" onSelect={() => {}} />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

describe("ReportArchive", () => {
  it("groups reports by status with one chip treatment each", () => {
    mockUseReports.mockReturnValue({
      data: [
        makeReport({ id: "r1", status: "draft" }),
        makeReport({ id: "r2", status: "reviewed" }),
        makeReport({ id: "r3", status: "sent" }),
      ],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useReports>);

    const { container } = renderArchive();

    // one status chip per distinct status, carrying its data-status marker
    expect(container.querySelector('[data-status="draft"]')).toBeTruthy();
    expect(container.querySelector('[data-status="reviewed"]')).toBeTruthy();
    expect(container.querySelector('[data-status="sent"]')).toBeTruthy();
    expect(container.querySelector('[data-status="archived"]')).toBeFalsy();

    // localized group labels rendered
    expect(screen.getByText("Draft")).toBeTruthy();
    expect(screen.getByText("Reviewed")).toBeTruthy();
    expect(screen.getByText("Sent")).toBeTruthy();
  });

  it("shows the designed empty state when there are no reports", () => {
    mockUseReports.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useReports>);

    renderArchive();

    expect(screen.getByText("No reports yet")).toBeTruthy();
  });

  it("surfaces a load error as a warning banner", () => {
    mockUseReports.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as unknown as ReturnType<typeof useReports>);

    const { container } = renderArchive();

    expect(
      container.querySelector('[data-tone="warning"]')
    ).toBeTruthy();
  });
});
