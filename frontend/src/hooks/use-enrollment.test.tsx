import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuth } from "@/hooks/use-auth";
import {
  branchFromLookup,
  joinErrorReason,
  useEnrollByCode,
  useLookupCode,
  type CourseLookup,
} from "@/hooks/use-enrollment";
import { ApiError, apiFetch } from "@/lib/api";

vi.mock("@/hooks/use-auth", () => ({ useAuth: vi.fn() }));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, apiFetch: vi.fn() };
});

const mockUseAuth = vi.mocked(useAuth);
const mockApiFetch = vi.mocked(apiFetch);

function stubAuth(token: string | null = "jwt-token") {
  mockUseAuth.mockReturnValue({
    getToken: vi.fn(async () => token),
    isSignedIn: true,
    isLoaded: true,
    userId: null,
    signOut: vi.fn(async () => {}),
  });
}

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("joinErrorReason", () => {
  it("maps typed gate codes and 404 to reasons", () => {
    expect(joinErrorReason(new ApiError(409, "m", "d", "JOIN_CODE_INACTIVE"))).toBe(
      "inactive"
    );
    expect(joinErrorReason(new ApiError(409, "m", "d", "SETUP_NOT_OPEN"))).toBe(
      "not_open"
    );
    expect(joinErrorReason(new ApiError(404, "not found"))).toBe("invalid");
    expect(joinErrorReason(new ApiError(400, "m", "d", "JOIN_CODE_INVALID"))).toBe(
      "invalid"
    );
  });

  it("falls back to unknown for other errors", () => {
    expect(joinErrorReason(new ApiError(500, "boom"))).toBe("unknown");
    expect(joinErrorReason(new Error("network"))).toBe("unknown");
    expect(joinErrorReason(null)).toBe("unknown");
  });
});

describe("branchFromLookup", () => {
  const base: CourseLookup = {
    course_id: "c1",
    name: "LANG1511",
    is_open: true,
    join_mode: "code",
    code_active: true,
  };

  it("advances an active code with the course id", () => {
    const branch = branchFromLookup(base);
    expect(branch).toEqual({ kind: "advance", courseId: "c1", lookup: base });
  });

  it("routes a deactivated code to the invalid (inactive) state", () => {
    const branch = branchFromLookup({ ...base, code_active: false });
    expect(branch).toEqual({ kind: "invalid", reason: "inactive" });
  });
});

describe("useEnrollByCode", () => {
  it("POSTs the code and returns { course, enrollment_status }", async () => {
    stubAuth();
    mockApiFetch.mockResolvedValue({
      success: true,
      data: {
        course: { id: "course-9", name: "LANG1511" },
        enrollment_status: "pending",
      },
    });

    const { result } = renderHook(() => useEnrollByCode(), {
      wrapper: createWrapper(),
    });

    result.current.mutate("ABCD2345");

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.course.id).toBe("course-9");
    expect(result.current.data?.enrollment_status).toBe("pending");
    expect(mockApiFetch).toHaveBeenCalledWith("/courses/enroll-by-code", {
      method: "POST",
      token: "jwt-token",
      body: JSON.stringify({ enroll_code: "ABCD2345" }),
    });
  });
});

describe("useLookupCode", () => {
  it("GETs the code-gated lookup and unwraps the envelope", async () => {
    stubAuth();
    const lookup: CourseLookup = {
      course_id: "c1",
      name: "LANG1511",
      is_open: true,
      join_mode: "code",
      code_active: true,
    };
    mockApiFetch.mockResolvedValue({ success: true, data: lookup });

    const { result } = renderHook(() => useLookupCode(), {
      wrapper: createWrapper(),
    });

    result.current.mutate("ABCD2345");

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(lookup);
    expect(mockApiFetch).toHaveBeenCalledWith(
      "/courses/lookup?code=ABCD2345",
      { token: "jwt-token" }
    );
  });
});
