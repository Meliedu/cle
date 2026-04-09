"use client";

import { useEffect, useState } from "react";
import { Zap } from "lucide-react";

interface XPToastProps {
  readonly xpEarned: number;
  readonly newBadges?: readonly string[];
  readonly onDismiss: () => void;
  readonly duration?: number;
}

const BADGE_LABELS: Record<string, string> = {
  first_quiz: "First Quiz",
  perfect_score: "Perfect Score",
  streak_7: "7-Day Streak",
  streak_30: "30-Day Streak",
  flashcard_master: "Flashcard Master",
  speed_learner: "Speed Learner",
};

export function XPToast({
  xpEarned,
  newBadges = [],
  onDismiss,
  duration = 3000,
}: XPToastProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const enterTimer = setTimeout(() => setVisible(true), 10);
    const exitTimer = setTimeout(() => {
      setVisible(false);
      setTimeout(onDismiss, 300);
    }, duration);

    return () => {
      clearTimeout(enterTimer);
      clearTimeout(exitTimer);
    };
  }, [duration, onDismiss]);

  return (
    <div
      role="status"
      aria-live="polite"
      className={`fixed bottom-6 right-6 z-50 transition-all duration-300 ${
        visible
          ? "translate-y-0 opacity-100"
          : "translate-y-4 opacity-0"
      }`}
    >
      <div
        className="flex items-center gap-3 rounded-xl px-5 py-3 shadow-lg"
        style={{
          background: "var(--color-primary-light)",
          border: "1px solid var(--color-primary-muted)",
        }}
      >
        <div
          className="flex h-9 w-9 items-center justify-center rounded-full"
          style={{ background: "var(--color-primary)" }}
        >
          <Zap className="h-5 w-5" style={{ color: "var(--color-text-on-primary)" }} />
        </div>
        <div>
          <p
            className="text-sm font-semibold"
            style={{ color: "var(--color-text)" }}
          >
            +{xpEarned} XP
          </p>
          {newBadges.length > 0 && (
            <p
              className="text-xs"
              style={{ color: "var(--color-text-secondary)" }}
            >
              {newBadges.map((b) => BADGE_LABELS[b] ?? b).join(", ")}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
