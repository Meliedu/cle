import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { AttendanceRoster } from "./attendance-roster";
import { AttendanceOverrideDialog } from "./attendance-override-dialog";
import {
  useMeetingAttendance,
  useOverrideAttendance,
  type AttendanceRoster as AttendanceRosterType,
  type AttendanceRosterEntry,
} from "@/hooks/use-checkpoints";

vi.mock("@/hooks/use-auth", () => ({
  useAuth: () => ({ getToken: vi.fn().mockResolvedValue("jwt-token") }),
}));

vi.mock("@/hooks/use-checkpoints", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/hooks/use-checkpoints")>();
  return {
    ...actual,
    useMeetingAttendance: vi.fn(),
    useOverrideAttendance: vi.fn(),
  };
});

const mockUseAttendance = vi.mocked(useMeetingAttendance);
const mockUseOverride = vi.mocked(useOverrideAttendance);

function makeEntry(
  overrides: Partial<AttendanceRosterEntry> = {}
): AttendanceRosterEntry {
  return {
    user_id: "u1",
    full_name: "Ada Lovelace",
    email: "ada@connect.ust.hk",
    status: "present",
    attendance_id: "att1",
    source: "qr",
    override_reason: null,
    override_by: null,
    checked_in_at: "2026-01-15T10:31:00Z",
    ...overrides,
  };
}

function makeRoster(
  entries: readonly AttendanceRosterEntry[]
): AttendanceRosterType {
  return {
    meeting_id: "m1",
    course_id: "c1",
    present_count: entries.filter((e) => e.status === "present").length,
    late_count: entries.filter((e) => e.status === "late").length,
    excused_count: entries.filter((e) => e.status === "excused").length,
    absent_count: entries.filter((e) => e.status === "absent").length,
    entries,
  };
}

function withIntl(node: React.ReactNode) {
  return (
    <NextIntlClientProvider locale="en" messages={messages}>
      {node}
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  mockUseOverride.mockReturnValue({
    mutateAsync: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useOverrideAttendance>);
});

describe("AttendanceRoster", () => {
  it("renders a row per student with the tallies", () => {
    mockUseAttendance.mockReturnValue({
      data: makeRoster([
        makeEntry({ user_id: "u1", full_name: "Ada Lovelace", status: "present" }),
        makeEntry({
          user_id: "u2",
          full_name: "Alan Turing",
          status: "absent",
          attendance_id: null,
          source: null,
        }),
      ]),
      isLoading: false,
    } as unknown as ReturnType<typeof useMeetingAttendance>);

    render(withIntl(<AttendanceRoster meetingId="m1" />));

    expect(screen.getByText("Ada Lovelace")).toBeTruthy();
    expect(screen.getByText("Alan Turing")).toBeTruthy();
    // "Present"/"Absent" appear as both a tally label and a status chip
    expect(screen.getAllByText("Present").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Absent").length).toBeGreaterThan(0);
  });

  it("disables override for a derived-absent row (no attendance record)", () => {
    mockUseAttendance.mockReturnValue({
      data: makeRoster([
        makeEntry({
          user_id: "u2",
          full_name: "Alan Turing",
          status: "absent",
          attendance_id: null,
          source: null,
        }),
      ]),
      isLoading: false,
    } as unknown as ReturnType<typeof useMeetingAttendance>);

    render(withIntl(<AttendanceRoster meetingId="m1" />));

    const overrideBtn = screen.getByRole("button", { name: "Override" });
    expect(overrideBtn.hasAttribute("disabled")).toBe(true);
  });

  it("renders an empty state when there are no entries", () => {
    mockUseAttendance.mockReturnValue({
      data: makeRoster([]),
      isLoading: false,
    } as unknown as ReturnType<typeof useMeetingAttendance>);

    render(withIntl(<AttendanceRoster meetingId="m1" />));

    expect(screen.getByText("No attendance yet")).toBeTruthy();
  });
});

describe("AttendanceOverrideDialog — reason guard", () => {
  it("keeps confirm disabled until a non-empty reason is entered", () => {
    render(
      withIntl(
        <AttendanceOverrideDialog
          open
          onOpenChange={() => {}}
          meetingId="m1"
          entry={makeEntry({ status: "absent" })}
        />
      )
    );

    const confirm = screen.getByRole("button", { name: "Save override" });
    // no reason yet → blocked
    expect(confirm.hasAttribute("disabled")).toBe(true);

    const reason = screen.getByRole("textbox");
    fireEvent.change(reason, { target: { value: "Medical leave, emailed" } });

    expect(confirm.hasAttribute("disabled")).toBe(false);
  });
});
