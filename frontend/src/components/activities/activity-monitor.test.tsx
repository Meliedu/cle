import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { ActivityMonitor } from "./activity-monitor";
import {
  useActivityMonitor,
  type ActivityMonitorState,
} from "@/hooks/use-activities";

vi.mock("@/hooks/use-auth", () => ({
  useAuth: () => ({ getToken: vi.fn().mockResolvedValue("jwt-token") }),
}));

vi.mock("@/hooks/use-activities", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/use-activities")>();
  return { ...actual, useActivityMonitor: vi.fn() };
});

const mockUseMonitor = vi.mocked(useActivityMonitor);

function setState(overrides: Partial<ActivityMonitorState> = {}) {
  mockUseMonitor.mockReturnValue({
    submission_count: 0,
    distribution: {},
    closed: false,
    connected: false,
    ...overrides,
  });
}

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

describe("ActivityMonitor", () => {
  it("renders a swipe left/right distribution and the submission count", () => {
    setState({
      connected: true,
      submission_count: 14,
      distribution: { left: 5, right: 9 },
    });

    render(
      <NextIntlClientProvider locale="en" messages={messages}>
        <ActivityMonitor activityId="a1" format="swipe" enabled />
      </NextIntlClientProvider>
    );

    expect(screen.getByText("14")).toBeTruthy();
    expect(screen.getByText("Live")).toBeTruthy();
    expect(screen.getByText("Left")).toBeTruthy();
    expect(screen.getByText("Right")).toBeTruthy();
    // both bucket counts render
    expect(screen.getByText("5")).toBeTruthy();
    expect(screen.getByText("9")).toBeTruthy();
  });

  it("renders a vote tally bar per option key", () => {
    setState({
      connected: true,
      submission_count: 6,
      distribution: { Yes: 4, No: 2 },
    });

    render(
      <NextIntlClientProvider locale="en" messages={messages}>
        <ActivityMonitor activityId="a1" format="vote" enabled />
      </NextIntlClientProvider>
    );

    expect(screen.getByText("Yes")).toBeTruthy();
    expect(screen.getByText("No")).toBeTruthy();
  });

  it("shows the terminal closed notice once the activity closes", () => {
    setState({ closed: true, connected: true, submission_count: 20, distribution: { left: 10, right: 10 } });

    render(
      <NextIntlClientProvider locale="en" messages={messages}>
        <ActivityMonitor activityId="a1" format="swipe" enabled />
      </NextIntlClientProvider>
    );

    expect(
      screen.getByText("This activity has closed. No more responses will arrive.")
    ).toBeTruthy();
    expect(screen.getByText("Closed")).toBeTruthy();
  });
});
