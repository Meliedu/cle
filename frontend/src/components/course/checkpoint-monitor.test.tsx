import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { CheckpointMonitor } from "./checkpoint-monitor";
import {
  useCheckpointMonitor,
  type CheckpointMonitorState,
} from "@/hooks/use-checkpoints";

vi.mock("@/hooks/use-auth", () => ({
  useAuth: () => ({ getToken: vi.fn().mockResolvedValue("jwt-token") }),
}));

vi.mock("@/hooks/use-checkpoints", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/hooks/use-checkpoints")>();
  return { ...actual, useCheckpointMonitor: vi.fn() };
});

const mockUseMonitor = vi.mocked(useCheckpointMonitor);

function setState(overrides: Partial<CheckpointMonitorState> = {}) {
  mockUseMonitor.mockReturnValue({
    submission_count: 0,
    confidence_distribution: {},
    closed: false,
    connected: false,
    ...overrides,
  });
}

function renderMonitor(enabled = true) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <CheckpointMonitor checkpointId="cp1" enabled={enabled} />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

describe("CheckpointMonitor", () => {
  it("renders the submission count and a bar per confidence bucket", () => {
    // counts 5..9 avoid colliding with the −2..+2 bucket labels
    setState({
      connected: true,
      submission_count: 12,
      confidence_distribution: { "-2": 5, "-1": 6, "0": 7, "1": 8, "2": 9 },
    });

    renderMonitor();

    expect(screen.getByText("12")).toBeTruthy();
    expect(screen.getByText("Responses")).toBeTruthy();
    // live connection state
    expect(screen.getByText("Live")).toBeTruthy();
    // every −2..+2 bucket labelled + its count rendered
    for (const key of ["-2", "-1", "0", "1", "2"]) {
      expect(screen.getByText(key)).toBeTruthy();
    }
    for (const count of ["5", "6", "7", "8", "9"]) {
      expect(screen.getByText(count)).toBeTruthy();
    }
  });

  it("shows the connecting state before the socket opens", () => {
    setState({ connected: false });

    renderMonitor();

    expect(screen.getByText("Connecting…")).toBeTruthy();
  });

  it("renders the terminal closed notice once the checkpoint closes", () => {
    setState({ closed: true, connected: true, submission_count: 20 });

    renderMonitor();

    expect(
      screen.getByText(
        "This checkpoint has closed. No more responses will arrive."
      )
    ).toBeTruthy();
    expect(screen.getByText("Closed")).toBeTruthy();
  });
});
