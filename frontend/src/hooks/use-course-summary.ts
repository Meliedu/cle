import { useQuery, useMutation } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, isAuthError, type ApiEnvelope } from "@/lib/api";
import { useGenerationJobs } from "@/hooks/use-generation-jobs";

export interface CourseSummary {
  readonly id: string;
  readonly course_id: string;
  readonly summary_text: string;
  readonly document_ids: readonly string[] | null;
  readonly generated_by: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export function useCourseSummary(courseId: string) {
  const { getToken, isSignedIn } = useAuth();

  return useQuery<CourseSummary | null>({
    queryKey: ["course-summary", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<CourseSummary | null>>(
        `/rag/course-summary/${courseId}`,
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

interface GenerateArgs {
  readonly documentIds?: readonly string[];
}

interface EnqueueSummaryResponse {
  readonly job_id: string;
  readonly kind: "generate_summary";
  readonly course_id: string;
  readonly title: string | null;
}

/**
 * Fire-and-forget summary generation. Returns quickly after the backend
 * enqueues a job; the GenerationJobs provider takes care of polling for
 * completion and invalidating this query's cache.
 */
export function useGenerateCourseSummary(courseId: string) {
  const { getToken } = useAuth();
  const { trackJob } = useGenerationJobs();

  return useMutation<EnqueueSummaryResponse, Error, GenerateArgs>({
    mutationFn: async ({ documentIds }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<EnqueueSummaryResponse>>(
        "/rag/generate-summary",
        {
          method: "POST",
          token,
          body: JSON.stringify({
            course_id: courseId,
            document_ids:
              documentIds && documentIds.length > 0 ? documentIds : undefined,
          }),
        }
      );
      return response.data;
    },
    onSuccess: (data) => {
      trackJob({
        jobId: data.job_id,
        kind: "generate_summary",
        courseId,
        title: null,
      });
    },
  });
}
