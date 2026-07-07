"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/hooks/use-auth";
import { useAuthedQuery } from "@/hooks/use-authed-query";
import type { CourseResponse } from "@/hooks/use-courses";
import { ApiError, apiFetch, type ApiEnvelope } from "@/lib/api";

/**
 * Student enrollment hooks (P2 Task 5 endpoints). `enroll-by-code` is the
 * terminal join action; `lookup` is the non-committing resolver the join
 * funnel uses to branch a typed code before the student invests in the
 * readiness survey. The teacher-side join-request approve/deny mutations
 * (T033) are deferred to Task 15; the read-only `useRoster` list query below
 * is shared by the T029 overview stat (Task 13) and the T032 roster detail
 * (Task 14).
 */

// ----- enroll-by-code -----

/**
 * Result of a join-by-code attempt (mirrors backend `EnrollByCodeResult`). The
 * endpoint used to return a bare `CourseResponse`; it now wraps it so the
 * funnel can branch on `enrollment_status` (`active` → workspace/S013,
 * `pending` → awaits teacher approval).
 */
export interface EnrollByCodeResult {
  readonly course: CourseResponse;
  readonly enrollment_status: string;
}

/**
 * POST `/courses/enroll-by-code` — the terminal student join. Returns
 * `{ course, enrollment_status }`. Callers MUST read `data.course.id` (not
 * `data.id`) and branch on `data.enrollment_status`: never route a `pending`
 * student into the workspace (they can't read it until approved).
 */
export function useEnrollByCode() {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation<EnrollByCodeResult, Error, string>({
    mutationFn: async (enrollCode: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<EnrollByCodeResult>>(
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

// ----- roster (read-only) -----

/** An active enrollment row + user info (mirrors backend `RosterEntryOut`). */
export interface RosterEntry {
  readonly enrollment_id: string;
  readonly user_id: string;
  readonly full_name: string | null;
  readonly email: string;
  readonly role: string;
  readonly enrolled_at: string;
  readonly status: string;
}

/**
 * GET `/courses/{id}/roster` — active enrollments (students + instructors) for
 * an owned course. Read-only list used by the teacher course overview
 * (enrolled-student count) and the roster detail screen. The approve/deny
 * mutations that mutate join requests live with the T033 screen (Task 15).
 */
export function useRoster(courseId: string) {
  return useAuthedQuery<readonly RosterEntry[]>({
    queryKey: ["roster", courseId],
    path: `/courses/${courseId}/roster`,
    enabled: Boolean(courseId),
  });
}

// ----- join requests (read-only) -----

/**
 * A pending (or decided) join request + requesting student's info (mirrors
 * backend `JoinRequestOut`). `requested_at` mirrors the enrollment row's
 * `enrolled_at`; `status` is `pending` in the list, or the post-decision
 * status echoed back by approve/deny (Task 15).
 */
export interface JoinRequest {
  readonly enrollment_id: string;
  readonly user_id: string;
  readonly full_name: string | null;
  readonly email: string;
  readonly requested_at: string;
  readonly status: string;
}

/**
 * GET `/courses/{id}/join-requests` — pending join requests for an owned
 * `code_plus_approval` course. Read-only here: it backs the pending-count on
 * the enrollment overview (T031). The approve/deny mutations that act on this
 * list live with the T033 join-request-approval screen (Task 15), which reuses
 * this same query key so a decision invalidates both it and `["roster"]`.
 */
export function useJoinRequests(courseId: string) {
  return useAuthedQuery<readonly JoinRequest[]>({
    queryKey: ["join-requests", courseId],
    path: `/courses/${courseId}/join-requests`,
    enabled: Boolean(courseId),
  });
}

// ----- join-request approve / deny (T033) -----

/**
 * Shared query-key helpers so the approval screen invalidates exactly the two
 * lists a decision mutates: the pending `join-requests` list (the row leaves it)
 * and the `roster` (an approve adds the student as an active enrollment).
 */
export const enrollmentKeys = {
  joinRequests: (courseId: string) => ["join-requests", courseId] as const,
  roster: (courseId: string) => ["roster", courseId] as const,
};

/**
 * True when a decision failed because the request was already approved/denied
 * by someone else (backend 409 `NOT_PENDING`). The UI treats this as benign:
 * the list is simply stale, so it refetches rather than surfacing an error.
 */
export function isNotPendingError(error: unknown): boolean {
  return error instanceof ApiError && error.code === "NOT_PENDING";
}

/**
 * Factory for the approve/deny mutations — both POST to a decision endpoint,
 * return the decided `JoinRequest`, and invalidate the join-requests + roster
 * queries so an approved student appears in the roster and both leave the
 * pending list. Invalidate-on-settle (not optimistic): a decision also has a
 * server-side gate (`NOT_PENDING`) whose outcome the caller must observe, so we
 * revalidate from the server rather than guess. Mirrors the use-setup mutation
 * idiom (getToken → apiFetch → invalidate).
 */
function useDecideJoinRequest(courseId: string, decision: "approve" | "deny") {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation<JoinRequest, Error, string>({
    mutationFn: async (enrollmentId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<JoinRequest>>(
        `/courses/${courseId}/join-requests/${enrollmentId}/${decision}`,
        { method: "POST", token }
      );
      return response.data;
    },
    onSettled: () => {
      queryClient.invalidateQueries({
        queryKey: enrollmentKeys.joinRequests(courseId),
      });
      queryClient.invalidateQueries({
        queryKey: enrollmentKeys.roster(courseId),
      });
    },
  });
}

/**
 * POST `/courses/{id}/join-requests/{enrollment_id}/approve` — move a pending
 * enrollment to `active` (the student joins the roster). Invalidates both the
 * pending list and the roster on settle.
 */
export function useApproveJoinRequest(courseId: string) {
  return useDecideJoinRequest(courseId, "approve");
}

/**
 * POST `/courses/{id}/join-requests/{enrollment_id}/deny` — move a pending
 * enrollment to `rejected` (the row leaves the pending list; never enters the
 * roster). Invalidates both lists on settle.
 */
export function useDenyJoinRequest(courseId: string) {
  return useDecideJoinRequest(courseId, "deny");
}

// ----- typed join errors -----

/**
 * Why a join / code lookup was refused, mapped from the backend's typed gate
 * codes so the UI renders the matching state instead of a generic toast:
 * - `invalid`  → unknown/malformed code (404 or `JOIN_CODE_INVALID`) → S004
 * - `inactive` → `JOIN_CODE_INACTIVE` (deactivated code) → S004
 * - `not_open` → `SETUP_NOT_OPEN` (teacher hasn't published setup) → S012
 * - `unknown`  → anything else (network/auth/server)
 */
export type JoinErrorReason = "invalid" | "inactive" | "not_open" | "unknown";

export function joinErrorReason(error: unknown): JoinErrorReason {
  if (error instanceof ApiError) {
    if (error.code === "JOIN_CODE_INACTIVE") return "inactive";
    if (error.code === "SETUP_NOT_OPEN") return "not_open";
    if (error.code === "JOIN_CODE_INVALID" || error.status === 404) {
      return "invalid";
    }
  }
  return "unknown";
}

// ----- code lookup (S003 branch) -----

/** Non-committing resolve of a join code (mirrors backend `CourseLookupResult`). */
export interface CourseLookup {
  readonly course_id: string;
  readonly name: string;
  readonly is_open: boolean;
  readonly join_mode: string;
  readonly code_active: boolean;
}

/**
 * GET `/courses/lookup?code=` as a mutation — the funnel triggers it on submit
 * and branches on the result (or a 404). Kept as a mutation (not a query) so a
 * resubmit always re-resolves and the funnel drives navigation from the
 * awaited result rather than a cached value.
 */
export function useLookupCode() {
  const { getToken } = useAuth();

  return useMutation<CourseLookup, Error, string>({
    mutationFn: async (code: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<CourseLookup>>(
        `/courses/lookup?code=${encodeURIComponent(code)}`,
        { token }
      );
      return response.data;
    },
  });
}

// ----- pure branch helpers (unit-tested) -----

/** How S003 should react to a code the student typed. */
export type CodeBranch =
  | { readonly kind: "advance"; readonly courseId: string; readonly lookup: CourseLookup }
  | { readonly kind: "invalid"; readonly reason: "inactive" };

/**
 * Pure branch from a successful lookup: a deactivated code routes to S004
 * (inactive); an active code advances the funnel. A 404 (unknown/malformed
 * code) surfaces as a thrown `ApiError` on the mutation, not here — the caller
 * maps that to `invalid` via `joinErrorReason`.
 */
export function branchFromLookup(lookup: CourseLookup): CodeBranch {
  if (!lookup.code_active) return { kind: "invalid", reason: "inactive" };
  return { kind: "advance", courseId: lookup.course_id, lookup };
}

/** Terminal outcome of a successful `enroll-by-code` (Task 12). */
export type EnrollBranch =
  | { readonly kind: "active"; readonly course: CourseResponse }
  | { readonly kind: "pending"; readonly course: CourseResponse };

/**
 * Pure branch from a successful enroll result — the single authority both the
 * join funnel (S013 / pending-approval) and `JoinCourseDialog` use so they
 * behave identically. `active` → the workspace is readable (S013 success);
 * `pending` → awaiting instructor approval, and the caller MUST NOT route the
 * student into the workspace (a `code_plus_approval` course is unreadable until
 * approved). Gate ERRORS (SETUP_NOT_OPEN / JOIN_CODE_INACTIVE) are thrown, not
 * returned — map those with `joinErrorReason`.
 */
export function branchFromEnroll(result: EnrollByCodeResult): EnrollBranch {
  if (result.enrollment_status === "pending") {
    return { kind: "pending", course: result.course };
  }
  return { kind: "active", course: result.course };
}
