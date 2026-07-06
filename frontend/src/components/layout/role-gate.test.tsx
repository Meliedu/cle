import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RoleGate } from "@/components/layout/role-gate";
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

interface RoleStateInput {
  readonly role: "instructor" | "student" | null;
}

function stubRole({ role }: RoleStateInput) {
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

describe("RoleGate", () => {
  it("renders children when the role matches allow", () => {
    stubRole({ role: "instructor" });

    render(
      <RoleGate allow="instructor">
        <p>instructor content</p>
      </RoleGate>
    );

    expect(screen.getByText("instructor content")).toBeTruthy();
    expect(replace).not.toHaveBeenCalled();
  });

  it("renders nothing and redirects to the role home when the role mismatches", () => {
    stubRole({ role: "student" });

    render(
      <RoleGate allow="instructor">
        <p>instructor content</p>
      </RoleGate>
    );

    expect(screen.queryByText("instructor content")).toBeNull();
    expect(replace).toHaveBeenCalledTimes(1);
    expect(replace).toHaveBeenCalledWith("/student/dashboard");
  });

  it("renders nothing and never redirects while the role is loading (null)", () => {
    stubRole({ role: null });

    render(
      <RoleGate allow="instructor">
        <p>instructor content</p>
      </RoleGate>
    );

    expect(screen.queryByText("instructor content")).toBeNull();
    expect(replace).not.toHaveBeenCalled();
  });
});
