import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { StepSchedule } from "./step-schedule";
import {
  useCreateMeeting,
  useDeleteMeeting,
  useMeetings,
  useSetMeetingReleaseState,
  useUpdateMeeting,
  type Meeting,
} from "@/hooks/use-meetings";
import { useSetStep } from "@/hooks/use-setup";

vi.mock("@/hooks/use-meetings", () => ({
  useMeetings: vi.fn(),
  useCreateMeeting: vi.fn(),
  useUpdateMeeting: vi.fn(),
  useDeleteMeeting: vi.fn(),
  useSetMeetingReleaseState: vi.fn(),
}));

vi.mock("@/hooks/use-setup", () => ({
  useSetStep: vi.fn(),
}));

const mockUseMeetings = vi.mocked(useMeetings);
const mockUseCreateMeeting = vi.mocked(useCreateMeeting);
const mockUseUpdateMeeting = vi.mocked(useUpdateMeeting);
const mockUseDeleteMeeting = vi.mocked(useDeleteMeeting);
const mockUseSetRelease = vi.mocked(useSetMeetingReleaseState);
const mockUseSetStep = vi.mocked(useSetStep);

function makeMeeting(overrides: Partial<Meeting> = {}): Meeting {
  return {
    id: "m1",
    course_id: "c1",
    module_id: null,
    meeting_index: 1,
    title: null,
    scheduled_at: "2026-01-05T10:00:00Z",
    duration_minutes: 60,
    location: "Room 2503A",
    status: "planned",
    release_state: "locked",
    topic_summary: "Greetings and numbers",
    canvas_event_id: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderStep(onComplete = vi.fn()) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <StepSchedule courseId="c1" onComplete={onComplete} />
    </NextIntlClientProvider>
  );
}

let createMutate: ReturnType<typeof vi.fn>;
let setStepMutate: ReturnType<typeof vi.fn>;

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  createMutate = vi.fn(async () => makeMeeting());
  setStepMutate = vi.fn(async () => ({}));
  mockUseMeetings.mockReturnValue({ data: [], isLoading: false } as unknown as ReturnType<
    typeof useMeetings
  >);
  mockUseCreateMeeting.mockReturnValue({
    mutateAsync: createMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useCreateMeeting>);
  mockUseUpdateMeeting.mockReturnValue({
    mutateAsync: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useUpdateMeeting>);
  mockUseDeleteMeeting.mockReturnValue({
    mutateAsync: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useDeleteMeeting>);
  mockUseSetRelease.mockReturnValue({
    mutateAsync: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useSetMeetingReleaseState>);
  mockUseSetStep.mockReturnValue({
    mutateAsync: setStepMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useSetStep>);
});

describe("StepSchedule", () => {
  it("shows the empty state with Continue disabled when there are no sessions", () => {
    renderStep();
    expect(screen.getByText(/No sessions yet/i)).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: /^Continue$/i }) as HTMLButtonElement).disabled
    ).toBe(true);
  });

  it("lists existing sessions with their venue and enables Continue", () => {
    mockUseMeetings.mockReturnValue({
      data: [makeMeeting()],
      isLoading: false,
    } as unknown as ReturnType<typeof useMeetings>);
    renderStep();
    expect(screen.getByText(/Session 1/)).toBeTruthy();
    expect(screen.getByText(/Room 2503A/)).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: /^Continue$/i }) as HTMLButtonElement).disabled
    ).toBe(false);
  });

  it("creates a session via the meetings API with the entered venue", async () => {
    renderStep();
    fireEvent.change(screen.getByLabelText(/Date & time/i), {
      target: { value: "2026-02-01T09:30" },
    });
    fireEvent.change(screen.getByLabelText(/^Venue$/i), {
      target: { value: "Room 1103" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Add session$/i }));
    await waitFor(() => expect(createMutate).toHaveBeenCalledTimes(1));
    const payload = createMutate.mock.calls[0][0] as Record<string, unknown>;
    expect(payload.meeting_index).toBe(1);
    expect(payload.location).toBe("Room 1103");
    expect(typeof payload.scheduled_at).toBe("string");
  });

  it("flips the schedule flag when Continue is pressed with a session present", async () => {
    const onComplete = vi.fn();
    mockUseMeetings.mockReturnValue({
      data: [makeMeeting()],
      isLoading: false,
    } as unknown as ReturnType<typeof useMeetings>);
    renderStep(onComplete);
    fireEvent.click(screen.getByRole("button", { name: /^Continue$/i }));
    await waitFor(() =>
      expect(setStepMutate).toHaveBeenCalledWith({ step: "schedule", done: true })
    );
    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
  });
});
