import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuth } from "@/hooks/use-auth";
import {
  useActivities,
  useCreateActivity,
  type Activity,
} from "@/hooks/use-activities";
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

function makeActivity(overrides: Partial<Activity> = {}): Activity {
  return {
    id: "act-1",
    course_id: "course-1",
    meeting_id: null,
    format: "vote",
    title: "Warm-up poll",
    config: { options: ["A", "B"] },
    status: "draft",
    open_at: null,
    due_at: null,
    close_at: null,
    anonymous: true,
    score_category_id: null,
    points: null,
    grading_mode: null,
    late_rule: null,
    score_bearing: false,
    created_at: "2026-07-08T00:00:00Z",
    updated_at: "2026-07-08T00:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useActivities", () => {
  it("GETs the course activities and unwraps the list", async () => {
    const { getToken } = stubAuth();
    const activities: Activity[] = [makeActivity()];
    mockApiFetch.mockResolvedValue({ success: true, data: activities });

    const { result } = renderHook(() => useActivities("course-1"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(activities);
    expect(getToken).toHaveBeenCalledWith({ template: "backend" });
    expect(mockApiFetch).toHaveBeenCalledWith("/courses/course-1/activities", {
      token: "jwt-token",
    });
  });
});

describe("useCreateActivity", () => {
  it("POSTs the new activity and returns the persisted row", async () => {
    const { getToken } = stubAuth();
    const persisted = makeActivity({ id: "act-2", status: "draft" });
    mockApiFetch.mockResolvedValue({ success: true, data: persisted });

    const { result } = renderHook(() => useCreateActivity("course-1"), {
      wrapper: createWrapper(),
    });

    const returned = await result.current.mutateAsync({
      format: "vote",
      title: "Warm-up poll",
      config: { options: ["A", "B"] },
    });

    expect(returned).toEqual(persisted);
    expect(getToken).toHaveBeenCalledWith({ template: "backend" });
    expect(mockApiFetch).toHaveBeenCalledWith("/courses/course-1/activities", {
      method: "POST",
      token: "jwt-token",
      body: JSON.stringify({
        format: "vote",
        title: "Warm-up poll",
        config: { options: ["A", "B"] },
      }),
    });
  });

  it("throws when the backend token is unavailable", async () => {
    stubAuth(null);
    const { result } = renderHook(() => useCreateActivity("course-1"), {
      wrapper: createWrapper(),
    });

    await expect(
      result.current.mutateAsync({
        format: "vote",
        title: "x",
        config: { options: [] },
      })
    ).rejects.toThrow("Not authenticated");
    expect(mockApiFetch).not.toHaveBeenCalled();
  });
});
