import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { CheckpointRunner } from "./checkpoint-runner";
import {
  useCheckpointIntro,
  useSubmitCheckpointResponse,
  type CheckpointIntro,
} from "@/hooks/use-checkpoints";
import { usePilotConfig } from "@/hooks/use-pilot-config";
import type { PilotConfig } from "@/lib/pilot-config";

vi.mock("@/hooks/use-checkpoints", () => ({
  useCheckpointIntro: vi.fn(),
  useSubmitCheckpointResponse: vi.fn(),
}));

vi.mock("@/hooks/use-pilot-config", () => ({
  usePilotConfig: vi.fn(),
}));

const mockUseIntro = vi.mocked(useCheckpointIntro);
const mockUseSubmit = vi.mocked(useSubmitCheckpointResponse);
const mockUsePilot = vi.mocked(usePilotConfig);

const SCALE = {
  min: -2,
  max: 2,
  labels: {
    "-2": "No idea",
    "-1": "A little",
    "0": "Some",
    "1": "Confident",
    "2": "Very clear",
  },
};

const CONFIG = {
  confidence_scale: SCALE,
} as unknown as PilotConfig;

// Two review cards, no final card → the flow never reaches the (formatter-heavy)
// completion screen, keeping the test focused on the confidence submission.
const INTRO: CheckpointIntro = {
  checkpoint_id: "cp-1",
  title: "Session 4 checkpoint",
  status: "published",
  close_at: null,
  cards: [
    { id: "card-1", position: 1, kind: "review_point", prompt: "Thesis clarity" },
    { id: "card-2", position: 2, kind: "review_point", prompt: "Evidence support" },
  ],
};

let submitMutate: ReturnType<typeof vi.fn>;

function stubSubmit(isPending = false) {
  submitMutate = vi.fn(async () => ({
    id: "resp-1",
    checkpoint_id: "cp-1",
    card_id: "card-1",
    confidence: 1,
    text_response: null,
    status: "on_time",
    submitted_at: "2026-06-26T11:04:00Z",
  }));
  mockUseSubmit.mockReturnValue({
    mutateAsync: submitMutate,
    isPending,
  } as unknown as ReturnType<typeof useSubmitCheckpointResponse>);
}

function renderRunner() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages} timeZone="UTC">
      <CheckpointRunner
        checkpointId="cp-1"
        onExit={vi.fn()}
        onViewHistory={vi.fn()}
      />
    </NextIntlClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  stubSubmit();
  mockUsePilot.mockReturnValue({
    config: CONFIG,
    isLoaded: true,
    isError: false,
  });
  mockUseIntro.mockReturnValue({
    data: INTRO,
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useCheckpointIntro>);
});

afterEach(() => {
  cleanup();
});

describe("CheckpointRunner — intro (S034)", () => {
  it("renders the checkpoint title and the included review points", () => {
    renderRunner();
    expect(screen.getByText("Session 4 checkpoint")).toBeTruthy();
    expect(screen.getByText("This checkpoint includes")).toBeTruthy();
    expect(screen.getByText("Thesis clarity")).toBeTruthy();
    expect(screen.getByText("Evidence support")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Start checkpoint" })
    ).toBeTruthy();
  });
});

describe("CheckpointRunner — confidence flow (S035)", () => {
  it("submits a confidence response on Next and advances to the next card", async () => {
    renderRunner();

    fireEvent.click(screen.getByRole("button", { name: "Start checkpoint" }));

    // First confidence card — the config-driven −2..+2 scale is rendered.
    await screen.findByText("Card 1 of 2");
    expect(screen.getByRole("radio", { name: "No idea" })).toBeTruthy();
    expect(screen.getByRole("radio", { name: "Very clear" })).toBeTruthy();

    // The CTA is disabled until a confidence point is chosen.
    const next = screen.getByRole("button", { name: "Next card" });
    expect((next as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(screen.getByRole("radio", { name: "Confident" }));
    fireEvent.click(screen.getByRole("button", { name: "Next card" }));

    await waitFor(() =>
      expect(submitMutate).toHaveBeenCalledWith({
        card_id: "card-1",
        confidence: 1,
      })
    );

    // Advanced to the second card.
    await screen.findByText("Card 2 of 2");
  });
});
