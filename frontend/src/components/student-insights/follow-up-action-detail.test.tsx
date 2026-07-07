import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { FollowUpActionDetail } from "./follow-up-action-detail";
import { SignalDetail } from "./signal-detail";
import {
  useFollowUpDetail,
  useMarkFollowUpViewed,
  type FollowUpDetail,
} from "@/hooks/use-follow-ups";
import {
  useSignal,
  useEvidenceSource,
  type SignalDetail as SignalDetailType,
} from "@/hooks/use-insights";

vi.mock("@/hooks/use-follow-ups", () => ({
  useFollowUpDetail: vi.fn(),
  useMarkFollowUpViewed: vi.fn(),
}));

vi.mock("@/hooks/use-insights", () => ({
  useSignal: vi.fn(),
  useEvidenceSource: vi.fn(),
}));

const mockUseDetail = vi.mocked(useFollowUpDetail);
const mockUseMarkViewed = vi.mocked(useMarkFollowUpViewed);
const mockUseSignal = vi.mocked(useSignal);
const mockUseEvidenceSource = vi.mocked(useEvidenceSource);

function detail(overrides: Partial<FollowUpDetail>): FollowUpDetail {
  return {
    id: "fu-1",
    course_id: "course-1",
    learning_note_id: "note-1",
    action_type: "practice",
    target_kind: "checkpoint",
    target_id: "cp-1",
    assignment_status: "assigned",
    due_at: null,
    created_at: "2026-07-01T10:00:00Z",
    waiting_for_review: false,
    observed_signal: "You paused on the past-tense forms.",
    draft_interpretation: "Worth another short practice set.",
    limitation_note: "Based on one session only.",
    outcome_status: "improved",
    revisit: null,
    ...overrides,
  };
}

function wrap(node: ReactElement) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages} timeZone="UTC">
      {node}
    </NextIntlClientProvider>
  );
}

const mutate = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  mockUseMarkViewed.mockReturnValue({
    mutate,
    isPending: false,
  } as unknown as ReturnType<typeof useMarkFollowUpViewed>);
  // SignalDetail dependency: a reviewed signal with no linked source event.
  mockUseSignal.mockReturnValue({
    data: {
      id: "note-1",
      waiting_for_review: false,
      source_event_ids: [],
      context_anchor: null,
    } as unknown as SignalDetailType,
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useSignal>);
  mockUseEvidenceSource.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useEvidenceSource>);
});

afterEach(() => cleanup());

describe("FollowUpActionDetail — S061", () => {
  it("shows the designed waiting state and NO reviewed content while under review", () => {
    mockUseDetail.mockReturnValue({
      data: detail({
        waiting_for_review: true,
        observed_signal: null,
        draft_interpretation: null,
        limitation_note: null,
        outcome_status: null,
      }),
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useFollowUpDetail>);

    wrap(<FollowUpActionDetail courseId="course-1" followUpId="fu-1" />);

    expect(screen.getByText("Your instructor is reviewing this")).toBeTruthy();
    // No AI draft content and no mark-viewed affordance while waiting.
    expect(screen.queryByText("What we noticed")).toBeNull();
    expect(screen.queryByRole("button", { name: "Mark as viewed" })).toBeNull();
  });

  it("renders the reviewed fields, outcome, and a working mark-viewed action", () => {
    mockUseDetail.mockReturnValue({
      data: detail({}),
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useFollowUpDetail>);

    wrap(<FollowUpActionDetail courseId="course-1" followUpId="fu-1" />);

    expect(screen.getByText("You paused on the past-tense forms.")).toBeTruthy();
    expect(screen.getByText("Worth another short practice set.")).toBeTruthy();
    expect(screen.getByText("Did it move?")).toBeTruthy();
    expect(screen.getByText("Improved")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Mark as viewed" }));
    expect(mutate).toHaveBeenCalledWith("fu-1");
  });

  it("shows a revisit CTA linking to the revisit path when a revisit exists", () => {
    mockUseDetail.mockReturnValue({
      data: detail({
        revisit: { checkpoint_id: "cp-1", revisit_path: "/student/checkpoints/cp-1/follow-up" },
      }),
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useFollowUpDetail>);

    wrap(<FollowUpActionDetail courseId="course-1" followUpId="fu-1" />);

    const cta = screen.getByRole("link", { name: "Start revisit" });
    expect(cta.getAttribute("href")).toBe("/student/checkpoints/cp-1/follow-up");
  });
});

describe("SignalDetail — S063 provenance", () => {
  it("collapses to the waiting state for an unreviewed signal", () => {
    mockUseSignal.mockReturnValue({
      data: {
        id: "note-2",
        waiting_for_review: true,
        source_event_ids: [],
      } as unknown as SignalDetailType,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useSignal>);

    wrap(<SignalDetail signalId="note-2" />);

    expect(
      screen.getByText("Your instructor is reviewing this signal")
    ).toBeTruthy();
    expect(screen.queryByText("Where did this come from")).toBeNull();
  });

  it("renders nothing when there is no signal id", () => {
    const { container } = wrap(<SignalDetail signalId={null} />);
    expect(container.textContent).toBe("");
  });
});
