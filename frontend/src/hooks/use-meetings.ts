"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/hooks/use-auth";
import { useAuthedQuery } from "@/hooks/use-authed-query";
import { apiFetch, type ApiEnvelope } from "@/lib/api";

/**
 * TanStack hooks over the existing `meetings.py` router
 * (`/courses/{id}/meetings` + `/meetings/{id}/release-state`). The schedule
 * step (T018) reuses these to list/create/edit sessions rather than rebuilding
 * any meeting machinery. Query keys are namespaced under `["meetings", courseId]`.
 */

// ----- types (mirror backend `app/schemas/curriculum.py`) -----

export type MeetingStatus = "planned" | "in_progress" | "taught" | "cancelled";
export type ReleaseState = "locked" | "released" | "completed" | "archived";

/** Mirrors `CourseMeetingResponse`. */
export interface Meeting {
  readonly id: string;
  readonly course_id: string;
  readonly module_id: string | null;
  readonly meeting_index: number;
  readonly title: string | null;
  readonly scheduled_at: string;
  readonly duration_minutes: number;
  readonly location: string | null;
  readonly status: MeetingStatus;
  readonly release_state: ReleaseState;
  readonly topic_summary: string | null;
  readonly canvas_event_id: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

/** Mirrors `CourseMeetingCreate`. */
export interface MeetingCreate {
  readonly meeting_index: number;
  readonly title?: string | null;
  readonly scheduled_at: string;
  readonly duration_minutes?: number;
  readonly location?: string | null;
  readonly topic_summary?: string | null;
}

/** Mirrors `CourseMeetingUpdate` (all fields optional). */
export type MeetingUpdate = Partial<MeetingCreate> & { readonly status?: MeetingStatus };

export const meetingKeys = {
  list: (courseId: string) => ["meetings", courseId] as const,
};

/** GET `/courses/{id}/meetings` — every session for the course, by date. */
export function useMeetings(courseId: string) {
  return useAuthedQuery<readonly Meeting[]>({
    queryKey: meetingKeys.list(courseId),
    path: `/courses/${courseId}/meetings`,
    enabled: Boolean(courseId),
  });
}

/** POST `/courses/{id}/meetings` — create a session. */
export function useCreateMeeting(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation<Meeting, Error, MeetingCreate>({
    mutationFn: async (body) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<Meeting>>(
        `/courses/${courseId}/meetings`,
        { method: "POST", token, body: JSON.stringify(body) }
      );
      return res.data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: meetingKeys.list(courseId) });
    },
  });
}

interface UpdateMeetingInput {
  readonly meetingId: string;
  readonly patch: MeetingUpdate;
}

/** PUT `/courses/{id}/meetings/{meetingId}` — edit a session. */
export function useUpdateMeeting(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation<Meeting, Error, UpdateMeetingInput>({
    mutationFn: async ({ meetingId, patch }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<Meeting>>(
        `/courses/${courseId}/meetings/${meetingId}`,
        { method: "PUT", token, body: JSON.stringify(patch) }
      );
      return res.data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: meetingKeys.list(courseId) });
    },
  });
}

/** DELETE `/courses/{id}/meetings/{meetingId}` — soft-delete a session. */
export function useDeleteMeeting(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation<void, Error, string>({
    mutationFn: async (meetingId) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await apiFetch<ApiEnvelope<null>>(
        `/courses/${courseId}/meetings/${meetingId}`,
        { method: "DELETE", token }
      );
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: meetingKeys.list(courseId) });
    },
  });
}

interface ReleaseStateInput {
  readonly meetingId: string;
  readonly releaseState: ReleaseState;
  readonly topicSummary?: string | null;
}

/**
 * PATCH `/courses/{id}/meetings/{meetingId}/release-state` (Task 7) — transition
 * a session's student-visibility axis and, optionally, set its topic summary in
 * the same call. Only legal transitions succeed (the backend returns 409 with
 * `ILLEGAL_RELEASE_TRANSITION` otherwise).
 */
export function useSetMeetingReleaseState(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation<Meeting, Error, ReleaseStateInput>({
    mutationFn: async ({ meetingId, releaseState, topicSummary }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const body: Record<string, unknown> = { release_state: releaseState };
      if (topicSummary !== undefined) body.topic_summary = topicSummary;
      const res = await apiFetch<ApiEnvelope<Meeting>>(
        `/courses/${courseId}/meetings/${meetingId}/release-state`,
        { method: "PATCH", token, body: JSON.stringify(body) }
      );
      return res.data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: meetingKeys.list(courseId) });
    },
  });
}
