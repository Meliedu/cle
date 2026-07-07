import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { EnrollmentOverview } from "./enrollment-overview";
import { useCourse, type CourseResponse } from "@/hooks/use-courses";
import { useRoster, useJoinRequests } from "@/hooks/use-enrollment";

vi.mock("@/hooks/use-courses", () => ({ useCourse: vi.fn() }));
vi.mock("@/hooks/use-enrollment", () => ({
  useRoster: vi.fn(),
  useJoinRequests: vi.fn(),
}));

const mockUseCourse = vi.mocked(useCourse);
const mockUseRoster = vi.mocked(useRoster);
const mockUseJoinRequests = vi.mocked(useJoinRequests);

function makeCourse(overrides: Partial<CourseResponse> = {}): CourseResponse {
  return {
    id: "c1",
    name: "LANG1512",
    code: "LANG1512",
    description: null,
    language: "en",
    semester: "2026 Spring",
    instructor_id: "i1",
    enroll_code: "ABCD2345",
    enroll_code_active: true,
    settings: {},
    setup_status: "published",
    setup_checklist: {},
    join_mode: "code",
    context_status: "approved",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderOverview() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <EnrollmentOverview courseId="c1" />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  mockUseCourse.mockReturnValue({
    data: makeCourse(),
    isLoading: false,
  } as unknown as ReturnType<typeof useCourse>);
  mockUseRoster.mockReturnValue({
    data: [{ role: "student" }, { role: "student" }, { role: "instructor" }],
    isLoading: false,
  } as unknown as ReturnType<typeof useRoster>);
  mockUseJoinRequests.mockReturnValue({
    data: [],
    isLoading: false,
  } as unknown as ReturnType<typeof useJoinRequests>);
});

describe("EnrollmentOverview", () => {
  it("counts active students (instructors excluded) and pending requests", () => {
    mockUseJoinRequests.mockReturnValue({
      data: [{ enrollment_id: "e1" }, { enrollment_id: "e2" }, { enrollment_id: "e3" }],
      isLoading: false,
    } as unknown as ReturnType<typeof useJoinRequests>);
    renderOverview();
    // 2 students (instructor excluded)
    expect(screen.getByText("Enrolled students")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    // Pending count reflects the join-requests list length (3).
    expect(screen.getByText("Pending requests")).toBeTruthy();
    expect(screen.getByText("3")).toBeTruthy();
  });

  it("shows the join-access state as active for an active code course", () => {
    renderOverview();
    expect(screen.getByText("Join access")).toBeTruthy();
    expect(screen.getByText("Active")).toBeTruthy();
  });

  it("surfaces the approval-required badge for code_plus_approval courses", () => {
    mockUseCourse.mockReturnValue({
      data: makeCourse({ join_mode: "code_plus_approval" }),
      isLoading: false,
    } as unknown as ReturnType<typeof useCourse>);
    renderOverview();
    expect(screen.getByText("Approval required")).toBeTruthy();
  });

  it("shows a pending banner only when there are pending requests", () => {
    renderOverview();
    expect(screen.queryByText(/awaiting approval/i)).toBeNull();

    cleanup();
    mockUseJoinRequests.mockReturnValue({
      data: [{ enrollment_id: "e1" }, { enrollment_id: "e2" }, { enrollment_id: "e3" }],
      isLoading: false,
    } as unknown as ReturnType<typeof useJoinRequests>);
    renderOverview();
    expect(screen.getByText(/3 students are awaiting approval/i)).toBeTruthy();
  });
});
