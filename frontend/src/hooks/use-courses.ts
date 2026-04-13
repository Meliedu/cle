import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@clerk/nextjs";
import { apiFetch, type ApiEnvelope } from "@/lib/api";

export interface CourseResponse {
  readonly id: string;
  readonly name: string;
  readonly code: string | null;
  readonly description: string | null;
  readonly language: string;
  readonly semester: string | null;
  readonly instructor_id: string;
  readonly settings: Record<string, unknown>;
  readonly created_at: string;
  readonly updated_at: string;
}

export function useCourses() {
  const { getToken, isSignedIn } = useAuth();

  return useQuery({
    queryKey: ["courses"],
    queryFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<CourseResponse[]>>(
        "/courses",
        { token }
      );
      return response.data;
    },
    enabled: isSignedIn === true,
    retry: (count, error) => {
      if (error.message.includes("401") || error.message.includes("Unauthorized")) return false;
      return count < 3;
    },
  });
}

export function useCourse(courseId: string) {
  const { getToken, isSignedIn } = useAuth();

  return useQuery({
    queryKey: ["courses", courseId],
    queryFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<CourseResponse>>(
        `/courses/${courseId}`,
        { token }
      );
      return response.data;
    },
    enabled: isSignedIn === true && !!courseId,
    retry: (count, error) => {
      if (error.message.includes("401") || error.message.includes("Unauthorized")) return false;
      return count < 3;
    },
  });
}
