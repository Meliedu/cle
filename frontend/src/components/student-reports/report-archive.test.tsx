import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { ReportArchive } from "./report-archive";
import { useMyReports, type ReportResponse } from "@/hooks/use-reports";

vi.mock("@/hooks/use-reports", () => ({
  useMyReports: vi.fn(),
}));

const mockUseMyReports = vi.mocked(useMyReports);

function wrap(node: ReactElement) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages} timeZone="UTC">
      {node}
    </NextIntlClientProvider>
  );
}

function sentWeekly(over: Partial<ReportResponse> = {}): ReportResponse {
  return {
    id: "r-1",
    course_id: "course-1",
    audience: "student",
    user_id: "u-1",
    period: "weekly",
    period_start: "2026-06-12T00:00:00Z",
    period_end: "2026-06-19T00:00:00Z",
    body: null,
    evidence_refs: ["n-1"],
    status: "sent",
    reviewed_by: "t-1",
    reviewed_at: "2026-06-19T09:00:00Z",
    sent_at: "2026-06-19T10:15:00Z",
    export_history: [],
    created_at: "2026-06-19T08:00:00Z",
    updated_at: "2026-06-19T10:15:00Z",
    ...over,
  };
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => cleanup());

describe("ReportArchive — S066 / S069 delivery-state modeling", () => {
  it("shows the designed not-yet-sent waiting shell when no report has been sent", () => {
    // Student read returns ONLY sent reports; an empty list == nothing delivered
    // yet. This is the S069 waiting state — never a draft, never a blank div.
    mockUseMyReports.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useMyReports>);

    wrap(<ReportArchive courseId="course-1" />);

    expect(screen.getByText("No reports yet")).toBeTruthy();
    expect(
      screen.getByText(/you never see an unsent draft/)
    ).toBeTruthy();
  });

  it("renders a sent report row linking to its detail with a delivery chip", () => {
    mockUseMyReports.mockReturnValue({
      data: [sentWeekly()],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useMyReports>);

    wrap(<ReportArchive courseId="course-1" />);

    expect(screen.getByText("Weekly report")).toBeTruthy();
    // Delivery chip reflects the SENT state (S069).
    expect(screen.getByText(/Sent 19 Jun 2026/)).toBeTruthy();
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toBe(
      "/student/courses/course-1/reports/r-1"
    );
  });

  it("surfaces a designed error banner when the read fails", () => {
    mockUseMyReports.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as unknown as ReturnType<typeof useMyReports>);

    wrap(<ReportArchive courseId="course-1" />);
    expect(screen.getByText("We couldn't load your reports")).toBeTruthy();
  });
});
