import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@clerk/nextjs";
import { apiFetch, isAuthError, type ApiEnvelope } from "@/lib/api";

export type QuizPurpose = "after_class" | "live";

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
  readonly purpose: QuizPurpose;
  readonly folder_id: string | null;
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

export function useQuizzes(courseId: string, purpose?: QuizPurpose) {
  const { getToken, isSignedIn } = useAuth();

  return useQuery({
    queryKey: ["quizzes", courseId, purpose ?? "all"],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const qs = purpose ? `?purpose=${purpose}` : "";
      const response = await apiFetch<ApiEnvelope<QuizResponse[]>>(
        `/courses/${courseId}/quizzes${qs}`,
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

export interface ImportToLiveInput {
  readonly source_quiz_id: string;
  readonly question_ids: string[];
  readonly title: string;
}

export interface UpdateQuizInput {
  readonly quiz_id: string;
  readonly title?: string;
  readonly description?: string;
}

export function useUpdateQuiz(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();

  return useMutation({
    mutationFn: async (input: UpdateQuizInput) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const { quiz_id, ...body } = input;
      const response = await apiFetch<ApiEnvelope<QuizResponse>>(
        `/quizzes/${quiz_id}`,
        {
          token,
          method: "PUT",
          body: JSON.stringify(body),
        }
      );
      return response.data;
    },
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["quizzes", courseId, "live"] });
      qc.invalidateQueries({ queryKey: ["quizzes", courseId, "after_class"] });
      qc.invalidateQueries({ queryKey: ["quizzes", courseId, "all"] });
      qc.invalidateQueries({
        queryKey: ["quizzes", "detail", variables.quiz_id],
      });
    },
  });
}

export function useDeleteQuiz(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();

  return useMutation({
    mutationFn: async (quizId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await apiFetch<ApiEnvelope<null>>(`/quizzes/${quizId}`, {
        token,
        method: "DELETE",
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["quizzes", courseId, "live"] });
      qc.invalidateQueries({ queryKey: ["quizzes", courseId, "after_class"] });
      qc.invalidateQueries({ queryKey: ["quizzes", courseId, "all"] });
    },
  });
}

export function useImportQuestionsToLive(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();

  return useMutation({
    mutationFn: async (input: ImportToLiveInput) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<QuizResponse>>(
        `/courses/${courseId}/quizzes/import-to-live`,
        { token, method: "POST", body: JSON.stringify(input) }
      );
      return response.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["quizzes", courseId, "live"] });
      qc.invalidateQueries({ queryKey: ["quizzes", courseId, "all"] });
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
