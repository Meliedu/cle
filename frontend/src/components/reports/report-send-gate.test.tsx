import { cleanup, render } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it } from "vitest";

import messages from "../../../messages/en.json";
import { ReportSendGate } from "./report-send-gate";
import type { ReportResponse } from "@/hooks/use-reports";

function makeReport(overrides: Partial<ReportResponse> = {}): ReportResponse {
  return {
    id: "r1",
    course_id: "c1",
    audience: "student",
    user_id: "u1",
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

function renderGate(report: ReportResponse) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ReportSendGate report={report} />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);

describe("ReportSendGate", () => {
  it("blocks a draft with a blocked banner (not reviewed, no evidence)", () => {
    const { container, getByText } = renderGate(
      makeReport({ status: "draft", evidence_refs: [] })
    );

    const banner = container.querySelector('[data-tone="blocked"]');
    expect(banner).toBeTruthy();
    expect(banner?.getAttribute("role")).toBe("alert");
    // both checklist items unmet
    expect(
      container.querySelectorAll('[data-met="false"]').length
    ).toBe(2);
    expect(getByText("Not ready to send yet")).toBeTruthy();
  });

  it("blocks a reviewed report that has no evidence, flagging only evidence", () => {
    const { container } = renderGate(
      makeReport({ status: "reviewed", evidence_refs: [] })
    );

    expect(container.querySelector('[data-tone="blocked"]')).toBeTruthy();
    // reviewed is met, evidence is not
    expect(container.querySelectorAll('[data-met="true"]').length).toBe(1);
    expect(container.querySelectorAll('[data-met="false"]').length).toBe(1);
  });

  it("renders nothing once reviewed with evidence (gate satisfied)", () => {
    const { container } = renderGate(
      makeReport({ status: "reviewed", evidence_refs: ["e1"] })
    );

    expect(container.querySelector('[data-tone="blocked"]')).toBeFalsy();
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing for an already-sent report", () => {
    const { container } = renderGate(
      makeReport({ status: "sent", evidence_refs: ["e1"] })
    );

    expect(container.firstChild).toBeNull();
  });
});
