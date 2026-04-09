"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Flame, Trophy, BookOpen, Brain, Mic } from "lucide-react";
import type { ProgressResponse } from "@/hooks/use-progress";

interface ProgressCardProps {
  readonly progress: ProgressResponse | undefined;
  readonly isLoading: boolean;
}

function computeLevel(xp: number): { level: number; currentXp: number; nextLevelXp: number } {
  const level = Math.floor(xp / 1000) + 1;
  const currentXp = xp % 1000;
  const nextLevelXp = 1000;
  return { level, currentXp, nextLevelXp };
}

export function ProgressCard({ progress, isLoading }: ProgressCardProps) {
  if (isLoading) {
    return (
      <Card>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-3">
            <Skeleton className="size-10 rounded-full" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-full" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-16 rounded-[var(--radius-md)]" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!progress) {
    return null;
  }

  const { level, currentXp, nextLevelXp } = computeLevel(progress.xp_points);
  const progressPercent = (currentXp / nextLevelXp) * 100;

  return (
    <Card>
      <CardContent className="space-y-5">
        {/* XP + Level */}
        <div className="flex items-center gap-4">
          <div className="flex size-12 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary-light)]">
            <Trophy className="size-6 text-[var(--color-primary)]" />
          </div>
          <div className="flex-1">
            <div className="flex items-baseline justify-between">
              <h3 className="text-sm font-semibold text-[var(--color-text)]">
                Level {level}
              </h3>
              <span className="text-xs font-medium text-[var(--color-text-muted)]">
                {progress.xp_points.toLocaleString()} XP
              </span>
            </div>
            <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-[var(--color-border)]">
              <div
                className="h-full rounded-full bg-[var(--color-primary)] transition-all duration-[var(--duration-slow)]"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            <p className="mt-1 text-xs text-[var(--color-text-muted)]">
              {currentXp} / {nextLevelXp} XP to next level
            </p>
          </div>
        </div>

        {/* Stats grid */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile
            icon={<Flame className="size-4" />}
            label="Streak"
            value={`${progress.streak_days}d`}
            colorClass="text-[var(--color-warning)]"
            bgClass="bg-[var(--color-warning-light)]"
          />
          <StatTile
            icon={<BookOpen className="size-4" />}
            label="Quizzes"
            value={`${progress.quizzes_completed}`}
            colorClass="text-[var(--color-primary)]"
            bgClass="bg-[var(--color-primary-light)]"
          />
          <StatTile
            icon={<Brain className="size-4" />}
            label="Flashcards"
            value={`${progress.flashcards_reviewed}`}
            colorClass="text-[var(--color-accent)]"
            bgClass="bg-[var(--color-accent-light)]"
          />
          <StatTile
            icon={<Mic className="size-4" />}
            label="Speaking"
            value={`${progress.speaking_sessions}`}
            colorClass="text-[var(--color-success)]"
            bgClass="bg-[var(--color-success-light)]"
          />
        </div>
      </CardContent>
    </Card>
  );
}

interface StatTileProps {
  readonly icon: React.ReactNode;
  readonly label: string;
  readonly value: string;
  readonly colorClass: string;
  readonly bgClass: string;
}

function StatTile({ icon, label, value, colorClass, bgClass }: StatTileProps) {
  return (
    <div className="flex flex-col items-center gap-1.5 rounded-[var(--radius-md)] border border-[var(--color-border)] p-3">
      <div
        className={`flex size-8 items-center justify-center rounded-full ${bgClass} ${colorClass}`}
      >
        {icon}
      </div>
      <span className="text-lg font-bold text-[var(--color-text)]">{value}</span>
      <span className="text-xs text-[var(--color-text-muted)]">{label}</span>
    </div>
  );
}
