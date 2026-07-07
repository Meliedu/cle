import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { CourseScheduleTable } from "./course-schedule-table";
import { useMeetings, type Meeting } from "@/hooks/use-meetings";

vi.mock("@/hooks/use-meetings", () => ({ useMeetings: vi.fn() }));

const mockUseMeetings = vi.mocked(useMeetings);

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

function renderTable() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <CourseScheduleTable courseId="c1" />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

describe("CourseScheduleTable", () => {
  it("renders a row per meeting with venue, topic, and release badge", () => {
    mockUseMeetings.mockReturnValue({
      data: [
        makeMeeting({ id: "m1", meeting_index: 1 }),
        makeMeeting({
          id: "m2",
          meeting_index: 2,
          location: "Online",
          topic_summary: null,
          title: "Practice",
          release_state: "locked",
        }),
      ],
      isLoading: false,
    } as unknown as ReturnType<typeof useMeetings>);

    renderTable();

    expect(screen.getByText("Reading strategies")).toBeTruthy();
    expect(screen.getByText("Room 2402A")).toBeTruthy();
    expect(screen.getByText("Online")).toBeTruthy();
    // topic falls back to title when topic_summary is null
    expect(screen.getByText("Practice")).toBeTruthy();
    // release_state → localized badge
    expect(screen.getByText("Released")).toBeTruthy();
    expect(screen.getByText("Hidden")).toBeTruthy();
  });

  it("renders an empty state when there are no meetings", () => {
    mockUseMeetings.mockReturnValue({
      data: [],
      isLoading: false,
    } as unknown as ReturnType<typeof useMeetings>);

    renderTable();

    expect(screen.getByText("No sessions yet")).toBeTruthy();
  });

  it("shows loading skeletons while meetings load", () => {
    mockUseMeetings.mockReturnValue({
      data: undefined,
      isLoading: true,
    } as unknown as ReturnType<typeof useMeetings>);

    const { container } = renderTable();
    expect(container.querySelector('[data-slot="skeleton"]')).toBeTruthy();
  });
});
