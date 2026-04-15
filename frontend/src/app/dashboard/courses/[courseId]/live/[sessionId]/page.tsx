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
import {
  useLiveQuiz,
  useLiveSession,
} from "@/hooks/use-live-quiz";
import { useQuiz } from "@/hooks/use-quizzes";

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
    error: wsError,
    sendAnswer,
    nextQuestion,
    endSession,
    setAnonymity,
  } = useLiveQuiz(sessionId, token);

  const isHost = session?.is_host ?? false;

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

  /* Get current question data from the quiz detail */
  const currentQuestionData =
    quizDetail?.questions?.[currentQuestion?.index ?? -1];

  const handleAnswer = (answer: string) => {
    if (!currentQuestion || !user?.id) return;
    const elapsed = Math.round((Date.now() - questionStartRef.current) / 1000);
    const isCorrect =
      currentQuestionData?.options != null &&
      answer === Object.keys(currentQuestionData.options)[0]; // Simplified — backend decides correctness
    sendAnswer(answer, user.id, currentQuestion.index, isCorrect, elapsed);
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
        <Podium leaderboard={leaderboard} />
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
          correctAnswer={
            reviewMode === "per_question"
              ? currentQuestionData?.correct_answer
              : undefined
          }
          onAnswer={handleAnswer}
        />
      )}
    </div>
  );
}
