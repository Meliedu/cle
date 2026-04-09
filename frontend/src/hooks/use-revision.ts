"use client";

import { useState, useCallback, useRef } from "react";
import { useMutation } from "@tanstack/react-query";
import { useAuth } from "@clerk/nextjs";
import { apiFetch } from "@/lib/api";

// --- Types ---

export interface RevisionQuizItem {
  readonly pool_item_id: string;
  readonly content_type: "quiz";
  readonly question_text: string;
  readonly options: Record<string, string>;
}

export interface RevisionFlashcardItem {
  readonly pool_item_id: string;
  readonly content_type: "flashcard";
  readonly front: string;
  readonly back: string;
}

export interface RevisionSpeakingItem {
  readonly pool_item_id: string;
  readonly content_type: "speaking";
  readonly target_text: string;
  readonly language: string;
}

export type RevisionItem =
  | RevisionQuizItem
  | RevisionFlashcardItem
  | RevisionSpeakingItem;

export interface SessionStats {
  readonly items_answered: number;
  readonly accuracy: number;
  readonly current_streak: number;
}

interface StartResponse {
  readonly session_id: string;
  readonly status: "ready" | "preparing";
  readonly first_item: RevisionItem | null;
}

interface AnswerResponse {
  readonly score: number;
  readonly is_correct: boolean;
  readonly correct_answer: string;
  readonly explanation: string;
  readonly next_item: RevisionItem | null;
  readonly session_stats: SessionStats;
}

export interface EndResponse {
  readonly items_answered: number;
  readonly average_score: number;
  readonly scores_by_difficulty: Record<string, number>;
  readonly duration_seconds: number;
}

interface ApiEnvelope<T> {
  readonly success: boolean;
  readonly data: T;
}

// --- Mutation inputs ---

interface StartInput {
  readonly content_type?: string;
}

interface AnswerInput {
  readonly pool_item_id: string;
  readonly answer: string;
  readonly time_spent_ms?: number;
}

// --- Hook ---

export function useRevisionSession(courseId: string) {
  const { getToken } = useAuth();

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [currentItem, setCurrentItem] = useState<RevisionItem | null>(null);
  const [stats, setStats] = useState<SessionStats | null>(null);
  const [isPreparing, setIsPreparing] = useState(false);
  const [lastFeedback, setLastFeedback] = useState<AnswerResponse | null>(null);

  const advanceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const startMutation = useMutation({
    mutationFn: async (input: StartInput = {}): Promise<StartResponse> => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");

      const response = await apiFetch<ApiEnvelope<StartResponse>>(
        `/courses/${courseId}/revision/start`,
        {
          method: "POST",
          body: JSON.stringify({ content_type: input.content_type }),
          token,
        }
      );
      return response.data;
    },
    onSuccess: (data) => {
      setSessionId(data.session_id);
      setLastFeedback(null);
      setStats(null);

      if (data.status === "preparing") {
        setIsPreparing(true);
        setCurrentItem(null);
      } else {
        setIsPreparing(false);
        setCurrentItem(data.first_item);
      }
    },
  });

  const answerMutation = useMutation({
    mutationFn: async (input: AnswerInput): Promise<AnswerResponse> => {
      if (!sessionId) throw new Error("No active session");

      const token = await getToken();
      if (!token) throw new Error("Not authenticated");

      const response = await apiFetch<ApiEnvelope<AnswerResponse>>(
        `/revision/sessions/${sessionId}/answer`,
        {
          method: "POST",
          body: JSON.stringify(input),
          token,
        }
      );
      return response.data;
    },
    onSuccess: (data) => {
      setLastFeedback(data);
      setStats(data.session_stats);

      // Clear any previous pending advance timer
      if (advanceTimerRef.current) {
        clearTimeout(advanceTimerRef.current);
      }

      // Advance to next item after a brief delay so user can see feedback
      advanceTimerRef.current = setTimeout(() => {
        setCurrentItem(data.next_item);
        advanceTimerRef.current = null;
      }, 1500);
    },
  });

  const endMutation = useMutation({
    mutationFn: async (): Promise<EndResponse> => {
      if (!sessionId) throw new Error("No active session");

      const token = await getToken();
      if (!token) throw new Error("Not authenticated");

      const response = await apiFetch<ApiEnvelope<EndResponse>>(
        `/revision/sessions/${sessionId}/end`,
        {
          method: "POST",
          token,
        }
      );
      return response.data;
    },
    onSuccess: () => {
      // Clean up advance timer when session ends
      if (advanceTimerRef.current) {
        clearTimeout(advanceTimerRef.current);
        advanceTimerRef.current = null;
      }
      setCurrentItem(null);
      setLastFeedback(null);
    },
  });

  const startSession = useCallback(
    (contentType?: string) => {
      startMutation.mutate({ content_type: contentType });
    },
    [startMutation]
  );

  const submitAnswer = useCallback(
    (input: AnswerInput) => {
      answerMutation.mutate(input);
    },
    [answerMutation]
  );

  const endSession = useCallback(() => {
    endMutation.mutate();
  }, [endMutation]);

  return {
    startSession,
    submitAnswer,
    endSession,
    sessionId,
    currentItem,
    stats,
    lastFeedback,
    isPreparing,
    isLoading: answerMutation.isPending,
    isStarting: startMutation.isPending,
    endResult: endMutation.data ?? null,
    isEnding: endMutation.isPending,
  } as const;
}
