import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { SessionsList } from "./sessions-list";
import { useMeetings, type Meeting } from "@/hooks/use-meetings";
import {
  useCheckpoints,
  useCheckpointHistory,
  type Checkpoint,
} from "@/hooks/use-checkpoints";

vi.mock("@/hooks/use-meetings", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/use-meetings")>();
  return { ...actual, useMeetings: vi.fn() };
});
vi.mock("@/hooks/use-checkpoints", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/hooks/use-checkpoints")>();
  return {
    ...actual,
    useCheckpoints: vi.fn(),
    useCheckpointHistory: vi.fn(),
  };
});

const mockUseMeetings = vi.mocked(useMeetings);
const mockUseCheckpoints = vi.mocked(useCheckpoints);
const mockUseCheckpointHistory = vi.mocked(useCheckpointHistory);

function makeMeeting(overrides: Partial<Meeting> = {}): Meeting {
  return {
    id: "m1",
    course_id: "c1",
    module_id: null,
    meeting_index: 1,
    title: "Intro",
    scheduled_at: "2026-01-15T10:30:00Z",
    duration_minutes: 90,
    location: "Room 2402A",
    status: "planned",
    release_state: "released",
    topic_summary: "Reading strategies",
    canvas_event_id: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeCheckpoint(overrides: Partial<Checkpoint> = {}): Checkpoint {
  return {
    id: "cp1",
    course_id: "c1",
    meeting_id: "m1",
    kind: "review",
    status: "draft",
    title: "Session 1 checkpoint",
    qr_enabled: true,
    release_at: null,
    close_at: null,
    close_rule: null,
    generation_meta: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function setCheckpoints(
  draft: readonly Checkpoint[],
  history: readonly Checkpoint[] = []
) {
  mockUseCheckpoints.mockReturnValue({
    data: draft,
  } as unknown as ReturnType<typeof useCheckpoints>);
  mockUseCheckpointHistory.mockReturnValue({
    data: history,
  } as unknown as ReturnType<typeof useCheckpointHistory>);
}

function renderList() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <SessionsList courseId="c1" />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

describe("SessionsList", () => {
  it("renders a row per session with release + checkpoint status", () => {
    mockUseMeetings.mockReturnValue({
      data: [
        makeMeeting({ id: "m1", meeting_index: 1, release_state: "released" }),
        makeMeeting({
          id: "m2",
          meeting_index: 2,
          release_state: "locked",
          topic_summary: "Listening practice",
        }),
      ],
      isLoading: false,
    } as unknown as ReturnType<typeof useMeetings>);
    setCheckpoints([makeCheckpoint({ meeting_id: "m1", status: "published" })]);

    renderList();

    expect(screen.getByText("Reading strategies")).toBeTruthy();
    expect(screen.getByText("Listening practice")).toBeTruthy();
    // release-state chips (localized)
    expect(screen.getByText("Released")).toBeTruthy();
    expect(screen.getByText("Hidden")).toBeTruthy();
    // m1 has a published checkpoint; m2 has none
    expect(screen.getByText("Published")).toBeTruthy();
    expect(screen.getByText("No checkpoint")).toBeTruthy();
  });

  it("splits completed sessions into their own group", () => {
    mockUseMeetings.mockReturnValue({
      data: [
        makeMeeting({ id: "m1", meeting_index: 1, release_state: "released" }),
        makeMeeting({
          id: "m2",
          meeting_index: 2,
          release_state: "completed",
          topic_summary: "Wrap up",
        }),
      ],
      isLoading: false,
    } as unknown as ReturnType<typeof useMeetings>);
    setCheckpoints([]);

    renderList();

    expect(screen.getByText("Active sessions")).toBeTruthy();
    expect(screen.getByText("Completed sessions")).toBeTruthy();
  });

  it("renders an empty state when there are no sessions", () => {
    mockUseMeetings.mockReturnValue({
      data: [],
      isLoading: false,
    } as unknown as ReturnType<typeof useMeetings>);
    setCheckpoints([]);

    renderList();

    expect(screen.getByText("No sessions yet")).toBeTruthy();
  });

  it("shows loading skeletons while sessions load", () => {
    mockUseMeetings.mockReturnValue({
      data: undefined,
      isLoading: true,
    } as unknown as ReturnType<typeof useMeetings>);
    setCheckpoints([]);

    const { container } = renderList();
    expect(container.querySelector('[data-slot="skeleton"]')).toBeTruthy();
  });
});
