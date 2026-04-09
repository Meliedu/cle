"use client";

import { Flame, Target, CheckCircle } from "lucide-react";

interface SessionStatsBarProps {
  readonly stats: {
    readonly items_answered: number;
    readonly accuracy: number;
    readonly current_streak: number;
  };
}

export function SessionStatsBar({ stats }: SessionStatsBarProps) {
  return (
    <div className="flex items-center justify-between rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2.5 shadow-[var(--shadow-sm)]">
      <div className="flex items-center gap-2">
        <CheckCircle className="size-4 text-[var(--color-primary)]" />
        <span className="text-sm text-[var(--color-text-muted)]">
          <span className="font-semibold text-[var(--color-text)]">
            {stats.items_answered}
          </span>{" "}
          answered
        </span>
      </div>

      <div className="flex items-center gap-2">
        <Target className="size-4 text-[var(--color-accent)]" />
        <span className="text-sm text-[var(--color-text-muted)]">
          <span className="font-semibold text-[var(--color-text)]">
            {Math.round(stats.accuracy)}%
          </span>{" "}
          accuracy
        </span>
      </div>

      <div className="flex items-center gap-2">
        <Flame
          className="size-4"
          style={{
            color:
              stats.current_streak > 0
                ? "var(--color-warning)"
                : "var(--color-text-muted)",
          }}
        />
        <span className="text-sm text-[var(--color-text-muted)]">
          <span className="font-semibold text-[var(--color-text)]">
            {stats.current_streak}
          </span>{" "}
          streak
        </span>
      </div>
    </div>
  );
}
