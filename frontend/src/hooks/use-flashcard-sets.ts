import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, isAuthError, type ApiEnvelope } from "@/lib/api";

export interface FlashcardCardResponse {
  readonly id: string;
  readonly card_index: number;
  readonly front: string;
  readonly back: string;
  readonly difficulty?: string;
  readonly created_at: string;
}

export interface FlashcardSetResponse {
  readonly id: string;
  readonly course_id: string;
  readonly title: string;
  readonly is_published: boolean;
  readonly folder_id: string | null;
  readonly card_count: number;
  readonly created_at: string;
}

export interface FlashcardSetDetailResponse {
  readonly id: string;
  readonly course_id: string;
  readonly title: string;
  readonly cards: readonly FlashcardCardResponse[];
  readonly created_at: string;
}

export function useFlashcardSets(courseId: string) {
  const { getToken, isSignedIn } = useAuth();

  return useQuery({
    queryKey: ["flashcard-sets", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<FlashcardSetResponse[]>>(
        `/courses/${courseId}/flashcard-sets`,
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

function invalidateFcDetail(
  qc: ReturnType<typeof useQueryClient>,
  courseId: string,
  setId: string
) {
  qc.invalidateQueries({ queryKey: ["flashcard-sets", "detail", setId] });
  qc.invalidateQueries({ queryKey: ["flashcard-set", setId] });
  qc.invalidateQueries({ queryKey: ["flashcard-sets", courseId] });
}

export function useAddFlashcardCard(courseId: string, setId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      front: string;
      back: string;
      difficulty?: string;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<FlashcardCardResponse>>(
        `/flashcard-sets/${setId}/cards`,
        { token, method: "POST", body: JSON.stringify(input) }
      );
      return response.data;
    },
    onSuccess: () => invalidateFcDetail(qc, courseId, setId),
  });
}

export function useUpdateFlashcardCard(courseId: string, setId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      card_id: string;
      front?: string;
      back?: string;
      difficulty?: string;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const { card_id, ...patch } = input;
      const response = await apiFetch<ApiEnvelope<FlashcardCardResponse>>(
        `/flashcard-cards/${card_id}`,
        { token, method: "PATCH", body: JSON.stringify(patch) }
      );
      return response.data;
    },
    onSuccess: () => invalidateFcDetail(qc, courseId, setId),
  });
}

export function useDeleteFlashcardCard(courseId: string, setId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (cardId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await apiFetch<ApiEnvelope<null>>(`/flashcard-cards/${cardId}`, {
        token,
        method: "DELETE",
      });
    },
    onSuccess: () => invalidateFcDetail(qc, courseId, setId),
  });
}

export function useRegenerateFlashcardCard(courseId: string, setId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (cardId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<FlashcardCardResponse>>(
        `/flashcard-cards/${cardId}/regenerate`,
        { token, method: "POST" }
      );
      return response.data;
    },
    onSuccess: () => invalidateFcDetail(qc, courseId, setId),
  });
}

export function useFlashcardSet(setId: string) {
  const { getToken, isSignedIn } = useAuth();

  return useQuery({
    queryKey: ["flashcard-sets", "detail", setId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<FlashcardSetDetailResponse>>(
        `/flashcard-sets/${setId}`,
        { token }
      );
      return response.data;
    },
    enabled: isSignedIn === true && !!setId,
    retry: (count, error) => {
      if (isAuthError(error)) return false;
      return count < 3;
    },
  });
}
