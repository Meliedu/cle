import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { CourseOverview } from "./course-overview";
import { useCourse, type CourseResponse } from "@/hooks/use-courses";
import { useMeetings } from "@/hooks/use-meetings";
import { useDocuments } from "@/hooks/use-documents";
import { useRoster } from "@/hooks/use-enrollment";

vi.mock("@/hooks/use-courses", () => ({ useCourse: vi.fn() }));
vi.mock("@/hooks/use-meetings", () => ({ useMeetings: vi.fn() }));
vi.mock("@/hooks/use-documents", () => ({ useDocuments: vi.fn() }));
vi.mock("@/hooks/use-enrollment", () => ({ useRoster: vi.fn() }));

const mockUseCourse = vi.mocked(useCourse);
const mockUseMeetings = vi.mocked(useMeetings);
const mockUseDocuments = vi.mocked(useDocuments);
const mockUseRoster = vi.mocked(useRoster);

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
      <CourseOverview courseId="c1" />
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
  mockUseMeetings.mockReturnValue({
    data: [{}, {}, {}],
    isLoading: false,
  } as unknown as ReturnType<typeof useMeetings>);
  mockUseRoster.mockReturnValue({
    data: [{ role: "student" }, { role: "student" }, { role: "instructor" }],
    isLoading: false,
  } as unknown as ReturnType<typeof useRoster>);
  mockUseDocuments.mockReturnValue({
    data: [{}, {}, {}, {}, {}],
    isLoading: false,
  } as unknown as ReturnType<typeof useDocuments>);
});

describe("CourseOverview", () => {
  it("renders the three quick stats from the hooks", () => {
    renderOverview();
    // sessions=3, students=2 (instructor excluded), materials=5
    expect(screen.getByText("Sessions")).toBeTruthy();
    expect(screen.getByText("3")).toBeTruthy();
    expect(screen.getByText("Enrolled students")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("Materials")).toBeTruthy();
    expect(screen.getByText("5")).toBeTruthy();
  });

  it("hides the class code until revealed, then shows it", () => {
    renderOverview();
    expect(screen.queryByText("ABCD2345")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Reveal/i }));
    expect(screen.getByText("ABCD2345")).toBeTruthy();
  });

  it("shows the accepting-joins badge when the code is active", () => {
    renderOverview();
    expect(screen.getByText("Accepting joins")).toBeTruthy();
  });

  it("surfaces a draft banner + finish-setup link when not published", () => {
    mockUseCourse.mockReturnValue({
      data: makeCourse({ setup_status: "draft", context_status: "draft" }),
      isLoading: false,
    } as unknown as ReturnType<typeof useCourse>);
    renderOverview();
    expect(screen.getByText("This course is still in setup")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Continue setup/i })).toBeTruthy();
  });
});
