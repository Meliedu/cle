"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Trophy, RotateCcw, Clock, BarChart3 } from "lucide-react";
import type { EndResponse } from "@/hooks/use-revision";

interface SessionSummaryProps {
  readonly result: EndResponse;
  readonly onPlayAgain: () => void;
}

function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;

  if (minutes === 0) {
    return `${remainingSeconds}s`;
  }
  return `${minutes}m ${remainingSeconds}s`;
}

function ScoreGauge({ score }: { readonly score: number }) {
  // score is 0-5, map to percentage
  const percentage = Math.round((score / 5) * 100);
  const circumference = 2 * Math.PI * 40;
  const strokeOffset = circumference - (percentage / 100) * circumference;

  const gaugeColor =
    percentage >= 80
      ? "var(--color-success)"
      : percentage >= 50
        ? "var(--color-warning)"
        : "var(--color-error)";

  return (
    <div className="relative flex size-28 items-center justify-center">
      <svg
        className="absolute inset-0 -rotate-90"
        viewBox="0 0 100 100"
        aria-hidden="true"
      >
        <circle
          cx="50"
          cy="50"
          r="40"
          fill="none"
          stroke="var(--color-border)"
          strokeWidth="8"
        />
        <circle
          cx="50"
          cy="50"
          r="40"
          fill="none"
          stroke={gaugeColor}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={strokeOffset}
          className="transition-[stroke-dashoffset] duration-700 ease-[var(--ease-out)]"
        />
      </svg>
      <div className="text-center">
        <span
          className="text-2xl font-bold"
          style={{ color: gaugeColor }}
        >
          {score.toFixed(1)}
        </span>
        <span className="block text-xs text-[var(--color-text-muted)]">
          / 5.0
        </span>
      </div>
    </div>
  );
}

export function SessionSummary({ result, onPlayAgain }: SessionSummaryProps) {
  const difficultyEntries = Object.entries(result.scores_by_difficulty);

  return (
    <div data-testid="session-summary" className="mx-auto max-w-xl">
      <Card className="border-[var(--color-border)] bg-[var(--color-surface)]">
        <CardContent className="flex flex-col items-center py-10">
          {/* Trophy icon */}
          <div className="mb-4 flex size-16 items-center justify-center rounded-full bg-[oklch(96%_0.03_145)]">
            <Trophy className="size-8 text-[var(--color-success)]" />
          </div>

          <h2 className="text-[var(--text-2xl)] font-bold text-[var(--color-text)]">
            Session Complete!
          </h2>

          {/* Score gauge */}
          <div className="mt-6">
            <ScoreGauge score={result.average_score} />
            <p className="mt-2 text-center text-sm text-[var(--color-text-muted)]">
              Average Score
            </p>
          </div>

          {/* Stats row */}
          <div className="mt-8 flex w-full max-w-sm justify-around">
            <div className="flex flex-col items-center gap-1">
              <BarChart3 className="size-5 text-[var(--color-primary)]" />
              <span className="text-lg font-bold text-[var(--color-text)]">
                {result.items_answered}
              </span>
              <span className="text-xs text-[var(--color-text-muted)]">
                Items
              </span>
            </div>
            <div className="flex flex-col items-center gap-1">
              <Clock className="size-5 text-[var(--color-accent)]" />
              <span className="text-lg font-bold text-[var(--color-text)]">
                {formatDuration(result.duration_seconds)}
              </span>
              <span className="text-xs text-[var(--color-text-muted)]">
                Duration
              </span>
            </div>
          </div>

          {/* Per-difficulty breakdown */}
          {difficultyEntries.length > 0 && (
            <div className="mt-8 w-full max-w-sm space-y-3">
              <h3 className="text-sm font-semibold text-[var(--color-text)]">
                Scores by Difficulty
              </h3>
              <div className="space-y-2">
                {difficultyEntries.map(([difficulty, score]) => {
                  const percentage = Math.round((score / 5) * 100);
                  return (
                    <div key={difficulty} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="capitalize text-[var(--color-text-secondary)]">
                          {difficulty}
                        </span>
                        <span className="font-medium text-[var(--color-text)]">
                          {score.toFixed(1)}
                        </span>
                      </div>
                      <div className="h-2 w-full overflow-hidden rounded-full bg-[var(--color-border)]">
                        <div
                          className="h-full rounded-full transition-[width] duration-500 ease-[var(--ease-out)]"
                          style={{
                            width: `${percentage}%`,
                            backgroundColor:
                              percentage >= 80
                                ? "var(--color-success)"
                                : percentage >= 50
                                  ? "var(--color-warning)"
                                  : "var(--color-error)",
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Action button */}
          <div className="mt-8">
            <Button onClick={onPlayAgain}>
              <RotateCcw className="size-4" />
              Practice Again
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
