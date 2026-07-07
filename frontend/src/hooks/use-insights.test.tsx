import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuth } from "@/hooks/use-auth";
import {
  useLearningProfile,
  type LearningProfile,
} from "@/hooks/use-insights";
import {
  useMarkFollowUpViewed,
  type FollowUpAction,
} from "@/hooks/use-follow-ups";
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

describe("useLearningProfile", () => {
  it("GETs the student learning profile and unwraps the reshaped mastery groups", async () => {
    const { getToken } = stubAuth();
    const profile: LearningProfile = {
      course_id: "course-1",
      has_evidence: true,
      concept_count: 2,
      groups: {
        strong: [
          {
            concept_id: "c-1",
            concept_name: "Present perfect",
            mastery_score: 0.82,
            confidence: 0.7,
            attempt_count: 6,
            last_attempt_at: "2026-07-07T00:00:00Z",
          },
        ],
        developing: [],
        weak: [
          {
            concept_id: "c-2",
            concept_name: "Reported speech",
            mastery_score: 0.31,
            confidence: 0.6,
            attempt_count: 4,
            last_attempt_at: "2026-07-06T00:00:00Z",
          },
        ],
      },
      disclaimer: "This is a snapshot of your practice, not a grade.",
    };
    mockApiFetch.mockResolvedValue({ success: true, data: profile });

    const { result } = renderHook(() => useLearningProfile("course-1"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(profile);
    expect(getToken).toHaveBeenCalledWith({ template: "backend" });
    expect(mockApiFetch).toHaveBeenCalledWith(
      "/users/me/courses/course-1/insights",
      { token: "jwt-token" }
    );
  });
});

describe("useMarkFollowUpViewed", () => {
  it("POSTs the viewed transition and returns the updated follow-up", async () => {
    const { getToken } = stubAuth();
    const updated: FollowUpAction = {
      id: "fu-1",
      learning_note_id: "note-1",
      course_id: "course-1",
      user_id: "student-1",
      action_type: "revisit_checkpoint",
      target_kind: "checkpoint",
      target_id: "cp-1",
      assignment_status: "viewed",
      due_at: null,
      assigned_by: "teacher-1",
      created_at: "2026-07-07T00:00:00Z",
    };
    mockApiFetch.mockResolvedValue({ success: true, data: updated });

    const { result } = renderHook(() => useMarkFollowUpViewed(), {
      wrapper: createWrapper(),
    });

    const returned = await result.current.mutateAsync("fu-1");

    expect(returned).toEqual(updated);
    expect(getToken).toHaveBeenCalledWith({ template: "backend" });
    expect(mockApiFetch).toHaveBeenCalledWith("/follow-ups/fu-1/viewed", {
      method: "POST",
      token: "jwt-token",
    });
  });

  it("throws when the backend token is unavailable", async () => {
    stubAuth(null);
    const { result } = renderHook(() => useMarkFollowUpViewed(), {
      wrapper: createWrapper(),
    });

    await expect(result.current.mutateAsync("fu-1")).rejects.toThrow(
      "Not authenticated"
    );
    expect(mockApiFetch).not.toHaveBeenCalled();
  });
});
