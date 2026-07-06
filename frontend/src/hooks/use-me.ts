"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/hooks/use-auth";
import { useAuthedQuery } from "@/hooks/use-authed-query";
import { apiFetch, type ApiEnvelope } from "@/lib/api";

/**
 * Shared cache key for the authenticated user's `/auth/me` payload. `useRole`
 * reads the same key, so `useMe` and `useRole` share a single in-flight query
 * and a single cache entry.
 */
export const ME_QUERY_KEY = ["auth", "me"] as const;

/** The five whitelisted notification preference keys (mirror of the backend
 * `NotificationPrefs` schema). Any key outside this set is rejected 422. */
export const NOTIFICATION_PREF_KEYS = [
  "checkpoint_published",
  "report_ready",
  "follow_up_assigned",
  "quiz_due_soon",
  "weekly_summary",
] as const;

export type NotificationPrefKey = (typeof NOTIFICATION_PREF_KEYS)[number];

export type NotificationPrefs = Partial<Record<NotificationPrefKey, boolean>>;

export interface MeResponse {
  readonly id: string;
  readonly better_auth_id: string;
  readonly email: string;
  readonly full_name: string | null;
  readonly role: string;
  readonly avatar_url: string | null;
  readonly notification_prefs: NotificationPrefs;
  readonly created_at: string;
}

/** Reads the authoritative `/auth/me` payload (id, role, notification prefs). */
export function useMe() {
  return useAuthedQuery<MeResponse>({
    queryKey: ME_QUERY_KEY,
    path: "/auth/me",
    staleTime: 5 * 60 * 1000,
  });
}

interface MutationContext {
  readonly previous: MeResponse | undefined;
}

/**
 * PATCH `/auth/me/preferences`, merging the submitted (partial) preference map
 * over the stored one. Applies an optimistic update to the shared `["auth",
 * "me"]` cache, rolls back on error, reconciles with the server response on
 * success, and always revalidates on settle.
 */
export function useUpdateNotificationPrefs() {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation<MeResponse, Error, NotificationPrefs, MutationContext>({
    mutationFn: async (prefs) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<MeResponse>>(
        "/auth/me/preferences",
        {
          method: "PATCH",
          token,
          body: JSON.stringify({ notification_prefs: prefs }),
        },
      );
      return response.data;
    },
    onMutate: async (prefs) => {
      await queryClient.cancelQueries({ queryKey: ME_QUERY_KEY });
      const previous = queryClient.getQueryData<MeResponse>(ME_QUERY_KEY);
      if (previous) {
        queryClient.setQueryData<MeResponse>(ME_QUERY_KEY, {
          ...previous,
          notification_prefs: { ...previous.notification_prefs, ...prefs },
        });
      }
      return { previous };
    },
    onError: (_error, _prefs, context) => {
      if (context?.previous) {
        queryClient.setQueryData(ME_QUERY_KEY, context.previous);
      }
    },
    onSuccess: (data) => {
      queryClient.setQueryData(ME_QUERY_KEY, data);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY });
    },
  });
}
