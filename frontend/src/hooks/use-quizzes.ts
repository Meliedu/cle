import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@clerk/nextjs";
import { apiFetch, isAuthError, type ApiEnvelope } from "@/lib/api";

export interface QuestionResponse {
  readonly id: string;
  readonly question_index: number;
  readonly type: string;
  readonly question_text: string;
  readonly options: Record<string, string> | null;
  readonly correct_answer?: string;
  readonly explanation: string | null;
}

export interface QuizResponse {
  readonly id: string;
  readonly course_id: string;
  readonly title: string;
  readonly description: string | null;
  readonly quiz_type: string;
  readonly is_published: boolean;
  readonly question_count: number;
  readonly created_at: string;
}

export interface QuizDetailResponse {
  readonly id: string;
  readonly course_id: string;
  readonly title: string;
  readonly description: string | null;
  readonly quiz_type: string;
  readonly is_published: boolean;
  readonly questions: readonly QuestionResponse[];
  readonly created_at: string;
}

export function useQuizzes(courseId: string) {
  const { getToken, isSignedIn } = useAuth();

  return useQuery({
    queryKey: ["quizzes", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<QuizResponse[]>>(
        `/courses/${courseId}/quizzes`,
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

export function useQuiz(quizId: string) {
  const { getToken, isSignedIn } = useAuth();

  return useQuery({
    queryKey: ["quizzes", "detail", quizId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<QuizDetailResponse>>(
        `/quizzes/${quizId}`,
        { token }
      );
      return response.data;
    },
    enabled: isSignedIn === true && !!quizId,
    retry: (count, error) => {
      if (isAuthError(error)) return false;
      return count < 3;
    },
  });
}
