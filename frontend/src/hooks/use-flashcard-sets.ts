import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@clerk/nextjs";
import { apiFetch, isAuthError, type ApiEnvelope } from "@/lib/api";

export interface FlashcardCardResponse {
  readonly id: string;
  readonly card_index: number;
  readonly front: string;
  readonly back: string;
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
