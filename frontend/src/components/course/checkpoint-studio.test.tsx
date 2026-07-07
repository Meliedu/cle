import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { CheckpointStudio } from "./checkpoint-studio";
import {
  useCheckpoint,
  useCheckpoints,
  useCheckpointHistory,
  useUpdateCheckpointCard,
  type CheckpointCard,
  type CheckpointWithCards,
} from "@/hooks/use-checkpoints";

vi.mock("@/hooks/use-checkpoints", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/hooks/use-checkpoints")>();
  return {
    ...actual,
    useCheckpoint: vi.fn(),
    useCheckpoints: vi.fn(),
    useCheckpointHistory: vi.fn(),
    useUpdateCheckpointCard: vi.fn(),
  };
});

const mockUseCheckpoint = vi.mocked(useCheckpoint);
const mockUseCheckpoints = vi.mocked(useCheckpoints);
const mockUseCheckpointHistory = vi.mocked(useCheckpointHistory);
const mockUseUpdateCard = vi.mocked(useUpdateCheckpointCard);

function makeCard(overrides: Partial<CheckpointCard> = {}): CheckpointCard {
  return {
    id: "card1",
    checkpoint_id: "cp1",
    position: 0,
    kind: "review_point",
    prompt: "Explain the difference between skimming and scanning.",
    document_id: null,
    chunk_id: null,
    objective_id: null,
    removed: false,
    removed_reason: null,
    removed_note: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeCheckpoint(
  overrides: Partial<CheckpointWithCards> = {}
): CheckpointWithCards {
  return {
    id: "cp1",
    course_id: "c1",
    meeting_id: "m1",
    kind: "session",
    status: "draft",
    title: "Session 1 checkpoint",
    qr_enabled: true,
    release_at: null,
    close_at: null,
    close_rule: null,
    carried_from_id: null,
    generation_meta: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    cards: [makeCard()],
    ...overrides,
  };
}

function setCheckpoint(
  data: CheckpointWithCards | undefined,
  isLoading = false
) {
  mockUseCheckpoint.mockReturnValue({
    data,
    isLoading,
  } as unknown as ReturnType<typeof useCheckpoint>);
  mockUseCheckpoints.mockReturnValue({
    data: [],
  } as unknown as ReturnType<typeof useCheckpoints>);
  mockUseCheckpointHistory.mockReturnValue({
    data: [],
  } as unknown as ReturnType<typeof useCheckpointHistory>);
}

function renderStudio() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <CheckpointStudio courseId="c1" meetingId="m1" checkpointId="cp1" />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  mockUseUpdateCard.mockReturnValue({
    mutateAsync: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useUpdateCheckpointCard>);
});

describe("CheckpointStudio", () => {
  it("renders the checkpoint title, its status chip, and a row per card", () => {
    setCheckpoint(
      makeCheckpoint({
        status: "draft",
        cards: [
          makeCard({ id: "card1", prompt: "First review point" }),
          makeCard({
            id: "final",
            kind: "final_comments",
            prompt: "Any final comments?",
          }),
        ],
      })
    );

    renderStudio();

    expect(screen.getByText("Session 1 checkpoint")).toBeTruthy();
    // one visual treatment per status → the localized "Draft" chip
    expect(screen.getByText("Draft")).toBeTruthy();
    expect(screen.getByText("First review point")).toBeTruthy();
    expect(screen.getByText("Any final comments?")).toBeTruthy();
    // the fixed final card exposes no remove affordance
    expect(screen.getByText("Fixed card")).toBeTruthy();
  });

  it("surfaces the carry-over banner for a follow-up checkpoint", () => {
    setCheckpoint(
      makeCheckpoint({ carried_from_id: "cp0", kind: "follow_up" })
    );

    renderStudio();

    expect(screen.getByText("This is a follow-up checkpoint")).toBeTruthy();
    expect(screen.getByText("Review carry-over")).toBeTruthy();
  });

  it("renders a designed empty state when the checkpoint has no cards", () => {
    setCheckpoint(makeCheckpoint({ cards: [] }));

    renderStudio();

    expect(screen.getByText("No cards yet")).toBeTruthy();
  });

  it("shows a skeleton while the checkpoint loads", () => {
    setCheckpoint(undefined, true);

    const { container } = renderStudio();
    expect(container.querySelector('[data-slot="skeleton"]')).toBeTruthy();
  });
});
