import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuth } from "@/hooks/use-auth";
import {
  useDecideMemory,
  useMemory,
  type MemoryItemResponse,
} from "@/hooks/use-memory";
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

const sampleItem: MemoryItemResponse = {
  id: "mem-1",
  course_id: "course-1",
  learning_note_id: "note-1",
  kind: "outcome",
  relationship_summary: null,
  action_summary: null,
  outcome_summary: { persistent: true },
  instructor_comment: "Watch tone sandhi next term.",
  carry_forward: false,
  decision: null,
  decided_by: null,
  decided_at: null,
  report_history: [],
  created_at: "2026-07-07T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useMemory", () => {
  it("GETs the course memory list and unwraps the record items", async () => {
    const { getToken } = stubAuth();
    mockApiFetch.mockResolvedValue({ success: true, data: [sampleItem] });

    const { result } = renderHook(() => useMemory("course-1"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([sampleItem]);
    expect(getToken).toHaveBeenCalledWith({ template: "backend" });
    expect(mockApiFetch).toHaveBeenCalledWith("/courses/course-1/memory", {
      token: "jwt-token",
    });
  });
});

describe("useDecideMemory", () => {
  it("POSTs the decision and returns the decided record item", async () => {
    const { getToken } = stubAuth();
    const decided = {
      ...sampleItem,
      decision: "carry_forward" as const,
      carry_forward: true,
    };
    mockApiFetch.mockResolvedValue({ success: true, data: decided });

    const { result } = renderHook(() => useDecideMemory("course-1"), {
      wrapper: createWrapper(),
    });

    const returned = await result.current.mutateAsync({
      itemId: "mem-1",
      decision: "carry_forward",
    });

    expect(returned).toEqual(decided);
    expect(getToken).toHaveBeenCalledWith({ template: "backend" });
    expect(mockApiFetch).toHaveBeenCalledWith("/memory/mem-1/decide", {
      method: "POST",
      token: "jwt-token",
      body: JSON.stringify({ decision: "carry_forward" }),
    });
  });

  it("throws when the backend token is unavailable", async () => {
    stubAuth(null);
    const { result } = renderHook(() => useDecideMemory("course-1"), {
      wrapper: createWrapper(),
    });

    await expect(
      result.current.mutateAsync({ itemId: "mem-1", decision: "keep" })
    ).rejects.toThrow("Not authenticated");
    expect(mockApiFetch).not.toHaveBeenCalled();
  });
});
