import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@clerk/nextjs";
import { isAuthError } from "@/lib/api";
import {
  disconnectCanvas,
  getCanvasConnection,
  importCanvasFiles,
  importCanvasRoster,
  joinCanvasCourse,
  linkCanvasCourse,
  listCanvasCourses,
  listCanvasFiles,
  listCanvasSyncEvents,
  runCanvasSync,
  startCanvasOAuth,
  type CanvasConnection,
  type CanvasCourseListing,
  type CanvasFileImportResult,
  type CanvasFileListing,
  type CanvasJoinResult,
  type CanvasLinkResult,
  type CanvasOAuthStart,
  type CanvasRosterImportResult,
  type CanvasSyncEvent,
} from "@/lib/canvas-api";

// ---------- Query keys ----------

export const canvasKeys = {
  connection: ["canvas", "connection"] as const,
  courses: (role: "student" | "teacher") =>
    ["canvas", "courses", role] as const,
  files: (courseId: string) => ["canvas", "files", courseId] as const,
  syncEvents: (courseId: string) =>
    ["canvas", "sync-events", courseId] as const,
};

// ---------- Connection ----------

export function useCanvasConnection() {
  const { getToken, isSignedIn } = useAuth();

  return useQuery<CanvasConnection>({
    queryKey: canvasKeys.connection,
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      return getCanvasConnection(token);
    },
    enabled: isSignedIn === true,
    retry: (count, error) => {
      if (isAuthError(error)) return false;
      return count < 3;
    },
  });
}

export function useStartCanvasOAuth() {
  const { getToken } = useAuth();

  return useMutation<CanvasOAuthStart, Error, void>({
    mutationFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      return startCanvasOAuth(token);
    },
  });
}

export function useDisconnectCanvas() {
  const { getToken } = useAuth();
  const qc = useQueryClient();

  return useMutation<void, Error, void>({
    mutationFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await disconnectCanvas(token);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["canvas"] });
    },
  });
}

// ---------- Course listings ----------

export function useCanvasCourses(role: "student" | "teacher", enabled = true) {
  const { getToken, isSignedIn } = useAuth();

  return useQuery<readonly CanvasCourseListing[]>({
    queryKey: canvasKeys.courses(role),
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      return listCanvasCourses(token, role);
    },
    enabled: isSignedIn === true && enabled,
    retry: (count, error) => {
      if (isAuthError(error)) return false;
      return count < 3;
    },
  });
}

export function useLinkCanvasCourse() {
  const { getToken } = useAuth();
  const qc = useQueryClient();

  return useMutation<CanvasLinkResult, Error, number>({
    mutationFn: async (canvasCourseId: number) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      return linkCanvasCourse(token, canvasCourseId);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["courses"] });
      qc.invalidateQueries({ queryKey: ["canvas", "courses"] });
    },
  });
}

export function useJoinCanvasCourse() {
  const { getToken } = useAuth();
  const qc = useQueryClient();

  return useMutation<CanvasJoinResult, Error, number>({
    mutationFn: async (canvasCourseId: number) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      return joinCanvasCourse(token, canvasCourseId);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["courses"] });
      qc.invalidateQueries({ queryKey: ["canvas", "courses"] });
    },
  });
}

// ---------- Course-level ----------

export function useCanvasFiles(courseId: string, enabled = true) {
  const { getToken, isSignedIn } = useAuth();

  return useQuery<CanvasFileListing>({
    queryKey: canvasKeys.files(courseId),
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      return listCanvasFiles(token, courseId);
    },
    enabled: isSignedIn === true && !!courseId && enabled,
    retry: (count, error) => {
      if (isAuthError(error)) return false;
      return count < 3;
    },
  });
}

export function useImportCanvasFiles(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();

  return useMutation<CanvasFileImportResult, Error, readonly number[]>({
    mutationFn: async (fileIds) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      return importCanvasFiles(token, courseId, fileIds);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: canvasKeys.files(courseId) });
      qc.invalidateQueries({ queryKey: ["documents", courseId] });
      qc.invalidateQueries({ queryKey: canvasKeys.syncEvents(courseId) });
    },
  });
}

export function useImportCanvasRoster(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();

  return useMutation<CanvasRosterImportResult, Error, boolean>({
    mutationFn: async (sendInviteEmails: boolean) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      return importCanvasRoster(token, courseId, sendInviteEmails);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: canvasKeys.syncEvents(courseId) });
    },
  });
}

export function useRunCanvasSync(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();

  return useMutation<void, Error, void>({
    mutationFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await runCanvasSync(token, courseId);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: canvasKeys.syncEvents(courseId) });
      qc.invalidateQueries({ queryKey: canvasKeys.files(courseId) });
    },
  });
}

export function useCanvasSyncEvents(courseId: string, limit = 20) {
  const { getToken, isSignedIn } = useAuth();

  return useQuery<readonly CanvasSyncEvent[]>({
    queryKey: [...canvasKeys.syncEvents(courseId), limit],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      return listCanvasSyncEvents(token, courseId, limit);
    },
    enabled: isSignedIn === true && !!courseId,
    retry: (count, error) => {
      if (isAuthError(error)) return false;
      return count < 3;
    },
  });
}
