"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@clerk/nextjs";
import { apiFetch } from "@/lib/api";

// Types
export interface RecalibrationContentTypeSummary {
  readonly content_type: string;
  readonly items_scanned: number;
  readonly items_relabeled: number;
  readonly relabel_pct: number;
  readonly last_run: string | null;
}

export interface RecalibrationOverview {
  readonly summaries: RecalibrationContentTypeSummary[];
  readonly transition_matrices: Record<string, Record<string, Record<string, number>>>;
}

export interface RecalibrationItemRow {
  readonly pool_item_id: string;
  readonly content_type: string;
  readonly item_preview: string;
  readonly llm_difficulty: string;
  readonly recalibrated_difficulty: string | null;
  readonly confidence: number | null;
  readonly attempt_count: number;
  readonly correct_rate: number;
  readonly instructor_override: boolean;
}

interface ApiEnvelope<T> {
  readonly success: boolean;
  readonly data: T;
}

// Hooks
export function useRecalibrationOverview(courseId: string) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["recalibration", "overview", courseId],
    queryFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<RecalibrationOverview>>(
        `/courses/${courseId}/recalibration/overview`, { token }
      );
      return res.data;
    },
  });
}

export function useRecalibrationItems(
  courseId: string,
  filters: {
    content_type?: string;
    llm_difficulty?: string;
    recalibrated_only?: boolean;
    page?: number;
    limit?: number;
  } = {}
) {
  const { getToken } = useAuth();
  const params = new URLSearchParams();
  if (filters.content_type) params.set("content_type", filters.content_type);
  if (filters.llm_difficulty) params.set("llm_difficulty", filters.llm_difficulty);
  if (filters.recalibrated_only) params.set("recalibrated_only", "true");
  if (filters.page) params.set("page", String(filters.page));
  if (filters.limit) params.set("limit", String(filters.limit));
  const qs = params.toString();

  return useQuery({
    queryKey: ["recalibration", "items", courseId, qs],
    queryFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<{ items: RecalibrationItemRow[] }>>(
        `/courses/${courseId}/recalibration/items?${qs}`, { token }
      );
      return res.data.items;
    },
  });
}

export function useToggleOverride(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (itemId: string) => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return apiFetch<ApiEnvelope<Record<string, unknown>>>(
        `/courses/${courseId}/recalibration/items/${itemId}/override`,
        { method: "POST", token }
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recalibration", "items", courseId] });
      queryClient.invalidateQueries({ queryKey: ["recalibration", "overview", courseId] });
    },
  });
}
