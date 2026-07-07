"use client";

import { useMutation } from "@tanstack/react-query";

import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";

/**
 * One graded question in an attempt response. `correct_answer` here is the
 * post-submit reveal (redacted only on the pre-attempt `GET /quizzes/{id}`); for
 * the new types it is the JSON-encoded key, so feedback leans on `is_correct` +
 * `explanation` rather than re-decoding it.
 */
export interface AttemptResultItem {
  readonly question_id: string;
  readonly question_text: string;
  readonly selected_answer: string;
  readonly correct_answer: string;
  readonly is_correct: boolean;
  readonly explanation: string | null;
}

export interface AttemptResponse {
  readonly id: string;
  readonly quiz_id: string;
  /** 0–100; Pydantic may serialize the Decimal as a string — coerce on display. */
  readonly score: number;
  readonly total_questions: number;
  readonly correct_count: number;
  readonly time_taken_seconds: number | null;
  readonly results: readonly AttemptResultItem[];
  readonly completed_at: string | null;
}

export interface SubmitAttemptInput {
  /** `{ "<question_id>": "<per-type encoded answer string>" }` (see `encodeAnswer`). */
  readonly answers: Record<string, string>;
  readonly time_taken_seconds: number;
}

/**
 * `POST /quizzes/{id}/attempt` — grades every question server-side and returns
 * per-question results. Shared by the practice runner (F7) and graded quiz
 * runner (F8); the two flows differ only in how they present the result, not in
 * how they submit. Co-located under `components/practice/` so the student track
 * owns it without touching the shared `use-quizzes.ts` hook surface.
 */
export function useSubmitAttempt(quizId: string) {
  const { getToken } = useAuth();

  return useMutation<AttemptResponse, Error, SubmitAttemptInput>({
    mutationFn: async (input) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<AttemptResponse>>(
        `/quizzes/${quizId}/attempt`,
        {
          method: "POST",
          token,
          body: JSON.stringify(input),
        }
      );
      return response.data;
    },
  });
}
