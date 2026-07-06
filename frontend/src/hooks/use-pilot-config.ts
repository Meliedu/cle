"use client";

import { useAuthedQuery } from "@/hooks/use-authed-query";
import type { PilotConfig } from "@/lib/pilot-config";

/**
 * Static per-deployment pilot config from `GET /api/config`. It never changes
 * within a session, so fetch it once and never refetch (`staleTime`/`gcTime`
 * are Infinity). `isLoaded` flips true only once data has arrived so consumers
 * can hold rendering (terminology, confidence scale, readiness) until then.
 */
export function usePilotConfig() {
  const { data, isError } = useAuthedQuery<PilotConfig>({
    queryKey: ["pilot-config"],
    path: "/config",
    staleTime: Infinity,
    gcTime: Infinity,
  });

  return { config: data ?? null, isLoaded: data !== undefined, isError } as const;
}
