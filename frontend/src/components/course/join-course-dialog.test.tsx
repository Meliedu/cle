import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { JoinCourseDialog } from "./join-course-dialog";
import {
  useEnrollByCode,
  type EnrollByCodeResult,
} from "@/hooks/use-enrollment";
import { ApiError } from "@/lib/api";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("@/hooks/use-enrollment", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/hooks/use-enrollment")>();
  return { ...actual, useEnrollByCode: vi.fn() };
});

const mockUseEnrollByCode = vi.mocked(useEnrollByCode);

function stubEnroll(impl: (code: string) => Promise<EnrollByCodeResult>) {
  const mutateAsync = vi.fn(impl);
  mockUseEnrollByCode.mockReturnValue({
    mutateAsync,
    isPending: false,
  } as unknown as ReturnType<typeof useEnrollByCode>);
  return mutateAsync;
}

function renderDialog() {
  return render(<JoinCourseDialog open onOpenChange={vi.fn()} />);
}

function submitCode(value: string) {
  fireEvent.change(screen.getByLabelText("Enrollment code"), {
    target: { value },
  });
  fireEvent.click(screen.getByRole("button", { name: "Join Course" }));
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
});

describe("JoinCourseDialog — enrollment_status branching", () => {
  it("routes an active enrollment to the course workspace using course.id", async () => {
    stubEnroll(async () => ({
      course: {
        id: "course-42",
        name: "LANG1511",
      } as EnrollByCodeResult["course"],
      enrollment_status: "active",
    }));
    renderDialog();

    submitCode("ABCD2345");

    await waitFor(() =>
      expect(push).toHaveBeenCalledWith(
        "/dashboard/courses/course-42?tab=overview"
      )
    );
    // Regression guard: never route to /courses/undefined.
    expect(push).not.toHaveBeenCalledWith(
      expect.stringContaining("undefined")
    );
  });

  it("shows awaiting-approval and does NOT route a pending enrollment", async () => {
    stubEnroll(async () => ({
      course: {
        id: "course-7",
        name: "LANG1511",
      } as EnrollByCodeResult["course"],
      enrollment_status: "pending",
    }));
    renderDialog();

    submitCode("ABCD2345");

    await waitFor(() =>
      expect(screen.getByText("Awaiting approval")).toBeTruthy()
    );
    expect(push).not.toHaveBeenCalled();
  });

  it("maps an inactive-code gate error to reason-specific copy", async () => {
    stubEnroll(async () => {
      throw new ApiError(409, "msg", "detail", "JOIN_CODE_INACTIVE");
    });
    renderDialog();

    submitCode("ABCD2345");

    await waitFor(() =>
      expect(screen.getByText(/no longer active/i)).toBeTruthy()
    );
    expect(push).not.toHaveBeenCalled();
  });

  it("maps a 404 to the invalid-code copy", async () => {
    stubEnroll(async () => {
      throw new ApiError(404, "not found");
    });
    renderDialog();

    submitCode("ZZZZ9999");

    await waitFor(() =>
      expect(
        screen.getByText("No course matches that code")
      ).toBeTruthy()
    );
  });
});
