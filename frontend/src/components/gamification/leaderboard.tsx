"use client";

import { useState } from "react";
import { useUser } from "@/hooks/use-auth";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar";
import { Trophy, ChevronLeft, ChevronRight } from "lucide-react";
import { useLeaderboard } from "@/hooks/use-progress";

interface LeaderboardProps {
  readonly courseId: string;
}

function rankBadge(rank: number): React.ReactNode {
  if (rank === 1) {
    return (
      <span className="flex size-7 items-center justify-center rounded-full bg-[oklch(90%_0.1_85)] text-sm font-bold text-[oklch(55%_0.15_85)]">
        1
      </span>
    );
  }
  if (rank === 2) {
    return (
      <span className="flex size-7 items-center justify-center rounded-full bg-[oklch(93%_0.02_260)] text-sm font-bold text-[oklch(50%_0.05_260)]">
        2
      </span>
    );
  }
  if (rank === 3) {
    return (
      <span className="flex size-7 items-center justify-center rounded-full bg-[oklch(90%_0.06_55)] text-sm font-bold text-[oklch(50%_0.1_55)]">
        3
      </span>
    );
  }
  return (
    <span className="flex size-7 items-center justify-center text-sm font-medium text-[var(--color-text-muted)]">
      {rank}
    </span>
  );
}

function getInitials(name: string): string {
  return name
    .split(" ")
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

function LeaderboardSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-32" />
      </CardHeader>
      <CardContent className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3">
            <Skeleton className="size-7 rounded-full" />
            <Skeleton className="size-8 rounded-full" />
            <Skeleton className="h-4 w-32 flex-1" />
            <Skeleton className="h-4 w-16" />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export function Leaderboard({ courseId }: LeaderboardProps) {
  const [page, setPage] = useState(1);
  const { user } = useUser();
  const { data: response, isLoading, error } = useLeaderboard(courseId, page);

  if (isLoading) {
    return <LeaderboardSkeleton />;
  }

  if (error) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center py-12 text-center">
          <p className="text-sm text-[var(--color-error)]">
            {error instanceof Error ? error.message : "Failed to load leaderboard"}
          </p>
        </CardContent>
      </Card>
    );
  }

  const entries = response?.data ?? [];
  const meta = response?.meta;

  if (entries.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center py-12 text-center">
          <div className="mb-4 flex size-12 items-center justify-center rounded-full bg-[var(--color-primary-light)]">
            <Trophy className="size-6 text-[var(--color-primary)]" />
          </div>
          <h3 className="font-semibold text-[var(--color-text)]">
            No rankings yet
          </h3>
          <p className="mt-1 max-w-sm text-sm text-[var(--color-text-muted)]">
            Complete quizzes and review flashcards to earn XP and appear on the leaderboard.
          </p>
        </CardContent>
      </Card>
    );
  }

  const currentUserId = user?.id;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Trophy className="size-4" />
          Leaderboard
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        {entries.map((entry) => {
          const isCurrentUser = entry.user_id === currentUserId;
          return (
            <div
              key={entry.user_id}
              className={`flex items-center gap-3 rounded-[var(--radius-md)] px-2 py-2.5 transition-colors duration-[var(--duration-fast)] ${
                isCurrentUser
                  ? "bg-[var(--color-primary-light)]"
                  : "hover:bg-[var(--color-surface-hover)]"
              }`}
            >
              {rankBadge(entry.rank)}
              <Avatar size="sm">
                {entry.avatar_url ? (
                  <AvatarImage src={entry.avatar_url} alt={entry.full_name} />
                ) : null}
                <AvatarFallback>{getInitials(entry.full_name)}</AvatarFallback>
              </Avatar>
              <span
                className={`flex-1 truncate text-sm ${
                  isCurrentUser
                    ? "font-semibold text-[var(--color-text)]"
                    : "font-medium text-[var(--color-text)]"
                }`}
              >
                {entry.full_name}
                {isCurrentUser && (
                  <span className="ml-1.5 text-xs text-[var(--color-text-muted)]">(you)</span>
                )}
              </span>
              <span className="text-sm font-semibold text-[var(--color-primary)]">
                {entry.xp_points.toLocaleString()} XP
              </span>
            </div>
          );
        })}

        {meta && meta.pages > 1 && (
          <div className="flex items-center justify-between border-t border-[var(--color-border)] pt-3 mt-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
            >
              <ChevronLeft className="size-4" />
              Previous
            </Button>
            <span className="text-xs text-[var(--color-text-muted)]">
              Page {meta.page} of {meta.pages}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.min(meta.pages, p + 1))}
              disabled={page >= meta.pages}
            >
              Next
              <ChevronRight className="size-4" />
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
