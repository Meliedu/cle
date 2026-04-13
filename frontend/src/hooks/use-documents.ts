import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@clerk/nextjs";
import { apiFetch, type ApiEnvelope } from "@/lib/api";

export interface DocumentResponse {
  readonly id: string;
  readonly course_id: string;
  readonly uploaded_by: string;
  readonly filename: string;
  readonly file_type: string;
  readonly file_size: number | null;
  readonly status: string;
  readonly page_count: number | null;
  readonly word_count: number | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export function useDocuments(courseId: string) {
  const { getToken, isSignedIn } = useAuth();

  return useQuery({
    queryKey: ["documents", courseId],
    queryFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<DocumentResponse[]>>(
        `/courses/${courseId}/documents`,
        { token }
      );
      return response.data;
    },
    enabled: isSignedIn === true && !!courseId,
    retry: (count, error) => {
      if (error.message.includes("401") || error.message.includes("Unauthorized")) return false;
      return count < 3;
    },
    refetchInterval: (query) => {
      const docs = query.state.data;
      if (!docs || !Array.isArray(docs)) return false;
      const hasPending = docs.some(
        (doc) => doc.status === "pending" || doc.status === "processing"
      );
      return hasPending ? 10_000 : false;
    },
  });
}

export function useDeleteDocument(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (documentId: string) => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      await apiFetch(`/courses/${courseId}/documents/${documentId}`, {
        method: "DELETE",
        token,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["documents", courseId] });
    },
  });
}
