import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { useAuthedQuery } from "@/hooks/use-authed-query";
import { apiFetch, isAuthError, type ApiEnvelope } from "@/lib/api";

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
  /** The `course_meetings` session this material is assigned to, or `null` (P4 B8). */
  readonly meeting_id: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export function useDocuments(courseId: string) {
  const { getToken, isSignedIn } = useAuth();

  return useQuery({
    queryKey: ["documents", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<DocumentResponse[]>>(
        `/courses/${courseId}/documents`,
        { token }
      );
      return response.data;
    },
    enabled: isSignedIn === true && !!courseId,
    retry: (count, error) => {
      if (isAuthError(error)) return false;
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
      const token = await getToken({ template: "backend" });
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

/* ================================================================== */
/*  P4 B8 — materials library: session folders, assign-to-session,    */
/*  signed preview. Mirrors backend `documents.py` materials handlers. */
/* ================================================================== */

/** One session folder in the materials library (documents grouped by meeting). */
export interface MaterialsSessionGroup {
  readonly meeting_id: string;
  readonly meeting_index: number;
  readonly title: string;
  readonly release_state: string;
  readonly documents: readonly DocumentResponse[];
}

/** Mirrors `MaterialsLibrary` — session folders + an "unassigned" bucket (B8). */
export interface MaterialsLibrary {
  readonly sessions: readonly MaterialsSessionGroup[];
  readonly unassigned: readonly DocumentResponse[];
}

/** Mirrors the signed-preview payload — a short-lived R2 URL (expires in 300s). */
export interface MaterialPreview {
  readonly url: string;
  readonly expires_in: number;
  readonly filename: string;
  readonly file_type: string;
}

export const materialsKeys = {
  library: (courseId: string) => ["materials", courseId] as const,
  preview: (courseId: string, docId: string) =>
    ["material-preview", courseId, docId] as const,
};

/**
 * GET `/courses/{id}/materials` — documents grouped into session folders (by
 * `meeting_id`, each carrying its `release_state`) plus an "unassigned" bucket
 * (Decision 6). Owner or enrolled student.
 */
export function useMaterials(courseId: string) {
  return useAuthedQuery<MaterialsLibrary>({
    queryKey: materialsKeys.library(courseId),
    path: `/courses/${courseId}/materials`,
    enabled: Boolean(courseId),
  });
}

/**
 * PATCH `/courses/{id}/documents/{docId}` — assign a material to a session
 * (`meeting_id`) or unassign it (`null`), owner-guarded. A foreign meeting is a
 * typed 404 `MEETING_NOT_FOUND`. Invalidates the materials library, the raw
 * document list, and the calendar (assigning a released session may add a
 * `material` work_item event).
 */
export function useAssignMaterial(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation<
    DocumentResponse,
    Error,
    { documentId: string; meeting_id: string | null }
  >({
    mutationFn: async ({ documentId, meeting_id }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<DocumentResponse>>(
        `/courses/${courseId}/documents/${documentId}`,
        { method: "PATCH", token, body: JSON.stringify({ meeting_id }) }
      );
      return res.data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: materialsKeys.library(courseId),
      });
      void queryClient.invalidateQueries({ queryKey: ["documents", courseId] });
      void queryClient.invalidateQueries({ queryKey: ["calendar", courseId] });
    },
  });
}

/**
 * GET `/courses/{id}/documents/{docId}/preview` — a short-lived signed R2 URL
 * for the reader (owner or enrolled student on a released session). Student
 * errors carry typed codes: 403 `MATERIAL_NOT_RELEASED`, 403 not-enrolled, 404.
 * Disabled until both ids are set (and while `enabled` is explicitly false), so
 * the reader can fetch the URL only when the viewer is actually open.
 */
export function useMaterialPreview(
  courseId: string,
  docId: string | null,
  enabled = true
) {
  return useAuthedQuery<MaterialPreview>({
    queryKey: materialsKeys.preview(courseId, docId ?? ""),
    path: `/courses/${courseId}/documents/${docId}/preview`,
    enabled: enabled && Boolean(courseId && docId),
  });
}
