import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { StepCheckpoints } from "./step-checkpoints";
import {
  useCheckpoint,
  useCheckpoints,
  useUpdateCheckpointCard,
  type Checkpoint,
  type CheckpointCard,
  type CheckpointWithCards,
} from "@/hooks/use-checkpoints";
import { useGenerateCheckpoints, useSetStep } from "@/hooks/use-setup";

vi.mock("@/hooks/use-checkpoints", () => ({
  useCheckpoints: vi.fn(),
  useCheckpoint: vi.fn(),
  useUpdateCheckpointCard: vi.fn(),
}));

vi.mock("@/hooks/use-setup", () => ({
  useGenerateCheckpoints: vi.fn(),
  useSetStep: vi.fn(),
  setupErrorCode: () => null,
}));

const mockUseCheckpoints = vi.mocked(useCheckpoints);
const mockUseCheckpoint = vi.mocked(useCheckpoint);
const mockUseUpdateCard = vi.mocked(useUpdateCheckpointCard);
const mockUseGenerate = vi.mocked(useGenerateCheckpoints);
const mockUseSetStep = vi.mocked(useSetStep);

function makeCheckpoint(overrides: Partial<Checkpoint> = {}): Checkpoint {
  return {
    id: "cp1",
    course_id: "c1",
    meeting_id: "m1",
    kind: "session",
    status: "draft",
    title: "Session 1 · Introductions",
    qr_enabled: false,
    generation_meta: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeCard(overrides: Partial<CheckpointCard> = {}): CheckpointCard {
  return {
    id: "card1",
    checkpoint_id: "cp1",
    position: 0,
    kind: "review_point",
    prompt: "I can identify the main idea of the meeting.",
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

function renderStep(onComplete = vi.fn()) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <StepCheckpoints courseId="c1" onComplete={onComplete} />
    </NextIntlClientProvider>
  );
}

let generateMutate: ReturnType<typeof vi.fn>;
let setStepMutate: ReturnType<typeof vi.fn>;

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  generateMutate = vi.fn(async () => undefined);
  setStepMutate = vi.fn(async () => ({}));
  mockUseCheckpoints.mockReturnValue({
    data: [],
    isLoading: false,
  } as unknown as ReturnType<typeof useCheckpoints>);
  mockUseCheckpoint.mockReturnValue({
    data: undefined,
    isLoading: false,
  } as unknown as ReturnType<typeof useCheckpoint>);
  mockUseUpdateCard.mockReturnValue({
    mutateAsync: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useUpdateCheckpointCard>);
  mockUseGenerate.mockReturnValue({
    mutateAsync: generateMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useGenerateCheckpoints>);
  mockUseSetStep.mockReturnValue({
    mutateAsync: setStepMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useSetStep>);
});

describe("StepCheckpoints", () => {
  it("shows the empty state and a generate button when there are no drafts", () => {
    renderStep();
    expect(screen.getByText(/No checkpoints yet/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Generate checkpoints/i })).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: /Approve checkpoint drafts/i }) as HTMLButtonElement)
        .disabled
    ).toBe(true);
  });

  it("enqueues the generation job when Generate checkpoints is pressed", async () => {
    renderStep();
    fireEvent.click(screen.getByRole("button", { name: /Generate checkpoints/i }));
    await waitFor(() => expect(generateMutate).toHaveBeenCalledTimes(1));
  });

  it("lists draft checkpoints with a Draft badge", () => {
    mockUseCheckpoints.mockReturnValue({
      data: [makeCheckpoint()],
      isLoading: false,
    } as unknown as ReturnType<typeof useCheckpoints>);
    renderStep();
    expect(screen.getByText(/Session 1 · Introductions/)).toBeTruthy();
    expect(screen.getByText(/^Draft$/)).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: /Approve checkpoint drafts/i }) as HTMLButtonElement)
        .disabled
    ).toBe(false);
  });

  it("expands a checkpoint and fixes the final-comments card (no remove button)", () => {
    mockUseCheckpoints.mockReturnValue({
      data: [makeCheckpoint()],
      isLoading: false,
    } as unknown as ReturnType<typeof useCheckpoints>);
    const withCards: CheckpointWithCards = {
      ...makeCheckpoint(),
      cards: [
        makeCard(),
        makeCard({ id: "final", kind: "final_comments", position: 1, prompt: "Questions or comments?" }),
      ],
    };
    mockUseCheckpoint.mockReturnValue({
      data: withCards,
      isLoading: false,
    } as unknown as ReturnType<typeof useCheckpoint>);

    renderStep();
    fireEvent.click(screen.getByRole("button", { name: /Session 1 · Introductions/ }));
    expect(screen.getByText(/I can identify the main idea/)).toBeTruthy();
    // Exactly one review-point card is removable; the final card shows "Fixed card".
    expect(screen.getAllByRole("button", { name: /^Remove$/i })).toHaveLength(1);
    expect(screen.getByText(/Fixed card/i)).toBeTruthy();
  });

  it("flips the checkpoints flag on continue when drafts exist", async () => {
    mockUseCheckpoints.mockReturnValue({
      data: [makeCheckpoint()],
      isLoading: false,
    } as unknown as ReturnType<typeof useCheckpoints>);
    const onComplete = vi.fn();
    renderStep(onComplete);
    fireEvent.click(screen.getByRole("button", { name: /Approve checkpoint drafts/i }));
    await waitFor(() =>
      expect(setStepMutate).toHaveBeenCalledWith({ step: "checkpoints", done: true })
    );
    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
  });
});
