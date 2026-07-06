import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, isAuthError, type ApiEnvelope } from "@/lib/api";

export interface CourseResponse {
  readonly id: string;
  readonly name: string;
  readonly code: string | null;
  readonly description: string | null;
  readonly language: string;
  readonly semester: string | null;
  readonly instructor_id: string;
  readonly enroll_code: string;
  readonly enroll_code_active: boolean;
  readonly settings: Record<string, unknown>;
  readonly setup_status: string;
  readonly setup_checklist: Record<string, boolean>;
  readonly join_mode: string;
  readonly context_status: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export function useCourses() {
  const { getToken, isSignedIn } = useAuth();

  return useQuery({
    queryKey: ["courses"],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<CourseResponse[]>>(
        "/courses",
        { token }
      );
      return response.data;
    },
    enabled: isSignedIn === true,
    retry: (count, error) => {
      if (isAuthError(error)) return false;
      return count < 3;
    },
  });
}

export function useEnrollByCode() {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (enrollCode: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<CourseResponse>>(
        "/courses/enroll-by-code",
        {
          method: "POST",
          token,
          body: JSON.stringify({ enroll_code: enrollCode }),
        }
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["courses"] });
    },
  });
}

export interface CourseCreatePayload {
  readonly name: string;
  readonly code?: string | null;
  readonly description?: string | null;
  readonly language: string;
  readonly semester?: string | null;
  readonly settings?: Record<string, unknown>;
}

/**
 * POST `/courses` — create a course and return the persisted row so the caller
 * can route into the setup wizard (`/teacher/courses/{id}/setup`). Invalidates
 * the course list so it reflects the new draft.
 */
export function useCreateCourse() {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: CourseCreatePayload) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<CourseResponse>>("/courses", {
        method: "POST",
        token,
        body: JSON.stringify({ settings: {}, ...payload }),
      });
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["courses"] });
    },
  });
}

export function useCourse(courseId: string) {
  const { getToken, isSignedIn } = useAuth();

  return useQuery({
    queryKey: ["courses", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<CourseResponse>>(
        `/courses/${courseId}`,
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

/**
 * POST `/courses/{id}/enroll-code/rotate` — mint a fresh join code and
 * reactivate joining (T025 class-code step). Writes the returned course row
 * back into the caches so the revealed code updates immediately.
 */
export function useRotateEnrollCode(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation<CourseResponse, Error, void>({
    mutationFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<CourseResponse>>(
        `/courses/${courseId}/enroll-code/rotate`,
        { method: "POST", token }
      );
      return response.data;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(["courses", courseId], data);
      queryClient.invalidateQueries({ queryKey: ["courses"] });
    },
  });
}

/**
 * POST `/courses/{id}/enroll-code/deactivate` — stop accepting joins on the
 * current code without discarding it (T025 class-code step).
 */
export function useDeactivateEnrollCode(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation<CourseResponse, Error, void>({
    mutationFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<CourseResponse>>(
        `/courses/${courseId}/enroll-code/deactivate`,
        { method: "POST", token }
      );
      return response.data;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(["courses", courseId], data);
      queryClient.invalidateQueries({ queryKey: ["courses"] });
    },
  });
}

export interface CourseUpdatePayload {
  readonly name?: string;
  readonly code?: string | null;
  readonly description?: string | null;
  readonly language?: string;
  readonly semester?: string | null;
  readonly settings?: Record<string, unknown>;
}

export function useUpdateCourse(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: CourseUpdatePayload) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<CourseResponse>>(
        `/courses/${courseId}`,
        {
          method: "PUT",
          token,
          body: JSON.stringify(payload),
        }
      );
      return response.data;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(["courses", courseId], data);
      queryClient.invalidateQueries({ queryKey: ["courses"] });
    },
  });
}
