import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@clerk/nextjs";
import { apiFetch, isAuthError, type ApiEnvelope } from "@/lib/api";

export interface QuizFolder {
  readonly id: string;
  readonly course_id: string;
  readonly name: string;
  readonly parent_id: string | null;
  readonly created_at: string;
}

export function useQuizFolders(courseId: string) {
  const { getToken, isSignedIn } = useAuth();
  return useQuery({
    queryKey: ["quiz-folders", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<QuizFolder[]>>(
        `/courses/${courseId}/quiz-folders`,
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

function invalidateFolders(qc: ReturnType<typeof useQueryClient>, courseId: string) {
  qc.invalidateQueries({ queryKey: ["quiz-folders", courseId] });
  qc.invalidateQueries({ queryKey: ["quizzes", courseId, "live"] });
  qc.invalidateQueries({ queryKey: ["quizzes", courseId, "all"] });
}

export function useCreateQuizFolder(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { name: string; parent_id?: string | null }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<QuizFolder>>(
        `/courses/${courseId}/quiz-folders`,
        { token, method: "POST", body: JSON.stringify(input) }
      );
      return response.data;
    },
    onSuccess: () => invalidateFolders(qc, courseId),
  });
}

export function useRenameQuizFolder(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { folder_id: string; name: string }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<QuizFolder>>(
        `/quiz-folders/${input.folder_id}`,
        {
          token,
          method: "PATCH",
          body: JSON.stringify({ name: input.name }),
        }
      );
      return response.data;
    },
    onSuccess: () => invalidateFolders(qc, courseId),
  });
}

export function useMoveQuizFolder(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      folder_id: string;
      parent_id: string | null;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<QuizFolder>>(
        `/quiz-folders/${input.folder_id}/move`,
        {
          token,
          method: "POST",
          body: JSON.stringify({ parent_id: input.parent_id }),
        }
      );
      return response.data;
    },
    onSuccess: () => invalidateFolders(qc, courseId),
  });
}

export function useDeleteQuizFolder(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (folderId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await apiFetch<void>(`/quiz-folders/${folderId}`, {
        token,
        method: "DELETE",
      });
    },
    onSuccess: () => invalidateFolders(qc, courseId),
  });
}

export function useMoveQuizToFolder(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      quiz_id: string;
      folder_id: string | null;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await apiFetch<ApiEnvelope<unknown>>(
        `/quizzes/${input.quiz_id}/folder`,
        {
          token,
          method: "PATCH",
          body: JSON.stringify({ folder_id: input.folder_id }),
        }
      );
    },
    onSuccess: () => invalidateFolders(qc, courseId),
  });
}
