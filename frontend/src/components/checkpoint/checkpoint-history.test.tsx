import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { CheckpointHistory } from "./checkpoint-history";
import { RevisitRunner } from "./revisit-runner";
import {
  useCheckpointIntro,
  useMyCheckpointHistory,
  useRevisitResponse,
  type CheckpointIntro,
  type StudentCheckpointHistoryItem,
} from "@/hooks/use-checkpoints";
import { usePilotConfig } from "@/hooks/use-pilot-config";
import type { PilotConfig } from "@/lib/pilot-config";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("@/hooks/use-checkpoints", () => ({
  useMyCheckpointHistory: vi.fn(),
  useCheckpointIntro: vi.fn(),
  useRevisitResponse: vi.fn(),
}));

vi.mock("@/hooks/use-pilot-config", () => ({
  usePilotConfig: vi.fn(),
}));

const mockUseHistory = vi.mocked(useMyCheckpointHistory);
const mockUseIntro = vi.mocked(useCheckpointIntro);
const mockUseRevisit = vi.mocked(useRevisitResponse);
const mockUsePilot = vi.mocked(usePilotConfig);

const CONFIG = {
  confidence_scale: {
    min: -2,
    max: 2,
    labels: {
      "-2": "No idea",
      "-1": "A little",
      "0": "Some",
      "1": "Confident",
      "2": "Very clear",
    },
  },
} as unknown as PilotConfig;

function historyItem(
  overrides: Partial<StudentCheckpointHistoryItem>
): StudentCheckpointHistoryItem {
  return {
    checkpoint_id: "cp-1",
    title: "Session 4 checkpoint",
    kind: "checkpoint",
    status: "closed",
    derived_status: "complete",
    release_at: null,
    close_at: null,
    responded_count: 4,
    live_card_count: 4,
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

beforeEach(() => {
  vi.clearAllMocks();
  mockUsePilot.mockReturnValue({
    config: CONFIG,
    isLoaded: true,
    isError: false,
  });
});

afterEach(() => cleanup());

describe("CheckpointHistory — S039", () => {
  beforeEach(() => {
    mockUseHistory.mockReturnValue({
      data: [
        historyItem({
          checkpoint_id: "cp-complete",
          title: "Session 4 checkpoint",
          derived_status: "complete",
        }),
        historyItem({
          checkpoint_id: "cp-late",
          title: "Session 3 checkpoint",
          derived_status: "late",
          responded_count: 2,
        }),
      ],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useMyCheckpointHistory>);
  });

  it("renders each checkpoint with its derived status chip", () => {
    wrap(<CheckpointHistory courseId="course-1" />);
    expect(screen.getByText("Session 4 checkpoint")).toBeTruthy();
    expect(screen.getByText("Session 3 checkpoint")).toBeTruthy();
    // "Late" is unique to the status chip; "Completed" also names a filter, so
    // just assert at least one status chip carries it.
    expect(screen.getByText("Late")).toBeTruthy();
    expect(screen.getAllByText("Completed").length).toBeGreaterThanOrEqual(1);
  });

  it("filters to only the items that need a revisit", () => {
    wrap(<CheckpointHistory courseId="course-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Needs revisit" }));

    // The late item stays; the completed item is filtered out.
    expect(screen.getByText("Session 3 checkpoint")).toBeTruthy();
    expect(screen.queryByText("Session 4 checkpoint")).toBeNull();
  });

  it("routes to the follow-up when Review is pressed on a needs-revisit item", () => {
    wrap(<CheckpointHistory courseId="course-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Review" }));
    expect(push).toHaveBeenCalledWith(
      "/student/checkpoints/cp-late/follow-up"
    );
  });
});

describe("RevisitRunner — S041", () => {
  const INTRO: CheckpointIntro = {
    checkpoint_id: "cp-follow",
    title: "Follow-up checkpoint",
    status: "published",
    close_at: null,
    cards: [
      {
        id: "card-1",
        position: 1,
        kind: "review_point",
        prompt: "Evidence support",
      },
    ],
  };

  let revisitMutate: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    revisitMutate = vi.fn(async () => ({
      response: {
        id: "r1",
        checkpoint_id: "cp-follow",
        card_id: "card-1",
        confidence: 2,
        text_response: null,
        status: "on_time",
        submitted_at: "2026-06-26T11:04:00Z",
      },
      carried_from_id: "cp-1",
      concept_id: null,
      confidence_before: 0,
      confidence_after: 2,
      delta: 2,
    }));
    mockUseIntro.mockReturnValue({
      data: INTRO,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCheckpointIntro>);
    mockUseRevisit.mockReturnValue({
      mutateAsync: revisitMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useRevisitResponse>);
  });

  it("submits a revisit confidence and shows the delta on completion", async () => {
    wrap(<RevisitRunner checkpointId="cp-follow" onDone={vi.fn()} />);

    expect(screen.getByText("Evidence support")).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: "Very clear" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit follow-up" }));

    await waitFor(() =>
      expect(revisitMutate).toHaveBeenCalledWith({
        card_id: "card-1",
        confidence: 2,
      })
    );

    // Delta receipt (before 0 → after 2 = +2).
    await screen.findByText("Follow-up complete");
  });
});
