import { describe, expect, it } from "vitest";

import type { ReportResponse } from "@/hooks/use-reports";
import {
  canSendReport,
  formatMasteryPercent,
  formatPeriodRange,
  isReportEditable,
  sendGateState,
} from "./report-format";

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
    evidence_refs: [],
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

describe("formatPeriodRange", () => {
  it("collapses a same-month range onto one month/year", () => {
    expect(
      formatPeriodRange("2026-06-16T00:00:00Z", "2026-06-22T00:00:00Z")
    ).toBe("16 – 22 Jun 2026");
  });

  it("keeps both months when the range spans a month boundary", () => {
    expect(
      formatPeriodRange("2026-05-28T00:00:00Z", "2026-06-01T00:00:00Z")
    ).toBe("28 May – 1 Jun 2026");
  });

  it("falls back to raw input on an unparseable date", () => {
    expect(formatPeriodRange("not-a-date", "also-bad")).toBe(
      "not-a-date – also-bad"
    );
  });
});

describe("formatMasteryPercent", () => {
  it("renders a whole-percent string and clamps out-of-range scores", () => {
    expect(formatMasteryPercent(0.42)).toBe("42%");
    expect(formatMasteryPercent(1.5)).toBe("100%");
    expect(formatMasteryPercent(-0.2)).toBe("0%");
  });
});

describe("send/edit gate", () => {
  it("only allows send when reviewed AND evidence is present", () => {
    expect(canSendReport(makeReport({ status: "draft" }))).toBe(false);
    expect(
      canSendReport(makeReport({ status: "reviewed", evidence_refs: [] }))
    ).toBe(false);
    expect(
      canSendReport(
        makeReport({ status: "reviewed", evidence_refs: ["e1"] })
      )
    ).toBe(true);
  });

  it("reports which gate requirements are still missing", () => {
    const gate = sendGateState(
      makeReport({ status: "draft", evidence_refs: [] })
    );
    expect(gate.reviewed).toBe(false);
    expect(gate.hasEvidence).toBe(false);
    expect(gate.met).toBe(false);
  });

  it("treats only a draft as editable", () => {
    expect(isReportEditable("draft")).toBe(true);
    expect(isReportEditable("reviewed")).toBe(false);
    expect(isReportEditable("sent")).toBe(false);
  });
});
