"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Trophy, Medal, Award } from "lucide-react";
import type { LeaderboardEntry } from "@/hooks/use-live-quiz";

interface PodiumProps {
  readonly leaderboard: readonly LeaderboardEntry[];
}

const RANK_STYLES: Record<number, { bg: string; text: string; icon: React.ReactNode }> = {
  1: {
    bg: "bg-[oklch(90%_0.1_85)]",
    text: "text-[oklch(55%_0.15_85)]",
    icon: <Trophy className="size-6" />,
  },
  2: {
    bg: "bg-[oklch(93%_0.02_260)]",
    text: "text-[oklch(50%_0.05_260)]",
    icon: <Medal className="size-5" />,
  },
  3: {
    bg: "bg-[oklch(90%_0.06_55)]",
    text: "text-[oklch(50%_0.1_55)]",
    icon: <Award className="size-5" />,
  },
};

const PODIUM_HEIGHTS = ["h-28", "h-20", "h-16"];

export function Podium({ leaderboard }: PodiumProps) {
  const top3 = leaderboard.slice(0, 3);
  const rest = leaderboard.slice(3);

  // Reorder for podium display: 2nd, 1st, 3rd
  const podiumOrder = [top3[1], top3[0], top3[2]].filter(Boolean);

  return (
    <div className="space-y-6">
      {/* Podium visualization */}
      {top3.length > 0 && (
        <Card>
          <CardHeader className="text-center">
            <CardTitle className="flex items-center justify-center gap-2">
              <Trophy className="size-5 text-[oklch(55%_0.15_85)]" />
              Final Results
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-end justify-center gap-3 pb-4">
              {podiumOrder.map((entry, visualIndex) => {
                if (!entry) return null;
                const rank = entry.rank;
                const style = RANK_STYLES[rank] ?? {
                  bg: "bg-[var(--color-surface-hover)]",
                  text: "text-[var(--color-text-muted)]",
                  icon: null,
                };

                return (
                  <div
                    key={entry.user_id ?? `rank-${entry.rank}`}
                    className="flex flex-col items-center gap-2"
                  >
                    {/* Player info */}
                    <div className={`flex size-12 items-center justify-center rounded-full ${style.bg} ${style.text}`}>
                      {style.icon}
                    </div>
                    <p className="max-w-[100px] truncate text-center text-sm font-semibold text-[var(--color-text)]">
                      {entry.display_name ??
                        entry.full_name ??
                        (entry.user_id
                          ? `Player ${entry.user_id.slice(0, 4)}`
                          : `#${entry.rank}`)}
                    </p>
                    <p className="text-xs font-medium text-[var(--color-primary)]">
                      {entry.score.toLocaleString()} pts
                    </p>

                    {/* Podium block */}
                    <div
                      className={`w-24 rounded-t-[var(--radius-md)] ${style.bg} ${PODIUM_HEIGHTS[rank - 1] ?? "h-12"} flex items-center justify-center`}
                    >
                      <span className={`text-xl font-bold ${style.text}`}>
                        #{rank}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Full leaderboard */}
      {rest.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Full Leaderboard</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {rest.map((entry) => (
              <div
                key={entry.user_id ?? `rank-${entry.rank}`}
                className="flex items-center gap-3 rounded-[var(--radius-md)] px-2 py-2 hover:bg-[var(--color-surface-hover)]"
              >
                <span className="flex size-7 items-center justify-center text-sm font-medium text-[var(--color-text-muted)]">
                  {entry.rank}
                </span>
                <span className="flex-1 truncate text-sm font-medium text-[var(--color-text)]">
                  {entry.display_name ??
                    entry.full_name ??
                    (entry.user_id
                      ? `Player ${entry.user_id.slice(0, 4)}`
                      : `#${entry.rank}`)}
                </span>
                <span className="text-sm font-semibold text-[var(--color-primary)]">
                  {entry.score.toLocaleString()} pts
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
