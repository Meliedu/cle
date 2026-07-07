import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuth } from "@/hooks/use-auth";
import {
  useAddWorkItem,
  useChecklist,
  type ChecklistItem,
} from "@/hooks/use-work-items";
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

describe("useChecklist", () => {
  it("GETs the course checklist and unwraps the merged spine items", async () => {
    const { getToken } = stubAuth();
    const items: ChecklistItem[] = [
      {
        id: "wi-1",
        course_id: "course-1",
        source_kind: "checkpoint",
        source_id: "cp-1",
        title: "Lecture 1 checkpoint",
        required: true,
        score_bearing: false,
        due_at: "2026-07-10T00:00:00Z",
        close_at: "2026-07-10T00:00:00Z",
        visible_from: null,
        status: "pending",
      },
    ];
    mockApiFetch.mockResolvedValue({ success: true, data: items });

    const { result } = renderHook(() => useChecklist("course-1"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(items);
    expect(getToken).toHaveBeenCalledWith({ template: "backend" });
    expect(mockApiFetch).toHaveBeenCalledWith("/courses/course-1/checklist", {
      token: "jwt-token",
    });
  });
});

describe("useAddWorkItem", () => {
  it("POSTs the new work_item and returns the persisted row", async () => {
    const { getToken } = stubAuth();
    const persisted = {
      id: "wi-2",
      course_id: "course-1",
      source_kind: "material",
      source_id: null,
      title: "Read chapter 3",
      required: false,
      score_bearing: false,
      due_at: null,
      close_at: null,
      visible_from: null,
      created_by: "teacher-1",
      created_at: "2026-07-08T00:00:00Z",
      updated_at: "2026-07-08T00:00:00Z",
    };
    mockApiFetch.mockResolvedValue({ success: true, data: persisted });

    const { result } = renderHook(() => useAddWorkItem("course-1"), {
      wrapper: createWrapper(),
    });

    const returned = await result.current.mutateAsync({
      title: "Read chapter 3",
      source_kind: "material",
      required: false,
    });

    expect(returned).toEqual(persisted);
    expect(getToken).toHaveBeenCalledWith({ template: "backend" });
    expect(mockApiFetch).toHaveBeenCalledWith("/courses/course-1/work-items", {
      method: "POST",
      token: "jwt-token",
      body: JSON.stringify({
        title: "Read chapter 3",
        source_kind: "material",
        required: false,
      }),
    });
  });

  it("throws when the backend token is unavailable", async () => {
    stubAuth(null);
    const { result } = renderHook(() => useAddWorkItem("course-1"), {
      wrapper: createWrapper(),
    });

    await expect(
      result.current.mutateAsync({ title: "x" })
    ).rejects.toThrow("Not authenticated");
    expect(mockApiFetch).not.toHaveBeenCalled();
  });
});
