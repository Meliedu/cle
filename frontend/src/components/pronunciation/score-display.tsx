"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { PronunciationGradeResponse } from "@/hooks/use-pronunciation";

interface ScoreDisplayProps {
  readonly result: PronunciationGradeResponse | null;
}

function getWordColor(accuracy: number): string {
  if (accuracy >= 80) return "var(--color-success)";
  if (accuracy >= 60) return "var(--color-warning)";
  return "var(--color-error)";
}

function getWordBgColor(accuracy: number): string {
  if (accuracy >= 80) return "var(--color-success-light)";
  if (accuracy >= 60) return "var(--color-warning-light)";
  return "var(--color-error-light)";
}

function ScoreRing({
  score,
  size = 120,
  strokeWidth = 10,
}: {
  readonly score: number;
  readonly size?: number;
  readonly strokeWidth?: number;
}) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;

  const getScoreColor = (value: number): string => {
    if (value >= 80) return "var(--color-success)";
    if (value >= 60) return "var(--color-warning)";
    return "var(--color-error)";
  };

  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--color-border)"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={getScoreColor(score)}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className="transition-all duration-[var(--duration-slow)]"
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span
          className="text-2xl font-bold"
          style={{ color: getScoreColor(score) }}
        >
          {Math.round(score)}
        </span>
        <span
          className="text-xs"
          style={{ color: "var(--color-text-muted)" }}
        >
          Overall
        </span>
      </div>
    </div>
  );
}

interface BreakdownBarProps {
  readonly label: string;
  readonly score: number;
}

function BreakdownBar({ label, score }: BreakdownBarProps) {
  const getBarColor = (value: number): string => {
    if (value >= 80) return "var(--color-success)";
    if (value >= 60) return "var(--color-warning)";
    return "var(--color-error)";
  };

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span
          className="text-sm font-medium"
          style={{ color: "var(--color-text-secondary)" }}
        >
          {label}
        </span>
        <span
          className="text-sm font-semibold tabular-nums"
          style={{ color: "var(--color-text)" }}
        >
          {Math.round(score)}
        </span>
      </div>
      <div
        className="h-2 overflow-hidden rounded-full"
        style={{ backgroundColor: "var(--color-border)" }}
      >
        <div
          className="h-full rounded-full transition-all duration-[var(--duration-slow)]"
          style={{
            width: `${Math.min(score, 100)}%`,
            backgroundColor: getBarColor(score),
          }}
        />
      </div>
    </div>
  );
}

export function ScoreDisplay({ result }: ScoreDisplayProps) {
  if (!result) return null;

  return (
    <div className="space-y-4">
      {/* Overall Score + Breakdown */}
      <Card>
        <CardHeader>
          <CardTitle>Pronunciation Score</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-start">
            {/* Ring */}
            <div className="shrink-0">
              <ScoreRing score={result.overall_score} />
            </div>

            {/* Breakdown */}
            <div className="w-full flex-1 space-y-3">
              <BreakdownBar label="Accuracy" score={result.accuracy_score} />
              <BreakdownBar label="Fluency" score={result.fluency_score} />
              <BreakdownBar
                label="Completeness"
                score={result.completeness_score}
              />
              {result.prosody_score != null && (
                <BreakdownBar label="Prosody" score={result.prosody_score} />
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Word-level heatmap */}
      {result.word_scores.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Word Breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {result.word_scores.map((ws, index) => (
                <span
                  key={`${ws.word}-${index}`}
                  className="inline-flex items-center rounded-[var(--radius-md)] px-2.5 py-1 text-sm font-medium transition-transform duration-[var(--duration-fast)] hover:scale-105"
                  style={{
                    backgroundColor: getWordBgColor(ws.accuracy),
                    color: getWordColor(ws.accuracy),
                  }}
                  title={`${ws.word}: ${Math.round(ws.accuracy)}%${ws.error_type ? ` (${ws.error_type})` : ""}`}
                >
                  {ws.word}
                  <span className="ml-1.5 text-xs opacity-80">
                    {Math.round(ws.accuracy)}
                  </span>
                </span>
              ))}
            </div>
            {/* Legend */}
            <div
              className="mt-4 flex flex-wrap gap-4 border-t pt-3 text-xs"
              style={{ borderColor: "var(--color-border)" }}
            >
              <span className="flex items-center gap-1.5">
                <span
                  className="inline-block size-2.5 rounded-full"
                  style={{ backgroundColor: "var(--color-success)" }}
                />
                Good (80+)
              </span>
              <span className="flex items-center gap-1.5">
                <span
                  className="inline-block size-2.5 rounded-full"
                  style={{ backgroundColor: "var(--color-warning)" }}
                />
                Fair (60-80)
              </span>
              <span className="flex items-center gap-1.5">
                <span
                  className="inline-block size-2.5 rounded-full"
                  style={{ backgroundColor: "var(--color-error)" }}
                />
                Needs Work (&lt;60)
              </span>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
