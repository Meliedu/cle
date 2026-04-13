import { useQuery, useMutation } from "@tanstack/react-query";
import { useAuth } from "@clerk/nextjs";
import { apiFetch, isAuthError } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

// --- Response types ---

export interface WordScore {
  readonly word: string;
  readonly accuracy: number;
  readonly error_type: string | null;
}

export interface PronunciationGradeResponse {
  readonly id: string;
  readonly overall_score: number;
  readonly accuracy_score: number;
  readonly fluency_score: number;
  readonly completeness_score: number;
  readonly prosody_score: number | null;
  readonly word_scores: readonly WordScore[];
  readonly provider: string;
}

export interface PronunciationHistoryEntry {
  readonly id: string;
  readonly target_text: string;
  readonly overall_score: number;
  readonly accuracy_score: number;
  readonly fluency_score: number;
  readonly created_at: string;
}

interface ApiEnvelope<T> {
  readonly success: boolean;
  readonly data: T;
}

// --- Mutation input ---

interface GradeInput {
  readonly audioBlob: Blob;
  readonly referenceText: string;
  readonly courseId: string;
  readonly language: string;
}

// --- Hooks ---

export function usePronunciationGrade() {
  const { getToken } = useAuth();

  return useMutation({
    mutationFn: async ({
      audioBlob,
      referenceText,
      courseId,
      language,
    }: GradeInput): Promise<PronunciationGradeResponse> => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");

      const formData = new FormData();
      formData.append("audio", audioBlob, "recording.wav");
      formData.append("reference_text", referenceText);
      formData.append("course_id", courseId);
      formData.append("language", language);

      const response = await fetch(`${API_URL}/speech/grade`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!response.ok) {
        const error = await response
          .json()
          .catch(() => ({ error: { message: "Grading failed" } }));
        throw new Error(
          error.error?.message || `HTTP ${response.status}`
        );
      }

      const envelope: ApiEnvelope<PronunciationGradeResponse> =
        await response.json();
      return envelope.data;
    },
  });
}

export function usePronunciationHistory(courseId: string) {
  const { getToken, isSignedIn } = useAuth();

  return useQuery({
    queryKey: ["pronunciation-history", courseId],
    queryFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<
        ApiEnvelope<PronunciationHistoryEntry[]>
      >(`/speech/courses/${courseId}/pronunciation-history`, { token });
      return response.data;
    },
    enabled: isSignedIn === true && !!courseId,
    retry: (count, error) => {
      if (
        isAuthError(error)
      )
        return false;
      return count < 3;
    },
  });
}
