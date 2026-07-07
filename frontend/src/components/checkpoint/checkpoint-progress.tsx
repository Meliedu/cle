"use client";

import { cn } from "@/lib/utils";

interface CheckpointProgressProps {
  /** 1-based index of the active step. */
  readonly current: number;
  /** Total number of steps in the flow. */
  readonly total: number;
  /** Accessible label for the whole progress row (e.g. "Card 2 of 4"). */
  readonly label: string;
}

/**
 * A compact, mobile-first step indicator for the checkpoint card flow: a short
 * text label plus a row of segments that fill as the student advances. Segments
 * are decorative (`aria-hidden`); the `label` carries the real progress for
 * assistive tech via `role="status"`.
 */
export function CheckpointProgress({
  current,
  total,
  label,
}: CheckpointProgressProps) {
  return (
    <div className="space-y-2" role="status" aria-live="polite">
      <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
        {label}
      </p>
      <div className="flex gap-1.5" aria-hidden="true">
        {Array.from({ length: total }, (_, i) => (
          <span
            key={i}
            className={cn(
              "h-1.5 flex-1 rounded-[var(--radius-pill)] transition-colors",
              i < current
                ? "bg-[var(--color-primary)]"
                : "bg-[var(--color-border)]"
            )}
          />
        ))}
      </div>
    </div>
  );
}
