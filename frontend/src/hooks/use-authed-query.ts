"use client";

import { useQuery, type UseQueryOptions } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, isAuthError, type ApiEnvelope } from "@/lib/api";

type AuthedQueryOptions<T> = Omit<
  UseQueryOptions<T>,
  "queryKey" | "queryFn"
> & {
  queryKey: readonly unknown[];
  path: string;
};

/**
 * Shared wiring for authenticated GET queries that return the standard
 * `ApiEnvelope<T>`: fetch a fresh backend JWT, throw on a missing token,
 * unwrap `.data`, and apply the two auth guards every data hook needs —
 * `enabled` waits for a signed-in session and `retry` never retries auth
 * failures (401/403). Caller-supplied `enabled`/`retry` compose with those
 * guards rather than replacing them.
 */
export function useAuthedQuery<T>({
  queryKey,
  path,
  enabled,
  retry,
  ...options
}: AuthedQueryOptions<T>) {
  const { getToken, isSignedIn } = useAuth();

  return useQuery<T>({
    ...options,
    queryKey,
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<T>>(path, { token });
      return response.data;
    },
    // Compose with the auth guard: the query only runs once signed in, and
    // additionally honors an explicit `enabled: false` from the caller.
    enabled: isSignedIn === true && enabled !== false,
    // Compose with the auth guard: auth failures never retry; otherwise defer
    // to the caller's retry policy, falling back to the default of 3 attempts.
    retry: (count, error) => {
      if (isAuthError(error)) return false;
      if (typeof retry === "function") return retry(count, error);
      if (typeof retry === "boolean") return retry;
      if (typeof retry === "number") return count < retry;
      return count < 3;
    },
  });
}
