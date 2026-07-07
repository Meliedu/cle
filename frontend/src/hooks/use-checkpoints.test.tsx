import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuth } from "@/hooks/use-auth";
import {
  useRevisitResponse,
  useSubmitCheckpointResponse,
} from "@/hooks/use-checkpoints";
import { apiFetch } from "@/lib/api";

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

describe("useSubmitCheckpointResponse", () => {
  it("POSTs the review-point answer and returns the persisted response", async () => {
    const { getToken } = stubAuth();
    const persisted = {
      id: "resp-1",
      checkpoint_id: "cp-1",
      card_id: "card-1",
      confidence: 2,
      text_response: null,
      status: "submitted",
      submitted_at: "2026-07-08T00:00:00Z",
    };
    mockApiFetch.mockResolvedValue({ success: true, data: persisted });

    const { result } = renderHook(
      () => useSubmitCheckpointResponse("cp-1", "course-1"),
      { wrapper: createWrapper() }
    );

    const returned = await result.current.mutateAsync({
      card_id: "card-1",
      confidence: 2,
    });

    expect(returned).toEqual(persisted);
    expect(getToken).toHaveBeenCalledWith({ template: "backend" });
    expect(mockApiFetch).toHaveBeenCalledWith("/checkpoints/cp-1/responses", {
      method: "POST",
      token: "jwt-token",
      body: JSON.stringify({ card_id: "card-1", confidence: 2 }),
    });
  });

  it("throws when the backend token is unavailable", async () => {
    stubAuth(null);
    const { result } = renderHook(
      () => useSubmitCheckpointResponse("cp-1"),
      { wrapper: createWrapper() }
    );

    await expect(
      result.current.mutateAsync({ card_id: "card-1", text_response: "done" })
    ).rejects.toThrow("Not authenticated");
    expect(mockApiFetch).not.toHaveBeenCalled();
  });
});

describe("useRevisitResponse", () => {
  it("POSTs to the revisit endpoint and surfaces the before/after delta", async () => {
    stubAuth();
    const revisit = {
      response: {
        id: "resp-2",
        checkpoint_id: "cp-2",
        card_id: "card-2",
        confidence: 1,
        text_response: null,
        status: "submitted",
        submitted_at: "2026-07-08T00:00:00Z",
      },
      carried_from_id: "cp-1",
      concept_id: "concept-1",
      confidence_before: -1,
      confidence_after: 1,
      delta: 2,
    };
    mockApiFetch.mockResolvedValue({ success: true, data: revisit });

    const { result } = renderHook(() => useRevisitResponse("cp-2"), {
      wrapper: createWrapper(),
    });

    const returned = await result.current.mutateAsync({
      card_id: "card-2",
      confidence: 1,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(returned.delta).toBe(2);
    expect(mockApiFetch).toHaveBeenCalledWith(
      "/checkpoints/cp-2/revisit-response",
      {
        method: "POST",
        token: "jwt-token",
        body: JSON.stringify({ card_id: "card-2", confidence: 1 }),
      }
    );
  });
});
