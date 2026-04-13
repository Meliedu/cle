import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@clerk/nextjs";
import { apiFetch, isAuthError } from "@/lib/api";

export interface ProgressResponse {
  readonly course_id: string;
  readonly xp_points: number;
  readonly streak_days: number;
  readonly last_activity_date: string | null;
  readonly quizzes_completed: number;
  readonly flashcards_reviewed: number;
  readonly speaking_sessions: number;
  readonly badges: readonly string[];
}

export interface LeaderboardEntry {
  readonly rank: number;
  readonly user_id: string;
  readonly full_name: string;
  readonly avatar_url: string | null;
  readonly xp_points: number;
}

interface ApiEnvelope<T> {
  readonly success: boolean;
  readonly data: T;
}

interface PaginatedEnvelope<T> {
  readonly success: boolean;
  readonly data: T;
  readonly meta: {
    readonly total: number;
    readonly page: number;
    readonly limit: number;
    readonly pages: number;
  };
}

export function useProgress(courseId: string) {
  const { getToken, isSignedIn } = useAuth();

  return useQuery({
    queryKey: ["progress", courseId],
    queryFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<ProgressResponse>>(
        `/courses/${courseId}/progress`,
        { token }
      );
      return response.data;
    },
    enabled: isSignedIn === true && !!courseId,
    retry: (count: number, error: Error) => {
      if (isAuthError(error)) return false;
      return count < 3;
    },
  });
}

export function useLeaderboard(courseId: string, page = 1) {
  const { getToken, isSignedIn } = useAuth();

  return useQuery({
    queryKey: ["leaderboard", courseId, page],
    queryFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<PaginatedEnvelope<LeaderboardEntry[]>>(
        `/courses/${courseId}/leaderboard?page=${page}`,
        { token }
      );
      return response;
    },
    enabled: isSignedIn === true && !!courseId,
    retry: (count: number, error: Error) => {
      if (isAuthError(error)) return false;
      return count < 3;
    },
  });
}
