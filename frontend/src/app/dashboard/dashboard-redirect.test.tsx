import { render, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import DashboardRedirect from "@/app/dashboard/page";
import { useRole } from "@/hooks/use-role";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));

vi.mock("@/hooks/use-role", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/use-role")>();
  return { ...actual, useRole: vi.fn() };
});

const mockUseRole = vi.mocked(useRole);

function stubRole(role: "instructor" | "student" | null) {
  mockUseRole.mockReturnValue({
    role,
    isInstructor: role === "instructor",
    isStudent: role === "student",
    isLoaded: role !== null,
    isError: false,
  });
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("DashboardRedirect", () => {
  it("redirects an instructor to the teacher dashboard", () => {
    stubRole("instructor");

    render(<DashboardRedirect />);

    expect(replace).toHaveBeenCalledTimes(1);
    expect(replace).toHaveBeenCalledWith("/teacher/dashboard");
  });

  it("redirects a student to the student dashboard", () => {
    stubRole("student");

    render(<DashboardRedirect />);

    expect(replace).toHaveBeenCalledTimes(1);
    expect(replace).toHaveBeenCalledWith("/student/dashboard");
  });

  it("does not redirect while the role is loading (null)", () => {
    stubRole(null);

    render(<DashboardRedirect />);

    expect(replace).not.toHaveBeenCalled();
  });
});
