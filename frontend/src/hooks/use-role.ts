"use client";

import { useAuthedQuery } from "@/hooks/use-authed-query";
import { ME_QUERY_KEY } from "@/hooks/use-me";

export type Role = "instructor" | "student";

/** Landing page for a role's lane — single source of truth for lane redirects. */
export function roleHomePath(role: Role): string {
  return role === "instructor" ? "/teacher/dashboard" : "/student/dashboard";
}

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
  const { data, isError } = useAuthedQuery<MeResponse>({
    queryKey: ME_QUERY_KEY,
    path: "/auth/me",
    staleTime: 5 * 60 * 1000,
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
