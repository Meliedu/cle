import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, isAuthError, type ApiEnvelope } from "@/lib/api";

export type PronunciationItemType = "word" | "phrase" | "sentence";

export interface PronunciationItemResponse {
  readonly id: string;
  readonly item_index: number;
  readonly text: string;
  readonly phonetic: string | null;
  readonly translation: string | null;
  readonly tips: string | null;
  readonly item_type: PronunciationItemType;
  readonly difficulty: string;
  readonly created_at: string;
}

export interface PronunciationSetResponse {
  readonly id: string;
  readonly course_id: string;
  readonly title: string;
  readonly is_published: boolean;
  readonly difficulty: string;
  readonly language: string;
  readonly folder_id: string | null;
  readonly item_count: number;
  readonly created_at: string;
}

export interface PronunciationSetDetailResponse {
  readonly id: string;
  readonly course_id: string;
  readonly title: string;
  readonly is_published: boolean;
  readonly difficulty: string;
  readonly language: string;
  readonly folder_id: string | null;
  readonly items: readonly PronunciationItemResponse[];
  readonly created_at: string;
}

export function usePronunciationSets(courseId: string) {
  const { getToken, isSignedIn } = useAuth();

  return useQuery({
    queryKey: ["pronunciation-sets", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<PronunciationSetResponse[]>>(
        `/courses/${courseId}/pronunciation-sets`,
        { token }
      );
      return response.data;
    },
    enabled: isSignedIn === true && !!courseId,
    retry: (count, error) => {
      if (isAuthError(error)) return false;
      return count < 3;
    },
  });
}

export function usePronunciationSet(setId: string) {
  const { getToken, isSignedIn } = useAuth();

  return useQuery({
    queryKey: ["pronunciation-sets", "detail", setId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<
        ApiEnvelope<PronunciationSetDetailResponse>
      >(`/pronunciation-sets/${setId}`, { token });
      return response.data;
    },
    enabled: isSignedIn === true && !!setId,
    retry: (count, error) => {
      if (isAuthError(error)) return false;
      return count < 3;
    },
  });
}

function invalidateSetCaches(
  qc: ReturnType<typeof useQueryClient>,
  courseId: string,
  setId?: string
) {
  qc.invalidateQueries({ queryKey: ["pronunciation-sets", courseId] });
  if (setId) {
    qc.invalidateQueries({
      queryKey: ["pronunciation-sets", "detail", setId],
    });
  }
}

export function usePublishPronunciationSet(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (setId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<PronunciationSetResponse>>(
        `/pronunciation-sets/${setId}/publish`,
        { method: "POST", token }
      );
      return response.data;
    },
    onSuccess: (data) => invalidateSetCaches(qc, courseId, data.id),
  });
}

export function useDeletePronunciationSet(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (setId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await apiFetch<ApiEnvelope<null>>(`/pronunciation-sets/${setId}`, {
        method: "DELETE",
        token,
      });
    },
    onSuccess: () => invalidateSetCaches(qc, courseId),
  });
}

export function useUpdatePronunciationSet(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { set_id: string; title: string }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<PronunciationSetResponse>>(
        `/pronunciation-sets/${input.set_id}`,
        {
          method: "PATCH",
          token,
          body: JSON.stringify({ title: input.title }),
        }
      );
      return response.data;
    },
    onSuccess: (data) => invalidateSetCaches(qc, courseId, data.id),
  });
}

function invalidateDetail(
  qc: ReturnType<typeof useQueryClient>,
  courseId: string,
  setId: string
) {
  qc.invalidateQueries({ queryKey: ["pronunciation-sets", "detail", setId] });
  qc.invalidateQueries({ queryKey: ["pronunciation-sets", courseId] });
}

export function useAddPronunciationItem(courseId: string, setId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      text: string;
      item_type: "word" | "phrase" | "sentence";
      phonetic?: string | null;
      translation?: string | null;
      tips?: string | null;
      difficulty?: string;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<PronunciationItemResponse>>(
        `/pronunciation-sets/${setId}/items`,
        { token, method: "POST", body: JSON.stringify(input) }
      );
      return response.data;
    },
    onSuccess: () => invalidateDetail(qc, courseId, setId),
  });
}

export function useUpdatePronunciationItem(courseId: string, setId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      item_id: string;
      text?: string;
      item_type?: "word" | "phrase" | "sentence";
      phonetic?: string | null;
      translation?: string | null;
      tips?: string | null;
      difficulty?: string;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const { item_id, ...patch } = input;
      const response = await apiFetch<ApiEnvelope<PronunciationItemResponse>>(
        `/pronunciation-items/${item_id}`,
        { token, method: "PATCH", body: JSON.stringify(patch) }
      );
      return response.data;
    },
    onSuccess: () => invalidateDetail(qc, courseId, setId),
  });
}

export function useDeletePronunciationItem(courseId: string, setId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (itemId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await apiFetch<ApiEnvelope<null>>(
        `/pronunciation-items/${itemId}`,
        { token, method: "DELETE" }
      );
    },
    onSuccess: () => invalidateDetail(qc, courseId, setId),
  });
}

export function useRegeneratePronunciationItem(
  courseId: string,
  setId: string
) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (itemId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<PronunciationItemResponse>>(
        `/pronunciation-items/${itemId}/regenerate`,
        { token, method: "POST" }
      );
      return response.data;
    },
    onSuccess: () => invalidateDetail(qc, courseId, setId),
  });
}

export function useMovePronunciationSetToFolder(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      set_id: string;
      folder_id: string | null;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await apiFetch<ApiEnvelope<unknown>>(
        `/pronunciation-sets/${input.set_id}/folder`,
        {
          token,
          method: "PATCH",
          body: JSON.stringify({ folder_id: input.folder_id }),
        }
      );
    },
    onSuccess: () => invalidateSetCaches(qc, courseId),
  });
}
