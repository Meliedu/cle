"use client";

import { useState, useEffect } from "react";
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
  onNextQuestion,
  onEndSession,
}: HostPanelProps) {
  const [timeRemaining, setTimeRemaining] = useState(0);

  /* Timer countdown */
  useEffect(() => {
    if (!currentQuestion) return;
    setTimeRemaining(currentQuestion.time_limit);

    const interval = setInterval(() => {
      setTimeRemaining((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [currentQuestion]);

  const questionIndex = currentQuestion?.index ?? 0;
  const isLastQuestion = questionIndex >= totalQuestions - 1;

  /* Build answer distribution skeleton keyed by this question's actual option
   * keys so true_false (T/F) renders correctly, not hardcoded A/B/C/D. */
  const distribution: Record<string, number> = Object.fromEntries(
    Object.keys(questionData?.options ?? { A: "", B: "", C: "", D: "" }).map(
      (k) => [k, 0]
    )
  );
  const totalAnswers = leaderboard.length;

  return (
    <div className="space-y-4">
      {/* Top bar: status + stats */}
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

      {/* Question display */}
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

      {/* Answer distribution */}
      <AnswerDistribution
        distribution={distribution}
        correctAnswer={questionData?.correct_answer}
        totalAnswers={totalAnswers}
      />

      {/* Mini leaderboard */}
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
                  {entry.full_name ??
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

      {/* Action buttons */}
      <div className="flex gap-3">
        <Button
          className="flex-1"
          onClick={onNextQuestion}
          disabled={status !== "active"}
        >
          {isLastQuestion ? "Show Results" : "Next Question"}
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
