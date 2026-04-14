import { useCallback, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@clerk/nextjs";
import { apiFetch, isAuthError } from "@/lib/api";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface LiveSessionResponse {
  readonly id: string;
  readonly quiz_id: string;
  readonly course_id: string;
  readonly host_id: string;
  readonly join_code: string;
  readonly status: string;
  readonly participant_count: number;
  readonly time_limit_seconds: number;
  readonly created_at: string;
  readonly is_host: boolean;
}

export interface LeaderboardEntry {
  readonly rank: number;
  readonly user_id: string;
  readonly score: number;
  readonly full_name?: string;
}

export interface QuestionMessage {
  readonly index: number;
  readonly time_limit: number;
}

export type LiveStatus = "connecting" | "connected" | "active" | "finished" | "error";

interface ApiEnvelope<T> {
  readonly success: boolean;
  readonly data: T;
}

interface LiveStateResponse {
  readonly status: string;
  readonly current_question_index: number;
  readonly time_limit: number;
  readonly leaderboard: readonly LeaderboardEntry[];
  readonly participant_count: number;
}

/* ------------------------------------------------------------------ */
/*  useLiveQuiz — polling-based hook                                   */
/* ------------------------------------------------------------------ */

const POLL_INTERVAL_MS = 1500;

export function useLiveQuiz(sessionId: string, token: string | null) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  /* Poll session state every 1.5s */
  const { data: state, error: pollError } = useQuery({
    queryKey: ["live-state", sessionId],
    queryFn: async () => {
      const t = await getToken({ template: "backend" });
      if (!t) throw new Error("Not authenticated");
      const res = await apiFetch<ApiEnvelope<LiveStateResponse>>(
        `/live-sessions/${sessionId}/state`,
        { token: t }
      );
      return res.data;
    },
    enabled: !!sessionId && !!token,
    refetchInterval: POLL_INTERVAL_MS,
    retry: 2,
  });

  const status: LiveStatus = !state
    ? "connecting"
    : state.status === "finished"
      ? "finished"
      : state.status === "active"
        ? "active"
        : "connected";

  /* Memoize so consumers depending on `currentQuestion` don't re-fire effects
   * every 1.5s poll — a new object literal each tick used to reset submitted
   * answer state in PlayerView and drive infinite score inflation. */
  const activeIndex =
    state?.status === "active" ? state.current_question_index : null;
  const activeTimeLimit =
    state?.status === "active" ? state.time_limit : null;
  const currentQuestion: QuestionMessage | null = useMemo(
    () =>
      activeIndex !== null && activeTimeLimit !== null
        ? { index: activeIndex, time_limit: activeTimeLimit }
        : null,
    [activeIndex, activeTimeLimit]
  );

  const leaderboard = state?.leaderboard ?? [];
  const participantCount = state?.participant_count ?? 0;

  /* Actions */
  const nextQuestionMut = useMutation({
    mutationFn: async () => {
      const t = await getToken({ template: "backend" });
      if (!t) throw new Error("Not authenticated");
      await apiFetch(`/live-sessions/${sessionId}/next-question`, {
        method: "POST",
        token: t,
      });
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["live-state", sessionId] }),
  });

  const answerMut = useMutation({
    mutationFn: async (body: {
      answer: string;
      user_id: string;
      question_index: number;
      is_correct: boolean;
      elapsed_seconds: number;
    }) => {
      const t = await getToken({ template: "backend" });
      if (!t) throw new Error("Not authenticated");
      await apiFetch(`/live-sessions/${sessionId}/answer`, {
        method: "POST",
        token: t,
        body: JSON.stringify(body),
      });
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["live-state", sessionId] }),
  });

  const endMut = useMutation({
    mutationFn: async () => {
      const t = await getToken({ template: "backend" });
      if (!t) throw new Error("Not authenticated");
      await apiFetch(`/live-sessions/${sessionId}/end`, {
        method: "POST",
        token: t,
      });
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["live-state", sessionId] }),
  });

  const sendAnswer = useCallback(
    (
      answer: string,
      userId: string,
      questionIndex: number,
      isCorrect: boolean,
      elapsedSeconds: number
    ) => {
      answerMut.mutate({
        answer,
        user_id: userId,
        question_index: questionIndex,
        is_correct: isCorrect,
        elapsed_seconds: elapsedSeconds,
      });
    },
    [answerMut]
  );

  const nextQuestion = useCallback(() => {
    nextQuestionMut.mutate();
  }, [nextQuestionMut]);

  const endSession = useCallback(() => {
    endMut.mutate();
  }, [endMut]);

  return {
    status,
    currentQuestion,
    leaderboard,
    participantCount,
    error: pollError?.message ?? null,
    sendAnswer,
    nextQuestion,
    endSession,
  } as const;
}

/* ------------------------------------------------------------------ */
/*  REST hooks                                                         */
/* ------------------------------------------------------------------ */

export function useLiveSessions(courseId: string) {
  const { getToken, isSignedIn } = useAuth();

  return useQuery({
    queryKey: ["live-sessions", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<LiveSessionResponse[]>>(
        `/courses/${courseId}/live-sessions`,
        { token }
      );
      return response.data;
    },
    enabled: isSignedIn === true && !!courseId,
    refetchInterval: 5000,
    retry: (count, error) => {
      if (
        isAuthError(error)
      )
        return false;
      return count < 3;
    },
  });
}

export function useLiveSession(sessionId: string) {
  const { getToken, isSignedIn } = useAuth();

  return useQuery({
    queryKey: ["live-sessions", "detail", sessionId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<LiveSessionResponse>>(
        `/live-sessions/${sessionId}`,
        { token }
      );
      return response.data;
    },
    enabled: isSignedIn === true && !!sessionId,
    retry: (count, error) => {
      if (
        isAuthError(error)
      )
        return false;
      return count < 3;
    },
  });
}

export function useCreateLiveSession(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (body: {
      quiz_id: string;
      time_limit_seconds?: number;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<LiveSessionResponse>>(
        `/courses/${courseId}/live-sessions`,
        {
          method: "POST",
          token,
          body: JSON.stringify(body),
        }
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["live-sessions", courseId],
      });
    },
  });
}

export function useDeleteLiveSession(courseId: string) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (sessionId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await apiFetch(`/live-sessions/${sessionId}`, {
        method: "DELETE",
        token,
      });
      return sessionId;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["live-sessions", courseId],
      });
    },
  });
}

export function useFindLiveSessionByCode() {
  const { getToken } = useAuth();

  return useMutation({
    mutationFn: async (code: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<ApiEnvelope<LiveSessionResponse>>(
        `/live-sessions/by-code/${encodeURIComponent(code.toUpperCase())}`,
        { token }
      );
      return response.data;
    },
  });
}
