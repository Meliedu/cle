import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { RosterDetail } from "./roster-detail";
import { useRoster, type RosterEntry } from "@/hooks/use-enrollment";

vi.mock("@/hooks/use-enrollment", () => ({ useRoster: vi.fn() }));

const mockUseRoster = vi.mocked(useRoster);

function entry(overrides: Partial<RosterEntry> = {}): RosterEntry {
  return {
    enrollment_id: "e1",
    user_id: "u1",
    full_name: "Hana Kim",
    email: "hana@connect.ust.hk",
    role: "student",
    enrolled_at: "2026-01-15T10:00:00Z",
    status: "active",
    ...overrides,
  };
}

function renderRoster() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <RosterDetail courseId="c1" />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("RosterDetail", () => {
  it("renders a row per active student (instructors excluded)", () => {
    mockUseRoster.mockReturnValue({
      data: [
        entry(),
        entry({
          enrollment_id: "e2",
          user_id: "u2",
          full_name: "Alex Wong",
          email: "alex@connect.ust.hk",
        }),
        entry({
          enrollment_id: "e3",
          user_id: "u3",
          full_name: "Prof Lee",
          email: "lee@ust.hk",
          role: "instructor",
        }),
      ],
      isLoading: false,
    } as unknown as ReturnType<typeof useRoster>);

    renderRoster();

    expect(screen.getByText("Hana Kim")).toBeTruthy();
    expect(screen.getByText("hana@connect.ust.hk")).toBeTruthy();
    expect(screen.getByText("Alex Wong")).toBeTruthy();
    // Instructor is filtered out of the student roster.
    expect(screen.queryByText("Prof Lee")).toBeNull();
    // Joined date is rendered for each student row.
    expect(screen.getAllByText(/2026/)).toHaveLength(2);
    // 2 students count line.
    expect(screen.getByText("2 students")).toBeTruthy();
  });

  it("shows an empty state when there are no students", () => {
    mockUseRoster.mockReturnValue({
      data: [entry({ role: "instructor", full_name: "Prof Lee" })],
      isLoading: false,
    } as unknown as ReturnType<typeof useRoster>);

    renderRoster();

    expect(screen.getByText("No students yet")).toBeTruthy();
  });

  it("shows a loading skeleton while the roster is loading", () => {
    mockUseRoster.mockReturnValue({
      data: undefined,
      isLoading: true,
    } as unknown as ReturnType<typeof useRoster>);

    const { container } = renderRoster();
    // No table while loading.
    expect(container.querySelector("table")).toBeNull();
  });
});
