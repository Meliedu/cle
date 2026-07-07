"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/hooks/use-auth";
import type { CourseResponse } from "@/hooks/use-courses";
import { ApiError, apiFetch, type ApiEnvelope } from "@/lib/api";

/**
 * Student enrollment hooks (P2 Task 5 endpoints). `enroll-by-code` is the
 * terminal join action; `lookup` is the non-committing resolver the join
 * funnel uses to branch a typed code before the student invests in the
 * readiness survey. Teacher-side join-request approve/deny + roster hooks are
 * deferred to Tasks 14/15 (their screens don't exist yet).
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
