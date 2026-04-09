"use client";

import { useCallback } from "react";
import { Loader2, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useRevisionSession } from "@/hooks/use-revision";
import type { RevisionItem } from "@/hooks/use-revision";
import { ContentTypePicker } from "./content-type-picker";
import { QuizItem } from "./quiz-item";
import { FlashcardItem } from "./flashcard-item";
import { ItemFeedback } from "./item-feedback";
import { SessionStatsBar } from "./session-stats-bar";
import { SessionSummary } from "./session-summary";

interface RevisionPlayerProps {
  readonly courseId: string;
}

type PlayerState = "idle" | "preparing" | "playing" | "ended";

function getPlayerState(session: ReturnType<typeof useRevisionSession>): PlayerState {
  if (session.endResult) return "ended";
  if (session.isPreparing || session.isStarting) return "preparing";
  if (session.sessionId && session.currentItem) return "playing";
  if (session.sessionId && !session.currentItem && !session.endResult) {
    // Session started but no item yet (waiting for next item after answer)
    return "playing";
  }
  return "idle";
}

function ItemRenderer({
  item,
  onQuizAnswer,
  onFlashcardAnswer,
  isLoading,
}: {
  readonly item: RevisionItem;
  readonly onQuizAnswer: (params: { answer: string; time_taken_ms: number }) => void;
  readonly onFlashcardAnswer: (params: { quality: number; time_taken_ms: number }) => void;
  readonly isLoading: boolean;
}) {
  switch (item.content_type) {
    case "quiz":
      return (
        <QuizItem
          item={item}
          onAnswer={onQuizAnswer}
          disabled={isLoading}
        />
      );

    case "flashcard":
      return (
        <FlashcardItem
          item={item}
          onAnswer={onFlashcardAnswer}
        />
      );

    case "speaking":
      return (
        <div className="space-y-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <p className="text-sm font-medium text-[var(--color-text-muted)]">
            Speaking practice ({item.language})
          </p>
          <p className="text-center text-xl font-semibold leading-relaxed text-[var(--color-text)]">
            {item.target_text}
          </p>
          <p className="text-center text-sm text-[var(--color-text-muted)]">
            Audio input coming soon
          </p>
        </div>
      );
  }
}

export function RevisionPlayer({ courseId }: RevisionPlayerProps) {
  const session = useRevisionSession(courseId);
  const state = getPlayerState(session);

  const handleContentSelect = useCallback(
    (contentType: "quiz" | "flashcard" | "speaking") => {
      session.startSession(contentType);
    },
    [session]
  );

  const handleQuizAnswer = useCallback(
    (params: { answer: string; time_taken_ms: number }) => {
      if (!session.currentItem) return;
      session.submitAnswer({
        pool_item_id: session.currentItem.pool_item_id,
        answer: params.answer,
        time_spent_ms: params.time_taken_ms,
      });
    },
    [session]
  );

  const handleFlashcardAnswer = useCallback(
    (params: { quality: number; time_taken_ms: number }) => {
      if (!session.currentItem) return;
      session.submitAnswer({
        pool_item_id: session.currentItem.pool_item_id,
        answer: String(params.quality),
        time_spent_ms: params.time_taken_ms,
      });
    },
    [session]
  );

  const handlePlayAgain = useCallback(() => {
    // Reset by starting fresh from idle state
    // The hook will reset itself when a new session starts
    window.location.reload();
  }, []);

  if (state === "idle") {
    return <ContentTypePicker onSelect={handleContentSelect} />;
  }

  if (state === "preparing") {
    return (
      <div className="mx-auto flex max-w-xl flex-col items-center gap-4 py-16">
        <Loader2 className="size-8 animate-spin text-[var(--color-primary)]" />
        <p className="text-sm font-medium text-[var(--color-text-muted)]">
          Generating practice items...
        </p>
      </div>
    );
  }

  if (state === "ended" && session.endResult) {
    return (
      <SessionSummary
        result={session.endResult}
        onPlayAgain={handlePlayAgain}
      />
    );
  }

  // state === "playing"
  return (
    <div className="mx-auto max-w-2xl space-y-4">
      {session.stats && <SessionStatsBar stats={session.stats} />}

      {session.currentItem ? (
        <ItemRenderer
          item={session.currentItem}
          onQuizAnswer={handleQuizAnswer}
          onFlashcardAnswer={handleFlashcardAnswer}
          isLoading={session.isLoading}
        />
      ) : (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="size-6 animate-spin text-[var(--color-primary)]" />
        </div>
      )}

      {session.lastFeedback && (
        <ItemFeedback
          score={session.lastFeedback.score}
          isCorrect={session.lastFeedback.is_correct}
          correctAnswer={session.lastFeedback.correct_answer}
          explanation={session.lastFeedback.explanation}
        />
      )}

      <div className="flex justify-end pt-2">
        <Button
          variant="outline"
          onClick={session.endSession}
          disabled={session.isEnding}
        >
          <Square className="size-3.5" />
          {session.isEnding ? "Ending..." : "End Session"}
        </Button>
      </div>
    </div>
  );
}
