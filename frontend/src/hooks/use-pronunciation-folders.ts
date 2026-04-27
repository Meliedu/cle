import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, isAuthError, type ApiEnvelope } from "@/lib/api";

export interface PronunciationFolder {
  readonly id: string;
  readonly course_id: string;
  readonly name: string;
  readonly parent_id: string | null;
  readonly created_at: string;
}

export function usePronunciationFolders(courseId: string) {
  const { getToken, isSignedIn } = useAuth();
  return useQuery({
    queryKey: ["pronunciation-folders", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<PronunciationFolder[]>>(
        `/courses/${courseId}/pronunciation-folders`,
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
  qc.invalidateQueries({ queryKey: ["pronunciation-folders", courseId] });
  qc.invalidateQueries({ queryKey: ["pronunciation-sets", courseId] });
}

export function useCreatePronunciationFolder(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      name: string;
      parent_id?: string | null;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<PronunciationFolder>>(
        `/courses/${courseId}/pronunciation-folders`,
        { token, method: "POST", body: JSON.stringify(input) }
      );
      return response.data;
    },
    onSuccess: () => invalidate(qc, courseId),
  });
}

export function useRenamePronunciationFolder(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { folder_id: string; name: string }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<PronunciationFolder>>(
        `/pronunciation-folders/${input.folder_id}`,
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

export function useMovePronunciationFolder(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      folder_id: string;
      parent_id: string | null;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<PronunciationFolder>>(
        `/pronunciation-folders/${input.folder_id}/move`,
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

export function useDeletePronunciationFolder(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (folderId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await apiFetch<ApiEnvelope<null>>(
        `/pronunciation-folders/${folderId}`,
        { token, method: "DELETE" }
      );
    },
    onSuccess: () => invalidate(qc, courseId),
  });
}
