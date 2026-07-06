import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuth } from "@/hooks/use-auth";
import { useAuthedQuery } from "@/hooks/use-authed-query";
import { ApiError, apiFetch } from "@/lib/api";

vi.mock("@/hooks/use-auth", () => ({
  useAuth: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, apiFetch: vi.fn() };
});

const mockUseAuth = vi.mocked(useAuth);
const mockApiFetch = vi.mocked(apiFetch);

interface AuthStateInput {
  readonly isSignedIn: boolean | undefined;
  readonly token?: string | null;
}

function stubAuth({ isSignedIn, token = "jwt-token" }: AuthStateInput) {
  const getToken = vi.fn(async () => token);
  mockUseAuth.mockReturnValue({
    getToken,
    isSignedIn,
    isLoaded: isSignedIn !== undefined,
    userId: null,
    signOut: vi.fn(async () => {}),
  });
  return { getToken };
}

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retryDelay: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    );
  };
}

interface TestQueryOverrides {
  readonly enabled?: boolean;
  readonly retry?: boolean | number;
}

function renderAuthedQuery(options: TestQueryOverrides = {}) {
  return renderHook(
    () =>
      useAuthedQuery<{ value: string }>({
        queryKey: ["test-key"],
        path: "/test",
        ...options,
      }),
    { wrapper: createWrapper() }
  );
}

/** Flush pending microtasks so a would-be fetch has a chance to fire. */
async function flush() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useAuthedQuery", () => {
  it("stays disabled while signed out and fires no fetch", async () => {
    stubAuth({ isSignedIn: false });

    const { result } = renderAuthedQuery();
    await flush();

    expect(result.current.fetchStatus).toBe("idle");
    expect(result.current.status).toBe("pending");
    expect(mockApiFetch).not.toHaveBeenCalled();
  });

  it("errors when the token resolves to null", async () => {
    stubAuth({ isSignedIn: true, token: null });

    const { result } = renderAuthedQuery({ retry: false });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(Error);
    expect((result.current.error as Error).message).toBe("Not authenticated");
    expect(mockApiFetch).not.toHaveBeenCalled();
  });

  it("does not retry auth errors (401): fetch fires exactly once", async () => {
    stubAuth({ isSignedIn: true });
    mockApiFetch.mockRejectedValue(new ApiError(401, "Not authorized"));

    const { result } = renderAuthedQuery();

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(mockApiFetch).toHaveBeenCalledTimes(1);
  });

  it("does not retry auth errors (403): fetch fires exactly once", async () => {
    stubAuth({ isSignedIn: true });
    mockApiFetch.mockRejectedValue(new ApiError(403, "Forbidden"));

    const { result } = renderAuthedQuery();

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(mockApiFetch).toHaveBeenCalledTimes(1);
  });

  it("unwraps the envelope and returns data on success", async () => {
    const { getToken } = stubAuth({ isSignedIn: true });
    mockApiFetch.mockResolvedValue({
      success: true,
      data: { value: "hello" },
    });

    const { result } = renderAuthedQuery();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({ value: "hello" });
    expect(getToken).toHaveBeenCalledWith({ template: "backend" });
    expect(mockApiFetch).toHaveBeenCalledWith("/test", { token: "jwt-token" });
  });

  it("honors caller enabled: false even when signed in", async () => {
    stubAuth({ isSignedIn: true });

    const { result } = renderAuthedQuery({ enabled: false });
    await flush();

    expect(result.current.fetchStatus).toBe("idle");
    expect(mockApiFetch).not.toHaveBeenCalled();
  });
});
