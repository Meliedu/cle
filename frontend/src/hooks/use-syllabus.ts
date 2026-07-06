"use client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { useAuthedQuery } from "@/hooks/use-authed-query";
import { apiFetch, type ApiEnvelope } from "@/lib/api";

interface SyllabusImportRef {
  readonly id: string;
}

/**
 * Lifecycle of a `syllabus_imports` row (mirrors backend `SyllabusImportStatus`).
 * `pending`/`applying` are in-flight; `parsed` awaits teacher apply; `applied`
 * is the terminal success the setup wizard gates its `syllabus` flag on.
 */
export type SyllabusImportStatus =
  | "pending"
  | "parsed"
  | "applying"
  | "applied"
  | "failed"
  | "superseded";

/** Mirrors `SyllabusImportResponse` (`app/schemas/curriculum.py`). */
export interface SyllabusImport {
  readonly id: string;
  readonly course_id: string;
  readonly document_id: string | null;
  readonly parsed_payload: Record<string, unknown>;
  readonly status: SyllabusImportStatus;
  readonly error_message: string | null;
  readonly applied_at: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export const syllabusKeys = {
  imports: (courseId: string) => ["syllabus-imports", courseId] as const,
};

const IMPORTS_POLL_INTERVAL_MS = 4000;

/**
 * GET `/courses/{id}/syllabus/imports` — every import for the course, newest
 * first. When `poll` is set, refetches while any import is still in-flight
 * (`pending`/`applying`) so the wizard reflects the background parse job.
 */
export function useSyllabusImports(
  courseId: string,
  options: { poll?: boolean } = {}
) {
  const { poll = false } = options;
  return useAuthedQuery<readonly SyllabusImport[]>({
    queryKey: syllabusKeys.imports(courseId),
    path: `/courses/${courseId}/syllabus/imports`,
    enabled: Boolean(courseId),
    refetchInterval: (query) => {
      if (!poll) return false;
      const rows = query.state.data;
      if (!rows) return false;
      const inFlight = rows.some(
        (r) => r.status === "pending" || r.status === "applying"
      );
      return inFlight ? IMPORTS_POLL_INTERVAL_MS : false;
    },
  });
}

export function useTriggerSyllabusImport(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (documentId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<SyllabusImportRef>>(
        `/courses/${courseId}/syllabus/imports`,
        {
          token,
          method: "POST",
          body: JSON.stringify({ document_id: documentId }),
        }
      );
      return res.data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: syllabusKeys.imports(courseId),
      });
    },
  });
}

/**
 * POST `/courses/{id}/syllabus/imports/{importId}/apply` — confirm a parsed
 * import, writing its curriculum into the course. The teacher confirms the
 * parsed payload as-is; the backend transitions the row `parsed → applied` and
 * supersedes any earlier applied import.
 */
export function useApplySyllabusImport(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation<SyllabusImport, Error, SyllabusImport>({
    mutationFn: async (imp) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<SyllabusImport>>(
        `/courses/${courseId}/syllabus/imports/${imp.id}/apply`,
        {
          token,
          method: "POST",
          body: JSON.stringify({ parsed_payload: imp.parsed_payload }),
        }
      );
      return res.data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: syllabusKeys.imports(courseId),
      });
    },
  });
}
