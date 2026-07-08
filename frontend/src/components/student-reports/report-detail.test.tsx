import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { ReportDetail } from "./report-detail";
import {
  useMyReport,
  type ReportBody,
  type ReportResponse,
} from "@/hooks/use-reports";
import { usePilotConfig } from "@/hooks/use-pilot-config";

vi.mock("@/hooks/use-reports", () => ({
  useMyReport: vi.fn(),
}));
vi.mock("@/hooks/use-pilot-config", () => ({
  usePilotConfig: vi.fn(),
}));

const mockUseMyReport = vi.mocked(useMyReport);
const mockUsePilot = vi.mocked(usePilotConfig);

const PILOT_DISCLAIMER = "PILOT FALLBACK: reviewed course evidence only.";
const SNAPSHOT_DISCLAIMER =
  "This report summarizes reviewed course evidence. It describes observed participation and learning patterns only.";

function wrap(node: ReactElement) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages} timeZone="UTC">
      {node}
    </NextIntlClientProvider>
  );
}

function body(over: Partial<ReportBody> = {}): ReportBody {
  return {
    summary: "You showed steady progress this week.",
    observations: ["Clearer topic sentences", "More varied vocabulary"],
    completed_work: { completed_count: 4 },
    weak_points: [
      { concept_id: "c-1", name: "Past tense agreement", mastery_score: 0.42 },
    ],
    next_actions: ["Review the Session 5 checkpoint"],
    claim_limits: SNAPSHOT_DISCLAIMER,
    ...over,
  };
}

function sentReport(over: Partial<ReportResponse> = {}): ReportResponse {
  return {
    id: "r-1",
    course_id: "course-1",
    audience: "student",
    user_id: "u-1",
    period: "weekly",
    period_start: "2026-06-12T00:00:00Z",
    period_end: "2026-06-19T00:00:00Z",
    body: body(),
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

function pilot(reportLimit: string | undefined) {
  mockUsePilot.mockReturnValue({
    config: {
      claim_limits: reportLimit ? { report: reportLimit } : {},
    },
    isLoaded: true,
    isError: false,
  } as unknown as ReturnType<typeof usePilotConfig>);
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => cleanup());

describe("ReportDetail — S067/S068 + verbatim claim limits", () => {
  it("renders the report's own claim_limits snapshot VERBATIM", () => {
    mockUseMyReport.mockReturnValue({
      data: sentReport(),
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useMyReport>);
    pilot(PILOT_DISCLAIMER);

    wrap(<ReportDetail courseId="course-1" reportId="r-1" />);

    // The snapshot is preferred over the pilot fallback and shown word-for-word.
    expect(screen.getByText(SNAPSHOT_DISCLAIMER)).toBeTruthy();
    expect(screen.queryByText(PILOT_DISCLAIMER)).toBeNull();
    // Body sections render.
    expect(screen.getByText("What we noticed")).toBeTruthy();
    expect(screen.getByText("Past tense agreement")).toBeTruthy();
    // Delivery state (S069) shows the sent confirmation, never draft content.
    expect(screen.getByText("Report sent")).toBeTruthy();
  });

  it("falls back to the pilot claim_limits.report VERBATIM when the snapshot is empty", () => {
    mockUseMyReport.mockReturnValue({
      data: sentReport({ body: body({ claim_limits: "" }) }),
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useMyReport>);
    pilot(PILOT_DISCLAIMER);

    wrap(<ReportDetail courseId="course-1" reportId="r-1" />);

    expect(screen.getByText(PILOT_DISCLAIMER)).toBeTruthy();
  });
});
