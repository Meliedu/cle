"use client";

import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, isAuthError, type ApiEnvelope } from "@/lib/api";

type Role = "instructor" | "student";

interface MeResponse {
  readonly id: string;
  readonly better_auth_id: string;
  readonly email: string;
  readonly full_name: string | null;
  readonly role: string;
  readonly avatar_url: string | null;
  readonly created_at: string;
}

/**
 * Resolves the current user's role from the backend's authoritative
 * `users.role` column (GET /api/auth/me), rather than guessing from the
 * email domain client-side. While the query is in flight `role` is null
 * and `isLoaded` is false so consumers never flash the wrong lane.
 * `isError` is true once the /me query has failed and settled (retries
 * exhausted), so gates on `isLoaded` can surface a retry affordance
 * instead of an eternal loading state.
 */
export function useRole() {
  const { getToken, isSignedIn } = useAuth();

  const { data, isError } = useQuery({
    queryKey: ["auth", "me"],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<MeResponse>>("/auth/me", {
        token,
      });
      return response.data;
    },
    enabled: isSignedIn === true,
    staleTime: 5 * 60 * 1000,
    retry: (count, error) => {
      if (isAuthError(error)) return false;
      return count < 3;
    },
  });

  const role: Role | null =
    data?.role === "instructor" || data?.role === "student"
      ? data.role
      : null;

  return {
    role,
    isInstructor: role === "instructor",
    isStudent: role === "student",
    isLoaded: role !== null,
    isError,
  } as const;
}
