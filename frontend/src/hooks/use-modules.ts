"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type { CourseModule } from "@/lib/curriculum-types";

export function useModules(courseId: string) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["modules", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<CourseModule[]>>(
        `/courses/${courseId}/modules`,
        { token }
      );
      return res.data;
    },
  });
}

export function useCreateModule(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: {
      name: string;
      order_index: number;
      description?: string;
      parent_id?: string;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<CourseModule>>(
        `/courses/${courseId}/modules`,
        { token, method: "POST", body: JSON.stringify(body) }
      );
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["modules", courseId] }),
  });
}

export function useUpdateModule(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: {
      moduleId: string;
      patch: Partial<CourseModule>;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<CourseModule>>(
        `/courses/${courseId}/modules/${vars.moduleId}`,
        { token, method: "PUT", body: JSON.stringify(vars.patch) }
      );
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["modules", courseId] }),
  });
}

export function useDeleteModule(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (moduleId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await apiFetch<ApiEnvelope<null>>(
        `/courses/${courseId}/modules/${moduleId}`,
        { token, method: "DELETE" }
      );
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["modules", courseId] }),
  });
}
