import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { StudentSessionsList } from "./student-sessions-list";
import { useMeetings, type Meeting } from "@/hooks/use-meetings";

vi.mock("@/hooks/use-meetings", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/use-meetings")>();
  return { ...actual, useMeetings: vi.fn() };
});

const mockUseMeetings = vi.mocked(useMeetings);

function makeMeeting(overrides: Partial<Meeting> = {}): Meeting {
  return {
    id: "m1",
    course_id: "c1",
    module_id: null,
    meeting_index: 1,
    title: "Intro",
    scheduled_at: "2026-07-10T10:30:00Z",
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

function setMeetings(
  data: readonly Meeting[] | undefined,
  extra: Partial<ReturnType<typeof useMeetings>> = {}
) {
  mockUseMeetings.mockReturnValue({
    data,
    isLoading: false,
    isError: false,
    ...extra,
  } as unknown as ReturnType<typeof useMeetings>);
}

function renderList() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <StudentSessionsList courseId="c1" />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

describe("StudentSessionsList", () => {
  it("shows only released/completed sessions and hides locked ones", () => {
    setMeetings([
      makeMeeting({ id: "m1", meeting_index: 1, release_state: "released" }),
      makeMeeting({
        id: "m2",
        meeting_index: 2,
        release_state: "locked",
        topic_summary: "Hidden topic",
      }),
      makeMeeting({
        id: "m3",
        meeting_index: 3,
        release_state: "completed",
        topic_summary: "Wrap up",
      }),
    ]);

    renderList();

    expect(screen.getByText("Reading strategies")).toBeTruthy();
    expect(screen.getByText("Wrap up")).toBeTruthy();
    expect(screen.queryByText("Hidden topic")).toBe(null);
    // completed group heading present
    expect(screen.getByText("Completed sessions")).toBeTruthy();
  });

  it("renders a designed empty state when nothing is released", () => {
    setMeetings([makeMeeting({ release_state: "locked" })]);
    renderList();
    expect(screen.getByText("No sessions open yet")).toBeTruthy();
  });
});
