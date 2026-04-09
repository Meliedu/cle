"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  BookOpen,
  Flame,
  Trophy,
  Brain,
  Mic,
  Target,
  Star,
  Zap,
  Award,
  Crown,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

interface BadgeDefinition {
  readonly name: string;
  readonly description: string;
  readonly icon: LucideIcon;
}

const BADGE_DEFINITIONS: Record<string, BadgeDefinition> = {
  first_quiz: {
    name: "First Quiz",
    description: "Completed your first quiz",
    icon: BookOpen,
  },
  quiz_master: {
    name: "Quiz Master",
    description: "Completed 10 quizzes",
    icon: Target,
  },
  first_flashcard: {
    name: "First Flashcard",
    description: "Reviewed your first flashcard set",
    icon: Brain,
  },
  flashcard_scholar: {
    name: "Flashcard Scholar",
    description: "Reviewed 50 flashcard sets",
    icon: Star,
  },
  first_speaking: {
    name: "First Speaking",
    description: "Completed your first speaking session",
    icon: Mic,
  },
  streak_3: {
    name: "3-Day Streak",
    description: "Maintained a 3-day learning streak",
    icon: Flame,
  },
  streak_7: {
    name: "Week Warrior",
    description: "Maintained a 7-day learning streak",
    icon: Zap,
  },
  streak_30: {
    name: "Monthly Master",
    description: "Maintained a 30-day learning streak",
    icon: Crown,
  },
  xp_1000: {
    name: "Rising Star",
    description: "Earned 1,000 XP",
    icon: Award,
  },
  xp_5000: {
    name: "Top Achiever",
    description: "Earned 5,000 XP",
    icon: Trophy,
  },
} as const;

interface BadgeDisplayProps {
  readonly badges: readonly string[];
}

export function BadgeDisplay({ badges }: BadgeDisplayProps) {
  const allBadgeIds = Object.keys(BADGE_DEFINITIONS);
  const earnedSet = new Set(badges);

  if (allBadgeIds.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Award className="size-4" />
          Badges
          <span className="text-sm font-normal text-[var(--color-text-muted)]">
            ({badges.length} / {allBadgeIds.length})
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5">
          {allBadgeIds.map((badgeId) => {
            const def = BADGE_DEFINITIONS[badgeId];
            const isEarned = earnedSet.has(badgeId);
            const Icon = def.icon;

            return (
              <div
                key={badgeId}
                className={`flex flex-col items-center gap-2 rounded-[var(--radius-lg)] border border-[var(--color-border)] p-3 text-center transition-all duration-[var(--duration-normal)] ${
                  isEarned
                    ? "bg-[var(--color-surface)] shadow-[var(--shadow-sm)]"
                    : "opacity-40"
                }`}
                title={def.description}
              >
                <div
                  className={`flex size-10 items-center justify-center rounded-full ${
                    isEarned
                      ? "bg-[var(--color-primary-light)] text-[var(--color-primary)]"
                      : "bg-[var(--color-border)] text-[var(--color-text-muted)]"
                  }`}
                >
                  <Icon className="size-5" />
                </div>
                <span
                  className={`text-xs font-medium leading-tight ${
                    isEarned ? "text-[var(--color-text)]" : "text-[var(--color-text-muted)]"
                  }`}
                >
                  {def.name}
                </span>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
