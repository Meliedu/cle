import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuth } from "@/hooks/use-auth";
import {
  setupErrorCode,
  setupKeys,
  useSetStep,
  useSetupState,
  type SetupState,
} from "@/hooks/use-setup";
import { ApiError, apiFetch } from "@/lib/api";

vi.mock("@/hooks/use-auth", () => ({ useAuth: vi.fn() }));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, apiFetch: vi.fn() };
});

const mockUseAuth = vi.mocked(useAuth);
const mockApiFetch = vi.mocked(apiFetch);

function stubAuth(token: string | null = "jwt-token") {
  const getToken = vi.fn(async () => token);
  mockUseAuth.mockReturnValue({
    getToken,
    isSignedIn: true,
    isLoaded: true,
    userId: null,
    signOut: vi.fn(async () => {}),
  });
  return { getToken };
}

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, retryDelay: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

const STATE: SetupState = {
  setup_status: "in_review",
  context_status: "draft",
  steps: { basics: true, syllabus: false },
  missing: ["syllabus"],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("setupKeys", () => {
  it("namespaces every slice under ['setup', courseId]", () => {
    expect(setupKeys.state("c1")).toEqual(["setup", "c1"]);
    expect(setupKeys.analysis("c1")).toEqual(["setup", "c1", "analysis"]);
    expect(setupKeys.scoreCategories("c1")).toEqual([
      "setup",
      "c1",
      "score-categories",
    ]);
  });
});

describe("setupErrorCode", () => {
  it("maps a known typed gate code", () => {
    expect(
      setupErrorCode(new ApiError(409, "msg", "detail", "SETUP_INCOMPLETE"))
    ).toBe("SETUP_INCOMPLETE");
    expect(
      setupErrorCode(new ApiError(409, "msg", "detail", "SETUP_NOT_OPEN"))
    ).toBe("SETUP_NOT_OPEN");
    expect(
      setupErrorCode(new ApiError(422, "msg", "detail", "UNKNOWN_STEP"))
    ).toBe("UNKNOWN_STEP");
  });

  it("returns null for an unknown code, a codeless ApiError, or a plain error", () => {
    expect(
      setupErrorCode(new ApiError(500, "msg", "detail", "SOMETHING_ELSE"))
    ).toBeNull();
    expect(setupErrorCode(new ApiError(404, "not found"))).toBeNull();
    expect(setupErrorCode(new Error("boom"))).toBeNull();
    expect(setupErrorCode(null)).toBeNull();
  });
});

describe("useSetupState", () => {
  it("GETs the setup path and unwraps the envelope", async () => {
    const { getToken } = stubAuth();
    mockApiFetch.mockResolvedValue({ success: true, data: STATE });

    const { result } = renderHook(() => useSetupState("c1"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(STATE);
    expect(getToken).toHaveBeenCalledWith({ template: "backend" });
    expect(mockApiFetch).toHaveBeenCalledWith("/courses/c1/setup", {
      token: "jwt-token",
    });
  });
});

describe("useSetStep", () => {
  it("PATCHes the step update and returns the new state", async () => {
    stubAuth();
    const next: SetupState = {
      ...STATE,
      steps: { basics: true, syllabus: true },
      missing: [],
    };
    mockApiFetch.mockResolvedValue({ success: true, data: next });

    const { result } = renderHook(() => useSetStep("c1"), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ step: "syllabus", done: true });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(next);
    expect(mockApiFetch).toHaveBeenCalledWith("/courses/c1/setup", {
      method: "PATCH",
      token: "jwt-token",
      body: JSON.stringify({ step: "syllabus", done: true }),
    });
  });
});
