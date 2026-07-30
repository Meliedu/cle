"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Clock } from "lucide-react";

import { cn } from "@/lib/utils";

interface PlacementTimerProps {
  /** ISO timestamp the server says the attempt closes at. */
  readonly expiresAt: string;
  /** Fired once, when the clock first reaches zero. */
  readonly onExpire: () => void;
}

/** Minutes remaining below which the timer starts drawing attention. */
const WARN_AT_SECONDS = 5 * 60;

function format(total: number): string {
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/**
 * The controlled-timer readout.
 *
 * Counts down against the server's `expires_at` rather than a locally
 * accumulated duration: a tab that sleeps, a laptop that suspends, or a clock
 * the learner changes must not buy extra time, and recomputing from an absolute
 * deadline on every tick is the only version of this that survives all three.
 *
 * It is deliberately not a `role="timer"` live region. A screen reader
 * announcing every second would make the test unusable; the remaining time is
 * announced at coarse milestones instead.
 */
export function PlacementTimer({ expiresAt, onExpire }: PlacementTimerProps) {
  const t = useTranslations("placement.sitting");
  const deadline = new Date(expiresAt).getTime();
  const [remaining, setRemaining] = useState(() =>
    Math.max(0, Math.round((deadline - Date.now()) / 1000))
  );
  const fired = useRef(false);
  // Announce at 10 and 5 minutes and at zero, not continuously.
  const announced = useRef<Set<number>>(new Set());
  const [announcement, setAnnouncement] = useState("");

  useEffect(() => {
    const tick = () => {
      const next = Math.max(0, Math.round((deadline - Date.now()) / 1000));
      setRemaining(next);

      for (const milestone of [600, 300, 0]) {
        if (next <= milestone && !announced.current.has(milestone)) {
          announced.current.add(milestone);
          setAnnouncement(
            milestone === 0
              ? t("timeUp")
              : t("minutesLeft", { minutes: milestone / 60 })
          );
        }
      }

      if (next === 0 && !fired.current) {
        fired.current = true;
        onExpire();
      }
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [deadline, onExpire, t]);

  const warning = remaining <= WARN_AT_SECONDS;

  return (
    <div className="flex items-center gap-2">
      <Clock
        aria-hidden="true"
        className={cn(
          "size-4",
          warning
            ? "text-[var(--color-error)]"
            : "text-[var(--color-text-secondary)]"
        )}
        strokeWidth={1.9}
      />
      <span
        className={cn(
          "text-[15px] font-medium tabular-nums",
          warning ? "text-[var(--color-error)]" : "text-[var(--color-text)]"
        )}
      >
        {format(remaining)}
      </span>
      <span className="sr-only">{t("timeRemainingLabel")}</span>
      {/* Milestone announcements only, so assistive tech is not flooded. */}
      <span role="status" aria-live="polite" className="sr-only">
        {announcement}
      </span>
    </div>
  );
}
