import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, isAuthError, type ApiEnvelope } from "@/lib/api";

export interface FlashcardFolder {
  readonly id: string;
  readonly course_id: string;
  readonly name: string;
  readonly parent_id: string | null;
  readonly created_at: string;
}

export function useFlashcardFolders(courseId: string) {
  const { getToken, isSignedIn } = useAuth();
  return useQuery({
    queryKey: ["flashcard-folders", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<FlashcardFolder[]>>(
        `/courses/${courseId}/flashcard-folders`,
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

function invalidate(
  qc: ReturnType<typeof useQueryClient>,
  courseId: string
) {
  qc.invalidateQueries({ queryKey: ["flashcard-folders", courseId] });
  qc.invalidateQueries({ queryKey: ["flashcard-sets", courseId] });
}

export function useCreateFlashcardFolder(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      name: string;
      parent_id?: string | null;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<FlashcardFolder>>(
        `/courses/${courseId}/flashcard-folders`,
        { token, method: "POST", body: JSON.stringify(input) }
      );
      return response.data;
    },
    onSuccess: () => invalidate(qc, courseId),
  });
}

export function useRenameFlashcardFolder(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { folder_id: string; name: string }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<FlashcardFolder>>(
        `/flashcard-folders/${input.folder_id}`,
        {
          token,
          method: "PATCH",
          body: JSON.stringify({ name: input.name }),
        }
      );
      return response.data;
    },
    onSuccess: () => invalidate(qc, courseId),
  });
}

export function useMoveFlashcardFolder(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      folder_id: string;
      parent_id: string | null;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<FlashcardFolder>>(
        `/flashcard-folders/${input.folder_id}/move`,
        {
          token,
          method: "POST",
          body: JSON.stringify({ parent_id: input.parent_id }),
        }
      );
      return response.data;
    },
    onSuccess: () => invalidate(qc, courseId),
  });
}

export function useDeleteFlashcardFolder(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (folderId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await apiFetch<ApiEnvelope<null>>(`/flashcard-folders/${folderId}`, {
        token,
        method: "DELETE",
      });
    },
    onSuccess: () => invalidate(qc, courseId),
  });
}

export function useMoveFlashcardSetToFolder(courseId: string) {
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
        `/flashcard-sets/${input.set_id}/folder`,
        {
          token,
          method: "PATCH",
          body: JSON.stringify({ folder_id: input.folder_id }),
        }
      );
    },
    onSuccess: () => invalidate(qc, courseId),
  });
}
