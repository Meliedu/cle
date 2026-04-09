import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@clerk/nextjs";
import { apiFetch } from "@/lib/api";

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

export type LiveStatus =
  | "connecting"
  | "connected"
  | "waiting"
  | "active"
  | "finished"
  | "error";

interface ApiEnvelope<T> {
  readonly success: boolean;
  readonly data: T;
}

/* ------------------------------------------------------------------ */
/*  WebSocket message types from backend                               */
/* ------------------------------------------------------------------ */

interface WsQuestionMsg {
  readonly type: "question";
  readonly index: number;
  readonly time_limit: number;
}

interface WsAnswerReceivedMsg {
  readonly type: "answer_received";
  readonly user_id: string;
  readonly leaderboard: readonly LeaderboardEntry[];
}

interface WsSessionEndedMsg {
  readonly type: "session_ended";
  readonly final_leaderboard: readonly LeaderboardEntry[];
}

interface WsErrorMsg {
  readonly type: "error";
  readonly message: string;
}

type WsMessage =
  | WsQuestionMsg
  | WsAnswerReceivedMsg
  | WsSessionEndedMsg
  | WsErrorMsg;

/* ------------------------------------------------------------------ */
/*  Helper: derive WS URL from API URL                                 */
/* ------------------------------------------------------------------ */

function getWsUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_WS_URL;
  if (explicit) return explicit;

  const apiUrl =
    process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
  return apiUrl
    .replace(/^https:/, "wss:")
    .replace(/^http:/, "ws:")
    .replace(/\/api$/, "");
}

/* ------------------------------------------------------------------ */
/*  useLiveQuiz — WebSocket hook                                       */
/* ------------------------------------------------------------------ */

export function useLiveQuiz(sessionId: string, token: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<LiveStatus>("connecting");
  const [currentQuestion, setCurrentQuestion] =
    useState<QuestionMessage | null>(null);
  const [leaderboard, setLeaderboard] = useState<readonly LeaderboardEntry[]>(
    []
  );
  const [participantCount, setParticipantCount] = useState(0);
  const [error, setError] = useState<string | null>(null);

  /* Connect / disconnect lifecycle */
  useEffect(() => {
    if (!sessionId || !token) return;

    const wsUrl = `${getWsUrl()}/live/${sessionId}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus("connected");
      setError(null);
    };

    ws.onmessage = (event) => {
      const msg: WsMessage = JSON.parse(event.data);

      switch (msg.type) {
        case "question":
          setStatus("active");
          setCurrentQuestion({ index: msg.index, time_limit: msg.time_limit });
          break;

        case "answer_received":
          setLeaderboard(msg.leaderboard);
          setParticipantCount(msg.leaderboard.length);
          break;

        case "session_ended":
          setStatus("finished");
          setLeaderboard(msg.final_leaderboard);
          setCurrentQuestion(null);
          break;

        case "error":
          setError(msg.message);
          break;
      }
    };

    ws.onerror = () => {
      setStatus("error");
      setError("WebSocket connection failed");
    };

    ws.onclose = () => {
      if (status !== "finished") {
        setStatus("error");
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, token]);

  /* Send helpers */
  const send = useCallback((data: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  const sendAnswer = useCallback(
    (
      answer: string,
      userId: string,
      questionIndex: number,
      isCorrect: boolean,
      elapsedSeconds: number
    ) => {
      send({
        type: "answer",
        answer,
        user_id: userId,
        question_index: questionIndex,
        is_correct: isCorrect,
        elapsed_seconds: elapsedSeconds,
      });
    },
    [send]
  );

  const nextQuestion = useCallback(() => {
    send({ type: "next_question" });
  }, [send]);

  const endSession = useCallback(() => {
    send({ type: "end_session" });
  }, [send]);

  return {
    status,
    currentQuestion,
    leaderboard,
    participantCount,
    error,
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
      const token = await getToken();
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
        error.message.includes("401") ||
        error.message.includes("Unauthorized")
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
      const token = await getToken();
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
        error.message.includes("401") ||
        error.message.includes("Unauthorized")
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
      const token = await getToken();
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
