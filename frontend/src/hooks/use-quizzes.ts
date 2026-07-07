import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import {
  API_URL,
  ApiError,
  apiFetch,
  isAuthError,
  type ApiEnvelope,
} from "@/lib/api";

export type QuizPurpose = "after_class" | "live";

/**
 * The NEW practice-vs-graded axis (backend B1 `quizzes.assessment_purpose`,
 * CHECK `practice|graded`). Distinct from `purpose` (`after_class|live`, when
 * the quiz runs) and legacy `quiz_type`. The FE branches practice vs graded
 * flows on this.
 */
export type AssessmentPurpose = "practice" | "graded";

/** Shared score-policy enums (backend B1) — reused by activities (B8). */
export type GradingMode = "auto" | "manual" | "participation";
export type LateRule = "accept_late" | "reject_late" | "accept_with_flag";

/** The publish-settings block (backend B1) present on graded/score-bearing quizzes. */
export interface ScorePolicyFields {
  readonly score_bearing: boolean;
  readonly score_category_id: string | null;
  readonly points: number | null;
  readonly grading_mode: GradingMode | null;
  readonly late_rule: LateRule | null;
  readonly due_at: string | null;
  readonly close_at: string | null;
}

export interface QuestionResponse {
  readonly id: string;
  readonly question_index: number;
  readonly type: string;
  readonly question_text: string;
  readonly options: Record<string, string> | null;
  readonly correct_answer?: string;
  readonly explanation: string | null;
}

export interface QuizResponse extends ScorePolicyFields {
  readonly id: string;
  readonly course_id: string;
  readonly title: string;
  readonly description: string | null;
  readonly quiz_type: string;
  readonly purpose: QuizPurpose;
  readonly assessment_purpose: AssessmentPurpose;
  readonly folder_id: string | null;
  readonly is_published: boolean;
  readonly question_count: number;
  readonly created_at: string;
}

export interface QuizDetailResponse extends ScorePolicyFields {
  readonly id: string;
  readonly course_id: string;
  readonly title: string;
  readonly description: string | null;
  readonly quiz_type: string;
  readonly assessment_purpose: AssessmentPurpose;
  readonly is_published: boolean;
  readonly questions: readonly QuestionResponse[];
  readonly created_at: string;
}

export function useQuizzes(courseId: string, purpose?: QuizPurpose) {
  const { getToken, isSignedIn } = useAuth();

  return useQuery({
    queryKey: ["quizzes", courseId, purpose ?? "all"],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const qs = purpose ? `?purpose=${purpose}` : "";
      const response = await apiFetch<ApiEnvelope<QuizResponse[]>>(
        `/courses/${courseId}/quizzes${qs}`,
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

export interface ImportToLiveInput {
  readonly source_quiz_id: string;
  readonly question_ids: string[];
  readonly title: string;
}

export interface UpdateQuizInput {
  readonly quiz_id: string;
  readonly title?: string;
  readonly description?: string;
}

export function useUpdateQuiz(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();

  return useMutation({
    mutationFn: async (input: UpdateQuizInput) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const { quiz_id, ...body } = input;
      const response = await apiFetch<ApiEnvelope<QuizResponse>>(
        `/quizzes/${quiz_id}`,
        {
          token,
          method: "PUT",
          body: JSON.stringify(body),
        }
      );
      return response.data;
    },
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["quizzes", courseId, "live"] });
      qc.invalidateQueries({ queryKey: ["quizzes", courseId, "after_class"] });
      qc.invalidateQueries({ queryKey: ["quizzes", courseId, "all"] });
      qc.invalidateQueries({
        queryKey: ["quizzes", "detail", variables.quiz_id],
      });
    },
  });
}

export function useDeleteQuiz(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();

  return useMutation({
    mutationFn: async (quizId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await apiFetch<ApiEnvelope<null>>(`/quizzes/${quizId}`, {
        token,
        method: "DELETE",
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["quizzes", courseId, "live"] });
      qc.invalidateQueries({ queryKey: ["quizzes", courseId, "after_class"] });
      qc.invalidateQueries({ queryKey: ["quizzes", courseId, "all"] });
    },
  });
}

export function useImportQuestionsToLive(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();

  return useMutation({
    mutationFn: async (input: ImportToLiveInput) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<QuizResponse>>(
        `/courses/${courseId}/quizzes/import-to-live`,
        { token, method: "POST", body: JSON.stringify(input) }
      );
      return response.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["quizzes", courseId, "live"] });
      qc.invalidateQueries({ queryKey: ["quizzes", courseId, "all"] });
    },
  });
}

export function useQuiz(quizId: string) {
  const { getToken, isSignedIn } = useAuth();

  return useQuery({
    queryKey: ["quizzes", "detail", quizId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<QuizDetailResponse>>(
        `/quizzes/${quizId}`,
        { token }
      );
      return response.data;
    },
    enabled: isSignedIn === true && !!quizId,
    retry: (count, error) => {
      if (isAuthError(error)) return false;
      return count < 3;
    },
  });
}

/* ================================================================== */
/*  P5 B5/B8 — gated publish + SCORE_POLICY_INCOMPLETE mapping.        */
/* ================================================================== */

/**
 * Typed publish-gate failure. The backend raises 422 with a structured
 * `{code:"SCORE_POLICY_INCOMPLETE", message, missing:[...]}` body when a graded
 * quiz (or score-bearing activity) is published while missing a required score
 * field. The shared `apiFetch` envelope only surfaces `code`/`message`, so the
 * publish path reads the raw body to preserve `missing` for the FE's blocked
 * banner (F3/F4). Callers `err instanceof ScorePolicyError` to branch.
 */
export class ScorePolicyError extends Error {
  readonly code = "SCORE_POLICY_INCOMPLETE" as const;
  readonly status = 422 as const;
  readonly missing: readonly string[];

  constructor(message: string, missing: readonly string[]) {
    super(message);
    this.name = "ScorePolicyError";
    this.missing = missing;
  }
}

/**
 * POST a publish endpoint, preserving the structured `SCORE_POLICY_INCOMPLETE`
 * body. Uses a raw `fetch` (mirroring `apiFetch`'s token/header wiring) ONLY
 * because `apiFetch` discards the `missing[]` array on error. On a policy-gate
 * 422 it throws `ScorePolicyError`; any other failure re-uses the shared
 * `ApiError` shape so existing error handling still applies. Shared by the
 * quiz (B5) and activity (B8) publish hooks.
 */
export async function publishWithScoreGate<T>(
  getToken: (opts: { template: string }) => Promise<string | null>,
  path: string
): Promise<T> {
  const token = await getToken({ template: "backend" });
  if (!token) throw new Error("Not authenticated");

  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
  });

  if (!res.ok) {
    const payload: unknown = await res.json().catch(() => null);
    const detail =
      payload && typeof payload === "object"
        ? (payload as Record<string, unknown>).detail
        : null;
    if (detail && typeof detail === "object" && !Array.isArray(detail)) {
      const d = detail as Record<string, unknown>;
      if (d.code === "SCORE_POLICY_INCOMPLETE") {
        const missing = Array.isArray(d.missing)
          ? d.missing.filter((m): m is string => typeof m === "string")
          : [];
        throw new ScorePolicyError(
          typeof d.message === "string" ? d.message : "Score policy incomplete.",
          missing
        );
      }
      throw new ApiError(
        res.status,
        typeof d.message === "string" ? d.message : `Publish failed (HTTP ${res.status}).`,
        typeof d.message === "string" ? d.message : undefined,
        typeof d.code === "string" ? d.code : undefined
      );
    }
    throw new ApiError(res.status, `Publish failed (HTTP ${res.status}).`);
  }

  const json = (await res.json()) as ApiEnvelope<T>;
  return json.data;
}

/**
 * POST `/quizzes/{id}/publish` — the gated publish (backend B5). A `practice`
 * quiz publishes freely; a `graded` quiz missing score fields throws a
 * `ScorePolicyError` carrying `missing[]` (F3 maps it to a blocked banner).
 * Invalidates the course quiz lists + the quiz detail on success.
 */
export function usePublishQuiz(courseId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();

  return useMutation<QuizResponse, Error, string>({
    mutationFn: (quizId) =>
      publishWithScoreGate<QuizResponse>(getToken, `/quizzes/${quizId}/publish`),
    onSuccess: (_data, quizId) => {
      qc.invalidateQueries({ queryKey: ["quizzes", courseId, "live"] });
      qc.invalidateQueries({ queryKey: ["quizzes", courseId, "after_class"] });
      qc.invalidateQueries({ queryKey: ["quizzes", courseId, "all"] });
      qc.invalidateQueries({ queryKey: ["quizzes", "detail", quizId] });
    },
  });
}
