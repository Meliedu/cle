import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuth } from "@/hooks/use-auth";
import {
  useApproveReport,
  useReports,
  type ReportResponse,
} from "@/hooks/use-reports";
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

const sampleReport: ReportResponse = {
  id: "rep-1",
  course_id: "course-1",
  audience: "student",
  user_id: "student-1",
  period: "weekly",
  period_start: "2026-07-01T00:00:00Z",
  period_end: "2026-07-07T00:00:00Z",
  body: {
    summary: "Steady progress on pronunciation.",
    observations: [],
    completed_work: { completed_count: 3 },
    weak_points: [{ concept_id: "c-1", name: "Tone sandhi", mastery_score: 0.4 }],
    next_actions: [],
    claim_limits: "Draft interpretations, reviewed by your instructor.",
  },
  evidence_refs: ["note-1"],
  status: "draft",
  reviewed_by: null,
  reviewed_at: null,
  sent_at: null,
  export_history: [],
  created_at: "2026-07-07T00:00:00Z",
  updated_at: "2026-07-07T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useReports", () => {
  it("GETs the course report archive with the audience/period/status filters", async () => {
    const { getToken } = stubAuth();
    mockApiFetch.mockResolvedValue({ success: true, data: [sampleReport] });

    const { result } = renderHook(
      () =>
        useReports("course-1", {
          audience: "student",
          period: "weekly",
          status: "draft",
        }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([sampleReport]);
    expect(getToken).toHaveBeenCalledWith({ template: "backend" });
    expect(mockApiFetch).toHaveBeenCalledWith(
      "/courses/course-1/reports?audience=student&period=weekly&status=draft",
      { token: "jwt-token" }
    );
  });
});

describe("useApproveReport", () => {
  it("POSTs the approve transition and returns the reviewed report", async () => {
    const { getToken } = stubAuth();
    const reviewed = { ...sampleReport, status: "reviewed" as const };
    mockApiFetch.mockResolvedValue({ success: true, data: reviewed });

    const { result } = renderHook(() => useApproveReport("course-1"), {
      wrapper: createWrapper(),
    });

    const returned = await result.current.mutateAsync("rep-1");

    expect(returned).toEqual(reviewed);
    expect(getToken).toHaveBeenCalledWith({ template: "backend" });
    expect(mockApiFetch).toHaveBeenCalledWith("/reports/rep-1/approve", {
      method: "POST",
      token: "jwt-token",
    });
  });

  it("throws when the backend token is unavailable", async () => {
    stubAuth(null);
    const { result } = renderHook(() => useApproveReport("course-1"), {
      wrapper: createWrapper(),
    });

    await expect(result.current.mutateAsync("rep-1")).rejects.toThrow(
      "Not authenticated"
    );
    expect(mockApiFetch).not.toHaveBeenCalled();
  });
});
