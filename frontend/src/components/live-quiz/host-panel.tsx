"use client";

import { useEffect, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  ChevronRight,
  Square,
  Users,
  Clock,
  HelpCircle,
} from "lucide-react";
import { AnswerDistribution } from "@/components/live-quiz/answer-distribution";
import type {
  QuestionMessage,
  LeaderboardEntry,
  LiveStatus,
  ReviewMode,
} from "@/hooks/use-live-quiz";

interface QuestionData {
  readonly question_text: string;
  readonly options: Record<string, string> | null;
  readonly correct_answer?: string;
}

interface HostPanelProps {
  readonly status: LiveStatus;
  readonly currentQuestion: QuestionMessage | null;
  readonly questionData?: QuestionData;
  readonly leaderboard: readonly LeaderboardEntry[];
  readonly participantCount: number;
  readonly totalQuestions: number;
  readonly answerDistribution: Record<string, number>;
  readonly elapsedSeconds: number;
  readonly reviewMode: ReviewMode;
  readonly onNextQuestion: () => void;
  readonly onEndSession: () => void;
}

export function HostPanel({
  status,
  currentQuestion,
  questionData,
  leaderboard,
  participantCount,
  totalQuestions,
  answerDistribution,
  elapsedSeconds,
  reviewMode,
  onNextQuestion,
  onEndSession,
}: HostPanelProps) {
  /* Server-anchored timer: use elapsed from /state, not a client-only counter.
   * That way host and students agree on when time is up even if React re-renders
   * drift. */
  const timeRemaining = currentQuestion
    ? Math.max(0, Math.ceil(currentQuestion.time_limit - elapsedSeconds))
    : 0;

  const questionIndex = currentQuestion?.index ?? 0;
  const isLastQuestion = questionIndex >= totalQuestions - 1;
  const isTimeUp = !!currentQuestion && timeRemaining <= 0;

  /* Auto-advance in "final" review mode: the whole point is to finish the
   * quiz first then review at the end, so the host shouldn't have to click.
   * In per_question mode, hold on the reveal until the host clicks next. */
  const autoAdvancedRef = useRef<number>(-1);
  useEffect(() => {
    if (!currentQuestion) return;
    if (!isTimeUp) return;
    if (reviewMode !== "final") return;
    if (autoAdvancedRef.current === currentQuestion.index) return;
    autoAdvancedRef.current = currentQuestion.index;
    onNextQuestion();
  }, [currentQuestion, isTimeUp, reviewMode, onNextQuestion]);

  const optionKeys = questionData?.options
    ? Object.keys(questionData.options)
    : [];
  const totalAnswers = Object.values(answerDistribution).reduce(
    (a, b) => a + b,
    0
  );

  /* Per-question review: once time is up, reveal correct answer on the card. */
  const isRevealing = reviewMode === "per_question" && isTimeUp;
  const revealCorrect = isRevealing ? questionData?.correct_answer : undefined;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Badge
          variant="outline"
          className={
            status === "active"
              ? "border-[var(--color-success)] text-[var(--color-success)]"
              : "border-[var(--color-warning)] text-[var(--color-warning)]"
          }
        >
          {status === "active" ? "Live" : status}
        </Badge>

        <Badge variant="outline" className="text-[var(--color-text-muted)]">
          {reviewMode === "per_question"
            ? "Review after each"
            : "Review at the end"}
        </Badge>

        <div className="flex items-center gap-1 text-sm text-[var(--color-text-muted)]">
          <Users className="size-3.5" />
          <span>{participantCount} participants</span>
        </div>

        <div className="flex items-center gap-1 text-sm text-[var(--color-text-muted)]">
          <HelpCircle className="size-3.5" />
          <span>
            Q{questionIndex + 1} / {totalQuestions}
          </span>
        </div>

        {currentQuestion && (
          <div className="flex items-center gap-1 text-sm">
            <Clock className="size-3.5" />
            <span
              className="font-mono font-semibold"
              style={{
                color:
                  timeRemaining > 10
                    ? "var(--color-success)"
                    : timeRemaining > 5
                      ? "var(--color-warning)"
                      : "var(--color-error)",
              }}
            >
              {timeRemaining}s
            </span>
          </div>
        )}
      </div>

      {questionData && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Question {questionIndex + 1}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-[var(--color-text)]">
              {questionData.question_text}
            </p>
            {questionData.options && (
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(questionData.options).map(([key, value]) => (
                  <div
                    key={key}
                    className={`rounded-[var(--radius-md)] border px-3 py-2 text-sm ${
                      questionData.correct_answer === key
                        ? "border-[var(--color-success)] bg-[var(--color-success-light)] font-medium text-[var(--color-success)]"
                        : "border-[var(--color-border)] text-[var(--color-text-secondary)]"
                    }`}
                  >
                    <span className="font-semibold">{key}:</span> {value}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {optionKeys.length > 0 && (
        <AnswerDistribution
          distribution={answerDistribution}
          optionKeys={optionKeys}
          correctAnswer={revealCorrect ?? questionData?.correct_answer}
          totalAnswers={totalAnswers}
        />
      )}

      {leaderboard.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Top Players</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {leaderboard.slice(0, 5).map((entry) => (
              <div
                key={entry.user_id}
                className="flex items-center gap-3 rounded-[var(--radius-md)] px-2 py-1.5"
              >
                <span className="flex size-6 items-center justify-center text-xs font-bold text-[var(--color-text-muted)]">
                  #{entry.rank}
                </span>
                <span className="flex-1 truncate text-sm text-[var(--color-text)]">
                  {entry.display_name ??
                    entry.full_name ??
                    `Player ${entry.user_id.slice(0, 4)}`}
                </span>
                <span className="text-sm font-semibold text-[var(--color-primary)]">
                  {entry.score.toLocaleString()}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <div className="flex gap-3">
        <Button
          className="flex-1"
          onClick={onNextQuestion}
          disabled={status !== "active"}
        >
          {isRevealing
            ? isLastQuestion
              ? "Show Results"
              : "Next Question"
            : isLastQuestion
              ? "Show Results"
              : "Next Question"}
          <ChevronRight className="size-4" />
        </Button>
        <Button variant="destructive" onClick={onEndSession}>
          <Square className="size-4" />
          End Quiz
        </Button>
      </div>
    </div>
  );
}
