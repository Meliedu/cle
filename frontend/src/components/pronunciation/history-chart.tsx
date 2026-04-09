"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { History } from "lucide-react";
import { usePronunciationHistory } from "@/hooks/use-pronunciation";
import type { PronunciationHistoryEntry } from "@/hooks/use-pronunciation";

interface HistoryChartProps {
  readonly courseId: string;
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function getBarColor(score: number): string {
  if (score >= 80) return "var(--color-success)";
  if (score >= 60) return "var(--color-warning)";
  return "var(--color-error)";
}

function HistoryBar({
  entry,
  maxScore,
}: {
  readonly entry: PronunciationHistoryEntry;
  readonly maxScore: number;
}) {
  const heightPercent = maxScore > 0 ? (entry.overall_score / maxScore) * 100 : 0;

  return (
    <div className="flex flex-1 flex-col items-center gap-1.5">
      {/* Bar container */}
      <div className="flex h-32 w-full items-end justify-center">
        <div
          className="w-full max-w-[28px] rounded-t-[var(--radius-sm)] transition-all duration-[var(--duration-normal)]"
          style={{
            height: `${Math.max(heightPercent, 4)}%`,
            backgroundColor: getBarColor(entry.overall_score),
            opacity: 0.85,
          }}
          title={`${entry.target_text} - Score: ${Math.round(entry.overall_score)}`}
        />
      </div>
      {/* Score label */}
      <span
        className="text-xs font-semibold tabular-nums"
        style={{ color: "var(--color-text)" }}
      >
        {Math.round(entry.overall_score)}
      </span>
      {/* Date label */}
      <span
        className="max-w-[48px] truncate text-center text-[10px]"
        style={{ color: "var(--color-text-muted)" }}
      >
        {formatDate(entry.created_at)}
      </span>
    </div>
  );
}

export function HistoryChart({ courseId }: HistoryChartProps) {
  const { data: history, isLoading, error } = usePronunciationHistory(courseId);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <History className="size-4" />
            Practice History
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-end gap-2">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton
                key={i}
                className="flex-1 rounded-t-[var(--radius-sm)]"
                style={{ height: `${40 + Math.random() * 60}%`, minHeight: 32 }}
              />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <History className="size-4" />
            Practice History
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm" style={{ color: "var(--color-error)" }}>
            {error instanceof Error
              ? error.message
              : "Failed to load history"}
          </p>
        </CardContent>
      </Card>
    );
  }

  const entries = history ?? [];
  // Show the most recent 20, reversed so oldest is on the left
  const recent = entries.slice(0, 20).toReversed();
  const maxScore = recent.reduce(
    (max, e) => Math.max(max, e.overall_score),
    100
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <History className="size-4" />
          Practice History
          {recent.length > 0 && (
            <span
              className="ml-auto text-xs font-normal"
              style={{ color: "var(--color-text-muted)" }}
            >
              Last {recent.length} attempts
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {recent.length === 0 ? (
          <div className="flex flex-col items-center py-8 text-center">
            <History
              className="mb-2 size-8"
              style={{ color: "var(--color-text-muted)" }}
            />
            <p
              className="text-sm"
              style={{ color: "var(--color-text-muted)" }}
            >
              No practice history yet. Record your first attempt above!
            </p>
          </div>
        ) : (
          <div className="flex items-end gap-1 overflow-x-auto pb-1">
            {recent.map((entry) => (
              <HistoryBar
                key={entry.id}
                entry={entry}
                maxScore={maxScore}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
