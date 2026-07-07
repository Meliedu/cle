"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/hooks/use-auth";
import { useAuthedQuery } from "@/hooks/use-authed-query";
import {
  publishWithScoreGate,
  type GradingMode,
  type LateRule,
} from "@/hooks/use-quizzes";
import { API_URL, apiFetch, type ApiEnvelope } from "@/lib/api";

/**
 * TanStack hooks over the activities router (backend B8–B10). Activities are
 * course-scoped, teacher-authored artifacts in one of three participation-only
 * formats (`swipe | vote | comment_reaction`); students submit a per-format
 * `payload` and the teacher watches a live distribution over a WS monitor that
 * mirrors `useCheckpointMonitor`. Query keys: `["activities", courseId]` (list),
 * `["activity", activityId]` (detail), `["activity", activityId, "results"]`.
 */

// ----- types (mirror backend `app/schemas/activity.py`) -----

export type ActivityFormat = "swipe" | "vote" | "comment_reaction";

export type ActivityStatus =
  | "draft"
  | "published"
  | "live"
  | "closed"
  | "archived";

/** Per-format `config` payload (backend B8). */
export interface SwipeConfig {
  readonly prompts: readonly string[];
}
export interface VoteConfig {
  readonly options: readonly string[];
}
export interface CommentReactionConfig {
  readonly reactions: readonly string[];
}
export type ActivityConfig =
  | SwipeConfig
  | VoteConfig
  | CommentReactionConfig
  | Record<string, unknown>;

/** Mirrors `ActivityRead`. */
export interface Activity {
  readonly id: string;
  readonly course_id: string;
  readonly meeting_id: string | null;
  readonly format: ActivityFormat;
  readonly title: string;
  readonly config: ActivityConfig;
  readonly status: ActivityStatus;
  readonly open_at: string | null;
  readonly due_at: string | null;
  readonly close_at: string | null;
  readonly anonymous: boolean;
  readonly score_category_id: string | null;
  readonly points: number | null;
  readonly grading_mode: GradingMode | null;
  readonly late_rule: LateRule | null;
  readonly score_bearing: boolean;
  readonly created_at: string;
  readonly updated_at: string;
}

/**
 * Mirrors `ActivityIntro` — the student-facing public shape returned by
 * `GET /activities/{id}/intro` (backend B9 intro read). A slim projection of
 * {@link Activity}: it carries everything the F9 runner needs to render the
 * interaction (`format`, `config`, `title`) plus the score-disclosure fields,
 * but omits owner-internal columns (`meeting_id`, `score_category_id`,
 * `created_at`/`updated_at`).
 */
export interface ActivityIntro {
  readonly id: string;
  readonly course_id: string;
  readonly format: ActivityFormat;
  readonly title: string;
  readonly config: ActivityConfig;
  readonly status: ActivityStatus;
  readonly open_at: string | null;
  readonly due_at: string | null;
  readonly close_at: string | null;
  readonly anonymous: boolean;
  readonly score_bearing: boolean;
  readonly points: number | null;
  readonly grading_mode: GradingMode | null;
  readonly late_rule: LateRule | null;
}

/** Per-format student submission payload (backend B9). */
export interface SwipeResponsePayload {
  readonly prompt_index: number;
  readonly direction: "left" | "right";
}
export interface VoteResponsePayload {
  readonly choice: string;
}
export interface CommentReactionResponsePayload {
  readonly reaction: string;
}
export type ActivityResponsePayload =
  | SwipeResponsePayload
  | VoteResponsePayload
  | CommentReactionResponsePayload
  | Record<string, unknown>;

/** One persisted response on the teacher results/evidence view. */
export interface ActivityResponseRecord {
  readonly id: string;
  readonly user_id: string;
  readonly payload: ActivityResponsePayload;
  readonly status: string;
  readonly submitted_at: string;
}

/** Mirrors `GET /activities/{id}/results`. */
export interface ActivityResults {
  readonly activity_id: string;
  readonly format: ActivityFormat;
  readonly status: ActivityStatus;
  readonly submission_count: number;
  readonly responses: readonly ActivityResponseRecord[];
}

export const activityKeys = {
  list: (courseId: string) => ["activities", courseId] as const,
  detail: (activityId: string) => ["activity", activityId] as const,
  intro: (activityId: string) => ["activity", activityId, "intro"] as const,
  results: (activityId: string) =>
    ["activity", activityId, "results"] as const,
};

// ----- shared mutation body (mirrors use-checkpoints/use-work-items) -----

async function authedWrite<T>(
  getToken: (opts: { template: string }) => Promise<string | null>,
  path: string,
  method: "POST" | "PATCH" | "DELETE",
  body?: unknown
): Promise<T> {
  const token = await getToken({ template: "backend" });
  if (!token) throw new Error("Not authenticated");
  const res = await apiFetch<ApiEnvelope<T>>(path, {
    method,
    token,
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
  return res.data;
}

// ----- teacher queries -----

/** GET `/courses/{id}/activities` — every activity for the course (owner-guarded). */
export function useActivities(courseId: string) {
  return useAuthedQuery<readonly Activity[]>({
    queryKey: activityKeys.list(courseId),
    path: `/courses/${courseId}/activities`,
    enabled: Boolean(courseId),
  });
}

/** GET `/activities/{id}` — a single activity with its `config`. */
export function useActivity(activityId: string | null) {
  return useAuthedQuery<Activity>({
    queryKey: activityKeys.detail(activityId ?? ""),
    path: `/activities/${activityId}`,
    enabled: Boolean(activityId),
  });
}

/**
 * GET `/activities/{id}/intro` — the student-facing public shape of an OPEN
 * activity (backend B9 intro read). Enrollment-scoped + gated to
 * `published`/`live`; a draft/closed/archived activity is refused with the typed
 * `ACTIVITY_NOT_OPEN` (409), a non-enrolled caller with 403. This is the read the
 * F9 student runner points at — NOT the owner-only `useActivity`.
 */
export function useActivityIntro(activityId: string | null) {
  return useAuthedQuery<ActivityIntro>({
    queryKey: activityKeys.intro(activityId ?? ""),
    path: `/activities/${activityId}/intro`,
    enabled: Boolean(activityId),
  });
}

/** GET `/activities/{id}/results` — teacher evidence + distribution (owner-guarded). */
export function useActivityResults(activityId: string | null) {
  return useAuthedQuery<ActivityResults>({
    queryKey: activityKeys.results(activityId ?? ""),
    path: `/activities/${activityId}/results`,
    enabled: Boolean(activityId),
  });
}

// ----- teacher mutations -----

export interface CreateActivityInput {
  readonly format: ActivityFormat;
  readonly title: string;
  readonly config: ActivityConfig;
  readonly meeting_id?: string | null;
  readonly anonymous?: boolean;
  readonly open_at?: string | null;
  readonly due_at?: string | null;
  readonly close_at?: string | null;
  readonly score_bearing?: boolean;
  readonly score_category_id?: string | null;
  readonly points?: number | null;
  readonly grading_mode?: GradingMode | null;
  readonly late_rule?: LateRule | null;
}

export interface UpdateActivityInput
  extends Partial<Omit<CreateActivityInput, "format">> {
  readonly activityId: string;
  readonly title?: string;
}

function invalidateActivity(
  queryClient: ReturnType<typeof useQueryClient>,
  courseId: string,
  activityId?: string
): void {
  void queryClient.invalidateQueries({ queryKey: activityKeys.list(courseId) });
  if (activityId) {
    void queryClient.invalidateQueries({
      queryKey: activityKeys.detail(activityId),
    });
  }
}

/** POST `/courses/{id}/activities` — author a new activity (201). */
export function useCreateActivity(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation<Activity, Error, CreateActivityInput>({
    mutationFn: (body) =>
      authedWrite<Activity>(
        getToken,
        `/courses/${courseId}/activities`,
        "POST",
        body
      ),
    onSuccess: (data) => invalidateActivity(queryClient, courseId, data.id),
  });
}

/** PATCH `/activities/{id}` — edit an activity's config / schedule / score policy. */
export function useUpdateActivity(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation<Activity, Error, UpdateActivityInput>({
    mutationFn: ({ activityId, ...rest }) => {
      const body: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(rest)) {
        if (value !== undefined) body[key] = value;
      }
      return authedWrite<Activity>(
        getToken,
        `/activities/${activityId}`,
        "PATCH",
        body
      );
    },
    onSuccess: (data) => invalidateActivity(queryClient, courseId, data.id),
  });
}

/**
 * POST `/activities/{id}/publish` — the gated publish (backend B8). A
 * participation-only activity publishes freely; a score-bearing activity
 * missing score fields throws a `ScorePolicyError` (`missing[]` → blocked
 * banner, F4). Reuses the shared quiz publish-gate helper.
 */
export function usePublishActivity(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation<Activity, Error, string>({
    mutationFn: (activityId) =>
      publishWithScoreGate<Activity>(
        getToken,
        `/activities/${activityId}/publish`
      ),
    onSuccess: (data) => invalidateActivity(queryClient, courseId, data.id),
  });
}

// ----- student mutation -----

export interface SubmitActivityResponseInput {
  readonly payload: ActivityResponsePayload;
}

/**
 * POST `/activities/{id}/responses` — submit the student's per-format answer
 * (backend B9). Upserts on `(activity_id, user_id)`; `comment_reaction` stacks
 * inside `payload`. Invalidates the activity detail on success.
 */
export function useSubmitActivityResponse(activityId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation<ActivityResponseRecord, Error, SubmitActivityResponseInput>(
    {
      mutationFn: (body) =>
        authedWrite<ActivityResponseRecord>(
          getToken,
          `/activities/${activityId}/responses`,
          "POST",
          body
        ),
      onSuccess: () => {
        void queryClient.invalidateQueries({
          queryKey: activityKeys.detail(activityId),
        });
      },
    }
  );
}

// ----- live monitor WebSocket (backend B10, mirrors useCheckpointMonitor) -----

/**
 * The live distribution shape is format-specific but always a `label → count`
 * map: swipe `{left, right}`, vote `{option: count}`, comment_reaction
 * `{reaction: count}`.
 */
export type ActivityDistribution = Record<string, number>;

/** State surfaced by `useActivityMonitor` from the monitor WS stream. */
export interface ActivityMonitorState {
  readonly submission_count: number;
  readonly distribution: ActivityDistribution;
  readonly closed: boolean;
  readonly connected: boolean;
}

interface ActivityMonitorMessage {
  readonly type: "state" | "submission" | "closed";
  readonly submission_count?: number;
  readonly distribution?: ActivityDistribution;
}

const MONITOR_RECONNECT_MS = 2000;

/** Convert the REST base (`http(s)://…/api`) to its `ws(s)://…/api` counterpart. */
function activityMonitorSocketUrl(activityId: string, token: string): string {
  const wsBase = API_URL.replace(/^http/, "ws");
  return `${wsBase}/activities/${activityId}/monitor?token=${encodeURIComponent(
    token
  )}`;
}

/**
 * Teacher live-monitor WS client (backend B10). Connects to
 * `ws(s)://<backend>/api/activities/{id}/monitor?token=<jwt>` and folds the
 * server's `state`/`submission`/`closed` frames into a single reactive
 * snapshot. Read-only (no outbound frames). Auto-reconnects on an unexpected
 * drop until the activity reports `closed` or the hook unmounts. Mirrors
 * `useCheckpointMonitor`.
 */
export function useActivityMonitor(
  activityId: string | null,
  token: string | null
): ActivityMonitorState {
  const [state, setState] = useState<ActivityMonitorState>({
    submission_count: 0,
    distribution: {},
    closed: false,
    connected: false,
  });

  // Track "closed" out of band so the reconnect path can read it without being
  // a dependency of the connect effect (which would re-open a fresh socket).
  const closedRef = useRef(false);

  useEffect(() => {
    if (!activityId || !token) return;

    closedRef.current = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let disposed = false;

    const connect = () => {
      if (disposed || closedRef.current) return;
      const ws = new WebSocket(activityMonitorSocketUrl(activityId, token));
      socket = ws;

      ws.onopen = () => {
        if (!disposed) setState((prev) => ({ ...prev, connected: true }));
      };

      ws.onmessage = (event) => {
        let msg: ActivityMonitorMessage;
        try {
          msg = JSON.parse(event.data as string) as ActivityMonitorMessage;
        } catch {
          return; // ignore a malformed frame
        }
        if (msg.type === "closed") {
          closedRef.current = true;
          setState((prev) => ({
            submission_count: msg.submission_count ?? prev.submission_count,
            distribution: msg.distribution ?? prev.distribution,
            closed: true,
            connected: prev.connected,
          }));
          return;
        }
        // "state" (initial snapshot) | "submission" (a response landed)
        setState((prev) => ({
          submission_count: msg.submission_count ?? prev.submission_count,
          distribution: msg.distribution ?? prev.distribution,
          closed: prev.closed,
          connected: prev.connected,
        }));
      };

      ws.onclose = () => {
        if (!disposed) setState((prev) => ({ ...prev, connected: false }));
        if (disposed || closedRef.current) return;
        reconnectTimer = setTimeout(connect, MONITOR_RECONNECT_MS);
      };

      ws.onerror = () => {
        // Let onclose drive the reconnect; just tear this socket down.
        ws.close();
      };
    };

    connect();

    return () => {
      disposed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (socket) {
        socket.onopen = null;
        socket.onmessage = null;
        socket.onclose = null;
        socket.onerror = null;
        socket.close();
      }
    };
  }, [activityId, token]);

  return state;
}
