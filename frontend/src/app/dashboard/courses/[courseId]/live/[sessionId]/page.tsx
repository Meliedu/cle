"use client";

import { use, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useAuth, useUser } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowLeft } from "lucide-react";
import { Lobby } from "@/components/live-quiz/lobby";
import { HostPanel } from "@/components/live-quiz/host-panel";
import { PlayerView } from "@/components/live-quiz/player-view";
import { Podium } from "@/components/live-quiz/podium";
import { LiveReview } from "@/components/live-quiz/live-review";
import {
  useDeleteLiveSession,
  useLiveQuiz,
  useLiveReview,
  useLiveSession,
} from "@/hooks/use-live-quiz";
import { useQuiz } from "@/hooks/use-quizzes";
import { API_URL } from "@/lib/api";

/* React Strict Mode synthetically unmounts/remounts components within the
 * same microtask on first mount in dev. A real host leaving the page takes
 * at least this long. Sub-1s real unmounts skip cleanup — acceptable. */
const STRICT_MODE_DEBOUNCE_MS = 1000;

interface LiveSessionPageProps {
  params: Promise<{ courseId: string; sessionId: string }>;
}

export default function LiveSessionPage({ params }: LiveSessionPageProps) {
  const { courseId, sessionId } = use(params);
  const { getToken } = useAuth();
  const { user, isLoaded: userLoaded } = useUser();
  const [token, setToken] = useState<string | null>(null);

  /* Fetch the Clerk token for the WebSocket hook */
  useEffect(() => {
    let cancelled = false;
    getToken({ template: "backend" }).then((t) => {
      if (!cancelled) setToken(t);
    });
    return () => {
      cancelled = true;
    };
  }, [getToken]);

  /* REST data */
  const { data: session, isLoading: sessionLoading } =
    useLiveSession(sessionId);
  const { data: quizDetail } = useQuiz(session?.quiz_id ?? "");

  /* Polling connection */
  const {
    status,
    currentQuestion,
    leaderboard,
    participantCount,
    answerDistribution,
    elapsedSeconds,
    reviewMode,
    isAnonymous,
    currentReveal,
    error: wsError,
    sendAnswer,
    nextQuestion,
    endSession,
    setAnonymity,
  } = useLiveQuiz(sessionId, token);

  const isHost = session?.is_host ?? false;

  /* Per-question review is fetched once the session is finished — for both
   * roles. Hosts have the live host panel mid-session (no need to also pull
   * a stale review snapshot), and students are 403'd by the backend until
   * status="finished" anyway. Single fetch path keeps the staleTime:Infinity
   * cache valid for the whole session lifetime. */
  const {
    data: reviewData,
    isLoading: reviewLoading,
    error: reviewError,
  } = useLiveReview(sessionId, status === "finished");

  const joinUrl =
    typeof window !== "undefined"
      ? `${window.location.origin}/dashboard/courses/${courseId}/live/${sessionId}`
      : "";

  /* Track when each question arrives to compute elapsed answer time */
  const questionStartRef = useRef<number>(Date.now());
  useEffect(() => {
    if (currentQuestion) {
      questionStartRef.current = Date.now();
    }
  }, [currentQuestion]);

  /* Auto-delete the session when the host leaves a finished session so the
   * dashboard doesn't accumulate stale "done" sessions. Two cleanup paths:
   *  1. React unmount (client-side route change, e.g. clicking Back) — fires
   *     the TanStack mutation which goes through apiFetch.
   *  2. Tab close / external navigation (visibilitychange=hidden) — fires a
   *     keepalive fetch so the DELETE survives the document tearing down.
   *     sendBeacon doesn't support custom headers, so keepalive fetch is the
   *     only way to attach the Bearer token.
   * Guards:
   *  - host only (backend DELETE also enforces this; this avoids a pointless
   *    403 round-trip for students)
   *  - STRICT_MODE_DEBOUNCE_MS on the unmount path dodges React Strict Mode's
   *    synthetic unmount/remount cycle on first mount in dev. */
  const deleteSessionMut = useDeleteLiveSession(courseId);
  const deleteMutateRef = useRef(deleteSessionMut.mutate);
  deleteMutateRef.current = deleteSessionMut.mutate;
  const shouldDeleteOnLeaveRef = useRef(false);
  shouldDeleteOnLeaveRef.current = isHost && status === "finished";
  const tokenRef = useRef<string | null>(null);
  tokenRef.current = token;
  const mountTimeRef = useRef<number>(0);
  useEffect(() => {
    mountTimeRef.current = Date.now();

    /* Path 2: tab-close / external nav. visibilitychange fires before
     * pagehide on mobile Safari and is the most reliable "user leaving"
     * signal. keepalive: true tells the browser to complete the fetch even
     * as the document unloads. */
    const onHide = () => {
      if (document.visibilityState !== "hidden") return;
      if (!shouldDeleteOnLeaveRef.current) return;
      const t = tokenRef.current;
      if (!t) return;
      fetch(`${API_URL}/live-sessions/${sessionId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${t}` },
        keepalive: true,
      }).catch(() => {
        /* Unload context — the fetch either completed via keepalive or the
         * browser dropped it. Either way, nothing useful to do with the
         * error; suppress unhandled-rejection noise. */
      });
    };
    document.addEventListener("visibilitychange", onHide);

    return () => {
      document.removeEventListener("visibilitychange", onHide);
      /* Path 1: React unmount. */
      const mountedMs = Date.now() - mountTimeRef.current;
      if (
        shouldDeleteOnLeaveRef.current &&
        mountedMs > STRICT_MODE_DEBOUNCE_MS
      ) {
        deleteMutateRef.current(sessionId);
      }
    };
  }, [sessionId]);

  /* Get current question data from the quiz detail */
  const currentQuestionData =
    quizDetail?.questions?.[currentQuestion?.index ?? -1];

  const handleAnswer = (answer: string) => {
    if (!currentQuestion || !user?.id) return;
    const elapsed = Math.round((Date.now() - questionStartRef.current) / 1000);
    // Correctness and points are decided server-side; the client just sends
    // its raw answer.
    sendAnswer(answer, currentQuestion.index, elapsed);
  };

  /* Loading state */
  if (!userLoaded || sessionLoading) {
    return (
      <div className="mx-auto max-w-3xl space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 rounded-[var(--radius-lg)]" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link href={`/dashboard/courses/${courseId}/live`}>
          <Button variant="ghost" size="sm">
            <ArrowLeft className="size-4" />
            Back
          </Button>
        </Link>
        <h1 className="text-xl font-bold text-[var(--color-text)]">
          Live Quiz
        </h1>
        {session?.join_code && (
          <span className="ml-auto font-mono text-sm font-bold text-[var(--color-text-muted)]">
            {session.join_code}
          </span>
        )}
      </div>

      {/* Error display */}
      {wsError && (
        <div className="rounded-[var(--radius-md)] border border-[var(--color-error)] bg-[var(--color-error-light)] px-4 py-3 text-sm text-[var(--color-error)]">
          {wsError}
        </div>
      )}

      {/* Session state routing */}
      {status === "finished" ? (
        <div className="space-y-6">
          <Podium leaderboard={leaderboard} />
          {reviewData ? (
            <LiveReview
              questions={reviewData.questions}
              isHost={reviewData.is_host}
            />
          ) : reviewLoading ? (
            <div className="flex items-center justify-center py-8 text-sm text-[var(--color-text-muted)]">
              Loading question review…
            </div>
          ) : reviewError ? (
            <div className="rounded-[var(--radius-md)] border border-[var(--color-error)] bg-[var(--color-error-light)] px-4 py-3 text-sm text-[var(--color-error)]">
              Failed to load question review: {reviewError.message}
            </div>
          ) : null}
        </div>
      ) : status === "connecting" || status === "connected" ? (
        <Lobby
          joinCode={session?.join_code ?? "------"}
          joinUrl={joinUrl}
          participantCount={participantCount}
          isHost={isHost}
          status={status}
          isAnonymous={isAnonymous}
          onAnonymityChange={setAnonymity}
          onStart={nextQuestion}
        />
      ) : isHost ? (
        <HostPanel
          status={status}
          currentQuestion={currentQuestion}
          questionData={
            currentQuestionData
              ? {
                  question_text: currentQuestionData.question_text,
                  options: currentQuestionData.options,
                  correct_answer: currentQuestionData.correct_answer,
                }
              : undefined
          }
          leaderboard={leaderboard}
          participantCount={participantCount}
          totalQuestions={quizDetail?.questions?.length ?? 0}
          answerDistribution={answerDistribution}
          elapsedSeconds={elapsedSeconds}
          reviewMode={reviewMode}
          onNextQuestion={nextQuestion}
          onEndSession={endSession}
        />
      ) : (
        <PlayerView
          currentQuestion={currentQuestion}
          questionText={currentQuestionData?.question_text}
          options={currentQuestionData?.options ?? undefined}
          questionType={currentQuestionData?.type}
          elapsedSeconds={elapsedSeconds}
          // currentReveal is server-gated: only populated in per_question
          // mode and only after the server-side timer has elapsed, so this
          // can't leak the answer before "time's up".
          correctAnswer={currentReveal?.correct_answer}
          explanation={currentReveal?.explanation}
          onAnswer={handleAnswer}
        />
      )}
    </div>
  );
}
