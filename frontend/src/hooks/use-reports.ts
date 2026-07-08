"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/hooks/use-auth";
import { useAuthedQuery } from "@/hooks/use-authed-query";
import { apiFetch, type ApiEnvelope } from "@/lib/api";

/**
 * TanStack hooks over the P7 reports router (`app/api/reports.py`, backend
 * B5–B7). A report is DRAFTED from reviewed learning notes only (Core §0.2) and
 * never leaves `draft` without non-empty `evidence_refs`; the send/export gate
 * is a server-side `REPORT_NOT_REVIEWED` (409). Teacher reads/writes are
 * owner-scoped (`/courses/{id}/reports`, `/reports/{id}`); student reads are
 * enrollment-scoped and only ever see `audience='student' AND status='sent'`
 * rows (`/users/me/courses/{id}/reports`). Mirrors the `use-work-items.ts`
 * shape — a query-key factory, `useAuthedQuery` for reads, `authedWrite` for
 * mutations that invalidate the course report archive on success.
 */

// ----- types (mirror backend `app/schemas/report.py`) -----

/** Mirrors the `reports.audience` CHECK (spec §4.9). */
export type ReportAudience = "student" | "teacher";

/** Mirrors the `reports.period` CHECK (spec §4.9). */
export type ReportPeriod = "weekly" | "end_term";

/** Mirrors the `reports.status` CHECK (spec §4.9). */
export type ReportStatus = "draft" | "reviewed" | "sent" | "archived";

/** A weak-concept row inside the report `body`, RESHAPED from `concept_mastery`. */
export interface ReportWeakPoint {
  readonly concept_id: string;
  readonly name: string;
  readonly mastery_score: number;
}

/** Completed-work rollup inside the report `body` (from the work-item spine). */
export interface ReportCompletedWork {
  readonly completed_count: number;
}

/**
 * The typed report `body` — every section is composed from reviewed evidence.
 * `null` while a draft is still being generated (no body yet). `claim_limits`
 * is the pilot `claim_limits['report']` disclaimer, rendered verbatim.
 */
export interface ReportBody {
  readonly summary: string;
  readonly observations: readonly string[];
  readonly completed_work: ReportCompletedWork;
  readonly weak_points: readonly ReportWeakPoint[];
  readonly next_actions: readonly string[];
  readonly claim_limits: string;
}

/** One export-history entry appended on each `POST /reports/{id}/export`. */
export interface ReportExportHistoryEntry {
  readonly exported_at: string;
  readonly exported_by?: string | null;
}

/** Mirrors `ReportResponse` — the full report row (teacher + student reads). */
export interface ReportResponse {
  readonly id: string;
  readonly course_id: string;
  readonly audience: ReportAudience;
  readonly user_id: string | null;
  readonly period: ReportPeriod;
  readonly period_start: string;
  readonly period_end: string;
  readonly body: ReportBody | null;
  readonly evidence_refs: readonly string[];
  readonly status: ReportStatus;
  readonly reviewed_by: string | null;
  readonly reviewed_at: string | null;
  readonly sent_at: string | null;
  readonly export_history: readonly ReportExportHistoryEntry[];
  readonly created_at: string;
  readonly updated_at: string;
}

/** One resolved reviewed-note row in the export evidence appendix (B6). */
export interface EvidenceAppendixEntry {
  readonly id: string;
  readonly review_status: string;
  readonly observed_signal: string | null;
  readonly draft_interpretation: string | null;
  readonly limitation_note: string | null;
}

/** Export-share flags (`PATCH /reports/{id}/share-settings`). */
export interface ReportShareSettings {
  readonly include_evidence_appendix: boolean;
  readonly visible_to_student: boolean;
  readonly allow_download: boolean;
}

/** Mirrors the export payload (`POST /reports/{id}/export`). */
export interface ReportExport {
  readonly report: ReportResponse;
  readonly evidence_appendix: readonly EvidenceAppendixEntry[];
  readonly share_settings: ReportShareSettings;
  readonly exported_at: string;
}

/** Optional archive filters for `GET /courses/{id}/reports`. */
export interface ReportFilters {
  readonly audience?: ReportAudience;
  readonly period?: ReportPeriod;
  readonly status?: ReportStatus;
}

export const reportKeys = {
  list: (courseId: string, filters?: ReportFilters) =>
    ["reports", "list", courseId, filters ?? {}] as const,
  detail: (reportId: string) => ["reports", "detail", reportId] as const,
  myList: (courseId: string) => ["reports", "me", "list", courseId] as const,
  myDetail: (reportId: string) =>
    ["reports", "me", "detail", reportId] as const,
};

// ----- shared mutation body -----

/**
 * JSON POST/PATCH that unwraps the standard envelope. Fetches a fresh backend
 * JWT, throws on a missing token, and returns `data`. Mirrors
 * `use-work-items.ts::authedWrite`.
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

/** Build the `?audience=&period=&status=` query string from optional filters. */
function buildReportQuery(filters?: ReportFilters): string {
  if (!filters) return "";
  const params = new URLSearchParams();
  if (filters.audience) params.set("audience", filters.audience);
  if (filters.period) params.set("period", filters.period);
  if (filters.status) params.set("status", filters.status);
  const query = params.toString();
  return query ? `?${query}` : "";
}

// ----- teacher reads (owner-scoped) -----

/**
 * GET `/courses/{id}/reports` — the owner's report archive, optionally filtered
 * by `audience`/`period`/`status` (backend B5). 404 on a non-owner course.
 */
export function useReports(courseId: string, filters?: ReportFilters) {
  return useAuthedQuery<readonly ReportResponse[]>({
    queryKey: reportKeys.list(courseId, filters),
    path: `/courses/${courseId}/reports${buildReportQuery(filters)}`,
    enabled: Boolean(courseId),
  });
}

/**
 * GET `/reports/{id}` — one report detail incl. `evidence_refs`. The backend
 * re-derives the course and re-applies the owner guard (404 on mismatch).
 */
export function useReport(reportId: string | null) {
  return useAuthedQuery<ReportResponse>({
    queryKey: reportKeys.detail(reportId ?? ""),
    path: `/reports/${reportId}`,
    enabled: Boolean(reportId),
  });
}

// ----- teacher mutations -----

/**
 * Invalidate every read that surfaces a course's reports — the archive and any
 * open detail — so an edit / approve / send / export refreshes without a manual
 * refetch.
 */
function invalidateReports(
  queryClient: ReturnType<typeof useQueryClient>,
  courseId: string,
  reportId?: string
): void {
  void queryClient.invalidateQueries({ queryKey: ["reports", "list", courseId] });
  if (reportId) {
    void queryClient.invalidateQueries({
      queryKey: reportKeys.detail(reportId),
    });
  }
}

/** Variables for a `PATCH /reports/{id}` draft-body edit. */
export interface UpdateReportInput {
  readonly reportId: string;
  readonly body: ReportBody;
}

/**
 * PATCH `/reports/{id}` — edit a draft report's `body` sections. The backend
 * refuses editing anything past `draft` with a typed 409 (`REPORT_NOT_EDITABLE`).
 */
export function useUpdateReport(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation<ReportResponse, Error, UpdateReportInput>({
    mutationFn: ({ reportId, body }) =>
      authedWrite<ReportResponse>(getToken, `/reports/${reportId}`, "PATCH", {
        body,
      }),
    onSuccess: (report) => invalidateReports(queryClient, courseId, report.id),
  });
}

/**
 * POST `/reports/{id}/approve` — move `draft→reviewed` (records reviewer +
 * timestamp, writes an `audit_events` row). 409 `REPORT_INVALID_TRANSITION`
 * from any non-`draft` state.
 */
export function useApproveReport(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation<ReportResponse, Error, string>({
    mutationFn: (reportId) =>
      authedWrite<ReportResponse>(
        getToken,
        `/reports/${reportId}/approve`,
        "POST"
      ),
    onSuccess: (report) => invalidateReports(queryClient, courseId, report.id),
  });
}

/**
 * POST `/reports/{id}/send` — move `reviewed→sent` (sets `sent_at`, flips the
 * student delivery state, writes an `audit_events` row). 409
 * `REPORT_NOT_REVIEWED` unless the report is `reviewed` with non-empty
 * `evidence_refs`.
 */
export function useSendReport(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation<ReportResponse, Error, string>({
    mutationFn: (reportId) =>
      authedWrite<ReportResponse>(
        getToken,
        `/reports/${reportId}/send`,
        "POST"
      ),
    onSuccess: (report) => invalidateReports(queryClient, courseId, report.id),
  });
}

/**
 * POST `/reports/{id}/export` — same send gate; appends to `export_history` +
 * an `audit_events` row and returns the export payload (report + reviewed-note
 * evidence appendix + share settings). 409 `REPORT_NOT_REVIEWED` on the gate.
 */
export function useExportReport(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation<ReportExport, Error, string>({
    mutationFn: (reportId) =>
      authedWrite<ReportExport>(
        getToken,
        `/reports/${reportId}/export`,
        "POST"
      ),
    onSuccess: (result) =>
      invalidateReports(queryClient, courseId, result.report.id),
  });
}

/** Variables for a `PATCH /reports/{id}/share-settings` update. */
export interface UpdateShareSettingsInput {
  readonly reportId: string;
  readonly include_evidence_appendix?: boolean;
  readonly visible_to_student?: boolean;
  readonly allow_download?: boolean;
}

/**
 * PATCH `/reports/{id}/share-settings` — persist the export-share flags. Only
 * the supplied flags are sent.
 */
export function useReportShareSettings(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  return useMutation<ReportShareSettings, Error, UpdateShareSettingsInput>({
    mutationFn: ({ reportId, ...rest }) => {
      const body: Record<string, unknown> = {};
      if (rest.include_evidence_appendix !== undefined)
        body.include_evidence_appendix = rest.include_evidence_appendix;
      if (rest.visible_to_student !== undefined)
        body.visible_to_student = rest.visible_to_student;
      if (rest.allow_download !== undefined)
        body.allow_download = rest.allow_download;
      return authedWrite<ReportShareSettings>(
        getToken,
        `/reports/${reportId}/share-settings`,
        "PATCH",
        body
      );
    },
    onSuccess: (_data, { reportId }) =>
      invalidateReports(queryClient, courseId, reportId),
  });
}

// ----- student reads (enrollment-scoped) -----

/**
 * GET `/users/me/courses/{id}/reports` — the caller's own SENT reports only
 * (`audience='student' AND status='sent'`, backend B7). A `draft`/`reviewed`
 * report is invisible. Enrollment-scoped; a non-enrolled caller 403s.
 */
export function useMyReports(courseId: string) {
  return useAuthedQuery<readonly ReportResponse[]>({
    queryKey: reportKeys.myList(courseId),
    path: `/users/me/courses/${courseId}/reports`,
    enabled: Boolean(courseId),
  });
}

/**
 * GET `/users/me/reports/{id}` — the caller's own sent report detail (404 for
 * another student's report; owner-isolation RLS + the sent-only filter).
 */
export function useMyReport(reportId: string | null) {
  return useAuthedQuery<ReportResponse>({
    queryKey: reportKeys.myDetail(reportId ?? ""),
    path: `/users/me/reports/${reportId}`,
    enabled: Boolean(reportId),
  });
}
