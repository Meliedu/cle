"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/hooks/use-auth";
import { useAuthedQuery } from "@/hooks/use-authed-query";
import { usePollWindow } from "@/hooks/use-setup";
import { API_URL, apiFetch, type ApiEnvelope } from "@/lib/api";

/**
 * TanStack hooks over the checkpoints router (backend Task 9). Checkpoints are
 * DRAFT-only in P1 (Decision 3): the teacher reviews generated draft cards,
 * lightly edits a review-point prompt, or removes a card with a reason. Query
 * keys are namespaced under `["checkpoints", courseId]` (list) and
 * `["checkpoint", checkpointId]` (detail with cards).
 */

// ----- types (mirror backend `app/schemas/checkpoint.py`) -----

export type CheckpointStatus =
  | "draft"
  | "teacher_editing"
  | "approved"
  | "scheduled"
  | "published"
  | "live"
  | "closed"
  | "archived";

export type CardKind = "review_point" | "final_comments";

export type RemovedReason = "not_needed" | "duplicate" | "not_covered" | "other";

/** Mirrors `CloseRule` (backend `app/schemas/checkpoint.py`). */
export type CloseRule = "manual" | "at_close_at" | "end_of_session";

/** Mirrors `CheckpointResponse`. */
export interface Checkpoint {
  readonly id: string;
  readonly course_id: string;
  readonly meeting_id: string | null;
  readonly kind: string;
  readonly status: CheckpointStatus;
  readonly title: string;
  readonly qr_enabled: boolean;
  readonly release_at?: string | null;
  readonly close_at?: string | null;
  readonly close_rule?: CloseRule | null;
  readonly generation_meta: Record<string, unknown> | null;
  readonly created_at: string;
  readonly updated_at: string;
}

/** Mirrors `CheckpointCardResponse`. */
export interface CheckpointCard {
  readonly id: string;
  readonly checkpoint_id: string;
  readonly position: number;
  readonly kind: CardKind;
  readonly prompt: string;
  readonly document_id: string | null;
  readonly chunk_id: string | null;
  readonly objective_id: string | null;
  readonly removed: boolean;
  readonly removed_reason: RemovedReason | null;
  readonly removed_note: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

/** Mirrors `CheckpointWithCardsResponse`. */
export interface CheckpointWithCards extends Checkpoint {
  readonly cards: readonly CheckpointCard[];
}

export const checkpointKeys = {
  list: (courseId: string) => ["checkpoints", courseId] as const,
  history: (courseId: string) => ["checkpoints", courseId, "history"] as const,
  myHistory: (courseId: string) =>
    ["checkpoints", courseId, "my-history"] as const,
  detail: (checkpointId: string) => ["checkpoint", checkpointId] as const,
  results: (checkpointId: string) =>
    ["checkpoint", checkpointId, "results"] as const,
  intro: (checkpointId: string) =>
    ["checkpoint", checkpointId, "intro"] as const,
  followUp: (checkpointId: string) =>
    ["checkpoint", checkpointId, "follow-up"] as const,
  attendance: (meetingId: string) =>
    ["meeting-attendance", meetingId] as const,
};

const LIST_POLL_INTERVAL_MS = 3000;

// ----- queries -----

/**
 * GET `/courses/{id}/checkpoints` — every draft checkpoint for the course. When
 * `poll` is set, refetches every few seconds until at least one checkpoint
 * appears, so the async `generate_checkpoints` job's output shows up without a
 * manual refresh.
 */
export function useCheckpoints(
  courseId: string,
  options: { poll?: boolean; pollKey?: number } = {}
) {
  const { poll = false, pollKey = 0 } = options;
  const { expired, windowRef } = usePollWindow(poll, pollKey);
  const query = useAuthedQuery<readonly Checkpoint[]>({
    queryKey: checkpointKeys.list(courseId),
    path: `/courses/${courseId}/checkpoints`,
    enabled: Boolean(courseId),
    refetchInterval: (q) => {
      if (!poll) return false;
      if ((q.state.data?.length ?? 0) > 0) return false;
      if (!windowRef.current) return false;
      return LIST_POLL_INTERVAL_MS;
    },
  });
  const timedOut = poll && (query.data?.length ?? 0) === 0 && expired;
  return { ...query, timedOut };
}

/** GET `/checkpoints/{id}` — a single checkpoint with its ordered cards. */
export function useCheckpoint(checkpointId: string | null) {
  return useAuthedQuery<CheckpointWithCards>({
    queryKey: checkpointKeys.detail(checkpointId ?? ""),
    path: `/checkpoints/${checkpointId}`,
    enabled: Boolean(checkpointId),
  });
}

// ----- mutations -----

interface UpdateCardInput {
  readonly cardId: string;
  readonly prompt?: string;
  readonly removed?: boolean;
  readonly removedReason?: RemovedReason;
  readonly removedNote?: string | null;
}

/**
 * PATCH `/checkpoints/{id}/cards/{cardId}` — edit a review-point prompt or
 * soft-remove a card with a categorized reason. The backend enforces
 * `FINAL_CARD_FIXED` (final card is never removable) and `REVIEW_REQUIRED`
 * (only draft checkpoints are editable); callers surface those typed codes.
 * Invalidates both the checkpoint detail and the course list on success.
 */
export function useUpdateCheckpointCard(courseId: string, checkpointId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation<CheckpointCard, Error, UpdateCardInput>({
    mutationFn: async ({ cardId, prompt, removed, removedReason, removedNote }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const body: Record<string, unknown> = {};
      if (prompt !== undefined) body.prompt = prompt;
      if (removed !== undefined) body.removed = removed;
      if (removedReason !== undefined) body.removed_reason = removedReason;
      if (removedNote !== undefined) body.removed_note = removedNote;
      const res = await apiFetch<ApiEnvelope<CheckpointCard>>(
        `/checkpoints/${checkpointId}/cards/${cardId}`,
        { method: "PATCH", token, body: JSON.stringify(body) }
      );
      return res.data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: checkpointKeys.detail(checkpointId),
      });
      void queryClient.invalidateQueries({
        queryKey: checkpointKeys.list(courseId),
      });
    },
  });
}

/* ================================================================== */
/*  P3 — publish-path lifecycle, teacher reads, student flow,         */
/*  attendance, live monitor. Mirrors backend `checkpoints.py` +      */
/*  `attendance.py` (P3 T1–T12).                                      */
/* ================================================================== */

// ----- P3 response types (mirror `app/schemas/checkpoint.py` + `attendance.py`) -----

/** Mirrors `CheckpointCardResult` — a per-card aggregate on the teacher results view. */
export interface CheckpointCardResult {
  readonly card_id: string;
  readonly kind: CardKind;
  readonly prompt: string;
  readonly position: number;
  readonly response_count: number;
  /** Histogram keyed `"-2".."2"` for review_point cards; empty for final_comments. */
  readonly confidence_distribution: Record<string, number>;
  readonly text_response_count: number;
}

/** Mirrors `CheckpointResults` — teacher results payload for one checkpoint. */
export interface CheckpointResults {
  readonly checkpoint_id: string;
  readonly status: string;
  readonly active_student_count: number;
  readonly responded_count: number;
  readonly missed_count: number;
  readonly cards: readonly CheckpointCardResult[];
}

/** Mirrors `StudentCheckpointCard` — a card as the student sees it (prompt only). */
export interface StudentCheckpointCard {
  readonly id: string;
  readonly position: number;
  readonly kind: CardKind;
  readonly prompt: string;
}

/** Mirrors `CheckpointIntroResponse` — the student intro payload (S034). */
export interface CheckpointIntro {
  readonly checkpoint_id: string;
  readonly title: string;
  readonly status: string;
  readonly close_at: string | null;
  readonly cards: readonly StudentCheckpointCard[];
}

/** Mirrors `CheckpointResponseResult` — a persisted response echoed to the student. */
export interface CheckpointResponseResult {
  readonly id: string;
  readonly checkpoint_id: string;
  readonly card_id: string;
  readonly confidence: number | null;
  readonly text_response: string | null;
  readonly status: string;
  readonly submitted_at: string;
}

export type HistoryDerivedStatus = "complete" | "late" | "missed" | "upcoming";

/** Mirrors `StudentCheckpointHistoryItem` — one row of the student's own history (S039). */
export interface StudentCheckpointHistoryItem {
  readonly checkpoint_id: string;
  readonly title: string;
  readonly kind: string;
  readonly status: string;
  readonly derived_status: HistoryDerivedStatus;
  readonly release_at: string | null;
  readonly close_at: string | null;
  readonly responded_count: number;
  readonly live_card_count: number;
}

/** Mirrors `FollowUpSuggestedCard` — a weak card the student should revisit (S040). */
export interface FollowUpSuggestedCard {
  readonly card_id: string;
  readonly prompt: string;
  readonly confidence: number;
  readonly concept_id: string | null;
  readonly concept_name: string | null;
}

/** Mirrors `FollowUpSuggested` — the suggested follow-up for a checkpoint (S040). */
export interface FollowUpSuggested {
  readonly checkpoint_id: string;
  readonly threshold: number;
  readonly weak_cards: readonly FollowUpSuggestedCard[];
}

/** Mirrors `RevisitResponseResult` — a revisit submission + before/after signal (S041). */
export interface RevisitResponseResult {
  readonly response: CheckpointResponseResult;
  readonly carried_from_id: string;
  readonly concept_id: string | null;
  readonly confidence_before: number | null;
  readonly confidence_after: number | null;
  readonly delta: number | null;
}

/** Mirrors `LaunchResponse` — a minted/rotated QR launch (attendance T9). */
export interface CheckpointLaunch {
  readonly id: string;
  readonly checkpoint_id: string;
  readonly meeting_id: string;
  readonly token: string;
  readonly jti: string;
  readonly window_start: string;
  readonly window_end: string;
  readonly status: string;
}

/** Mirrors `ScanResponse` — the result of a QR scan (attendance T10). */
export interface AttendanceScanResult {
  readonly attendance_id: string;
  readonly meeting_id: string;
  readonly checkpoint_id: string;
  readonly status: string;
  readonly source: string;
  readonly checked_in_at: string;
  /** Client route into the checkpoint intro (S034). */
  readonly intro_route: string;
}

export type AttendanceStatus = "present" | "late" | "excused" | "absent";

/** Mirrors `AttendanceRosterEntry` — one active student's attendance for a meeting. */
export interface AttendanceRosterEntry {
  readonly user_id: string;
  readonly full_name: string | null;
  readonly email: string;
  readonly status: AttendanceStatus;
  readonly attendance_id: string | null;
  readonly source: string | null;
  readonly override_reason: string | null;
  readonly override_by: string | null;
  readonly checked_in_at: string | null;
}

/** Mirrors `AttendanceRoster` — the teacher roster for a single meeting (S037). */
export interface AttendanceRoster {
  readonly meeting_id: string;
  readonly course_id: string;
  readonly present_count: number;
  readonly late_count: number;
  readonly excused_count: number;
  readonly absent_count: number;
  readonly entries: readonly AttendanceRosterEntry[];
}

/** Mirrors `AttendanceOverrideResponse` — the overridden attendance row. */
export interface AttendanceOverrideResult {
  readonly attendance_id: string;
  readonly meeting_id: string;
  readonly user_id: string;
  readonly status: string;
  readonly source: string;
  readonly override_reason: string | null;
  readonly override_by: string | null;
  readonly checked_in_at: string;
}

// ----- P3 mutation inputs -----

interface ScheduleInput {
  readonly release_at?: string;
  readonly close_at?: string | null;
  readonly close_rule?: CloseRule;
}

type PublishInput = ScheduleInput | void;

interface SubmitResponseInput {
  readonly card_id: string;
  readonly confidence?: number | null;
  readonly text_response?: string | null;
}

interface OverrideAttendanceInput {
  readonly attendanceId: string;
  readonly status: AttendanceStatus;
  readonly override_reason: string;
}

/**
 * Shared body for a JSON POST/PATCH that unwraps the standard envelope. Fetches
 * a fresh backend JWT, throws on a missing token, and returns `data`.
 */
async function authedWrite<T>(
  getToken: (opts: { template: string }) => Promise<string | null>,
  path: string,
  method: "POST" | "PATCH",
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

// ----- publish-path lifecycle mutations (P3 T5) -----

/**
 * Invalidate a checkpoint's detail + both course lists (draft + history) after a
 * lifecycle transition, so every surface that could render the checkpoint
 * refreshes without a manual refetch.
 */
function invalidateCheckpoint(
  queryClient: ReturnType<typeof useQueryClient>,
  courseId: string,
  checkpointId: string
): void {
  void queryClient.invalidateQueries({
    queryKey: checkpointKeys.detail(checkpointId),
  });
  void queryClient.invalidateQueries({
    queryKey: checkpointKeys.list(courseId),
  });
  void queryClient.invalidateQueries({
    queryKey: checkpointKeys.history(courseId),
  });
}

/** POST `/checkpoints/{id}/approve` — draft/teacher_editing → approved. */
export function useApproveCheckpoint(courseId: string, checkpointId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation<Checkpoint, Error, void>({
    mutationFn: () =>
      authedWrite<Checkpoint>(
        getToken,
        `/checkpoints/${checkpointId}/approve`,
        "POST"
      ),
    onSuccess: () => invalidateCheckpoint(queryClient, courseId, checkpointId),
  });
}

/** POST `/checkpoints/{id}/schedule` — approved → scheduled (future release). */
export function useScheduleCheckpoint(courseId: string, checkpointId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation<Checkpoint, Error, ScheduleInput>({
    mutationFn: (body) =>
      authedWrite<Checkpoint>(
        getToken,
        `/checkpoints/${checkpointId}/schedule`,
        "POST",
        body
      ),
    onSuccess: () => invalidateCheckpoint(queryClient, courseId, checkpointId),
  });
}

/** POST `/checkpoints/{id}/publish` — approved/scheduled → published. */
export function usePublishCheckpoint(courseId: string, checkpointId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation<Checkpoint, Error, PublishInput>({
    mutationFn: (body) =>
      authedWrite<Checkpoint>(
        getToken,
        `/checkpoints/${checkpointId}/publish`,
        "POST",
        body ?? undefined
      ),
    onSuccess: () => invalidateCheckpoint(queryClient, courseId, checkpointId),
  });
}

/** POST `/checkpoints/{id}/close` — published/live → closed. */
export function useCloseCheckpoint(courseId: string, checkpointId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation<Checkpoint, Error, void>({
    mutationFn: () =>
      authedWrite<Checkpoint>(
        getToken,
        `/checkpoints/${checkpointId}/close`,
        "POST"
      ),
    onSuccess: () => invalidateCheckpoint(queryClient, courseId, checkpointId),
  });
}

// ----- teacher reads (P3 T6, T049) -----

/** GET `/checkpoints/{id}/results` — per-card response aggregates (owner-guarded). */
export function useCheckpointResults(checkpointId: string | null) {
  return useAuthedQuery<CheckpointResults>({
    queryKey: checkpointKeys.results(checkpointId ?? ""),
    path: `/checkpoints/${checkpointId}/results`,
    enabled: Boolean(checkpointId),
  });
}

/** GET `/courses/{id}/checkpoints?history=1` — closed/archived checkpoints. */
export function useCheckpointHistory(courseId: string) {
  return useAuthedQuery<readonly Checkpoint[]>({
    queryKey: checkpointKeys.history(courseId),
    path: `/courses/${courseId}/checkpoints?history=1`,
    enabled: Boolean(courseId),
  });
}

// ----- launch (attendance T9) -----

/**
 * POST `/checkpoints/{id}/launch` — mint (or `rotate`) the signed QR token +
 * window. Owner-guarded; refuses with `QR_NOT_AVAILABLE` (409) when the
 * checkpoint is not a session-bound published/live checkpoint with QR enabled.
 */
export function useLaunchCheckpoint(checkpointId: string) {
  const { getToken } = useAuth();
  return useMutation<CheckpointLaunch, Error, { rotate?: boolean } | void>({
    mutationFn: (input) =>
      authedWrite<CheckpointLaunch>(
        getToken,
        `/checkpoints/${checkpointId}/launch`,
        "POST",
        { rotate: Boolean(input && input.rotate) }
      ),
  });
}

// ----- student flow (P3 T7, T8) -----

/** GET `/checkpoints/{id}/intro` — the ordered live cards + context (S034). */
export function useCheckpointIntro(checkpointId: string | null) {
  return useAuthedQuery<CheckpointIntro>({
    queryKey: checkpointKeys.intro(checkpointId ?? ""),
    path: `/checkpoints/${checkpointId}/intro`,
    enabled: Boolean(checkpointId),
  });
}

/**
 * POST `/checkpoints/{id}/responses` — submit one card's answer (S035). Supply
 * `confidence` (−2..+2) for a review_point card or `text_response` for the
 * final_comments card; the backend enforces exactly-one against the card kind.
 * Invalidates the intro (so answered state refreshes) and the student history.
 */
export function useSubmitCheckpointResponse(
  checkpointId: string,
  courseId?: string
) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation<CheckpointResponseResult, Error, SubmitResponseInput>({
    mutationFn: (body) =>
      authedWrite<CheckpointResponseResult>(
        getToken,
        `/checkpoints/${checkpointId}/responses`,
        "POST",
        body
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: checkpointKeys.intro(checkpointId),
      });
      void queryClient.invalidateQueries({
        queryKey: checkpointKeys.followUp(checkpointId),
      });
      if (courseId) {
        void queryClient.invalidateQueries({
          queryKey: checkpointKeys.myHistory(courseId),
        });
      }
    },
  });
}

/** GET `/users/me/courses/{id}/checkpoints` — the student's own history (S039). */
export function useMyCheckpointHistory(courseId: string) {
  return useAuthedQuery<readonly StudentCheckpointHistoryItem[]>({
    queryKey: checkpointKeys.myHistory(courseId),
    path: `/users/me/courses/${courseId}/checkpoints`,
    enabled: Boolean(courseId),
  });
}

/** GET `/checkpoints/{id}/follow-up-suggested` — the student's weak cards (S040). */
export function useFollowUpSuggested(checkpointId: string | null) {
  return useAuthedQuery<FollowUpSuggested>({
    queryKey: checkpointKeys.followUp(checkpointId ?? ""),
    path: `/checkpoints/${checkpointId}/follow-up-suggested`,
    enabled: Boolean(checkpointId),
  });
}

/**
 * POST `/checkpoints/{id}/revisit-response` — re-submit against a `follow_up`
 * checkpoint and get the before/after confidence delta (S041). A non-follow_up
 * or uncarried checkpoint is a typed `NOT_A_REVISIT` 409.
 */
export function useRevisitResponse(checkpointId: string) {
  const { getToken } = useAuth();
  return useMutation<RevisitResponseResult, Error, SubmitResponseInput>({
    mutationFn: (body) =>
      authedWrite<RevisitResponseResult>(
        getToken,
        `/checkpoints/${checkpointId}/revisit-response`,
        "POST",
        body
      ),
  });
}

// ----- attendance (P3 T10, T11) -----

/**
 * POST `/attend/{token}` — record a QR attendance scan. Errors carry typed
 * codes: 401 `LAUNCH_TOKEN_INVALID`, 409 `LAUNCH_CLOSED`, 429 `RATE_LIMITED`.
 */
export function useScanAttendance() {
  const { getToken } = useAuth();
  return useMutation<AttendanceScanResult, Error, { token: string }>({
    mutationFn: ({ token: launchToken }) =>
      authedWrite<AttendanceScanResult>(
        getToken,
        `/attend/${encodeURIComponent(launchToken)}`,
        "POST"
      ),
  });
}

/** GET `/meetings/{id}/attendance` — the teacher attendance roster (S037). */
export function useMeetingAttendance(meetingId: string | null) {
  return useAuthedQuery<AttendanceRoster>({
    queryKey: checkpointKeys.attendance(meetingId ?? ""),
    path: `/meetings/${meetingId}/attendance`,
    enabled: Boolean(meetingId),
  });
}

/**
 * PATCH `/attendance/{id}` — a teacher manual override. `override_reason` is
 * required (a blank reason is a 422). Invalidates the meeting roster on success.
 */
export function useOverrideAttendance(meetingId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation<AttendanceOverrideResult, Error, OverrideAttendanceInput>({
    mutationFn: ({ attendanceId, status, override_reason }) =>
      authedWrite<AttendanceOverrideResult>(
        getToken,
        `/attendance/${attendanceId}`,
        "PATCH",
        { status, override_reason }
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: checkpointKeys.attendance(meetingId),
      });
    },
  });
}

// ----- live monitor WebSocket (P3 T12) -----

/** State surfaced by `useCheckpointMonitor` from the monitor WS stream. */
export interface CheckpointMonitorState {
  readonly submission_count: number;
  /** −2..+2 histogram, keyed `"-2".."2"`. */
  readonly confidence_distribution: Record<string, number>;
  readonly closed: boolean;
  readonly connected: boolean;
}

interface MonitorMessage {
  readonly type: "state" | "submission" | "closed";
  readonly submission_count?: number;
  readonly confidence_distribution?: Record<string, number>;
}

const MONITOR_RECONNECT_MS = 2000;

/** Convert the REST base (`http(s)://…/api`) to its `ws(s)://…/api` counterpart. */
function monitorSocketUrl(checkpointId: string, token: string): string {
  const wsBase = API_URL.replace(/^http/, "ws");
  return `${wsBase}/checkpoints/${checkpointId}/monitor?token=${encodeURIComponent(
    token
  )}`;
}

/**
 * Teacher live-monitor WS client (Decision 4). Connects to
 * `ws(s)://<backend>/api/checkpoints/{id}/monitor?token=<jwt>` and folds the
 * server's `state`/`submission`/`closed` frames into a single reactive snapshot.
 * The monitor is read-only (no outbound frames). Auto-reconnects on an
 * unexpected drop until the checkpoint reports `closed` or the hook unmounts.
 */
export function useCheckpointMonitor(
  checkpointId: string | null,
  token: string | null
): CheckpointMonitorState {
  const [state, setState] = useState<CheckpointMonitorState>({
    submission_count: 0,
    confidence_distribution: {},
    closed: false,
    connected: false,
  });

  // Track "closed" out of band so the reconnect path can read it without being
  // a dependency of the connect effect (which would re-open a fresh socket).
  const closedRef = useRef(false);

  useEffect(() => {
    if (!checkpointId || !token) return;

    closedRef.current = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let disposed = false;

    const connect = () => {
      if (disposed || closedRef.current) return;
      const ws = new WebSocket(monitorSocketUrl(checkpointId, token));
      socket = ws;

      ws.onopen = () => {
        if (!disposed) setState((prev) => ({ ...prev, connected: true }));
      };

      ws.onmessage = (event) => {
        let msg: MonitorMessage;
        try {
          msg = JSON.parse(event.data as string) as MonitorMessage;
        } catch {
          return; // ignore a malformed frame
        }
        if (msg.type === "closed") {
          closedRef.current = true;
          setState((prev) => ({
            submission_count: msg.submission_count ?? prev.submission_count,
            confidence_distribution:
              msg.confidence_distribution ?? prev.confidence_distribution,
            closed: true,
            connected: prev.connected,
          }));
          return;
        }
        // "state" (initial snapshot) | "submission" (a response landed)
        setState((prev) => ({
          submission_count: msg.submission_count ?? prev.submission_count,
          confidence_distribution:
            msg.confidence_distribution ?? prev.confidence_distribution,
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
  }, [checkpointId, token]);

  return state;
}
