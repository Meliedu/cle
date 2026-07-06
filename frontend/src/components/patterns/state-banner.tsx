import * as React from "react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

import { toneStyles, type StateTone } from "./tones";

export interface StateBannerProps extends React.ComponentProps<"div"> {
  /** Semantic tone; drives icon + color treatment. */
  readonly tone: StateTone;
  /** Short headline describing the state. */
  readonly title: string;
  /** Optional explanation of why the user is seeing this state. */
  readonly reason?: string;
  /** Optional trailing action (link, button). Focus styling is the caller's job. */
  readonly action?: ReactNode;
}

/**
 * Horizontal status banner: tone icon | title + reason | action slot.
 * Announced via `role="alert"` for warning/blocked tones and `role="status"`
 * otherwise; the `waiting` tone adds `aria-live="polite"` so async progress is
 * read out to assistive tech.
 */
export function StateBanner({
  tone,
  title,
  reason,
  action,
  className,
  ...rest
}: StateBannerProps) {
  const { Icon, container, icon } = toneStyles[tone];
  const isUrgent = tone === "warning" || tone === "blocked";

  return (
    <div
      role={isUrgent ? "alert" : "status"}
      aria-live={tone === "waiting" ? "polite" : undefined}
      data-tone={tone}
      className={cn(
        "flex items-start gap-3 rounded-[var(--radius-lg)] border px-4 py-3",
        container,
        className
      )}
      {...rest}
    >
      <Icon
        aria-hidden="true"
        strokeWidth={1.85}
        className={cn("mt-0.5 size-[18px] shrink-0", icon)}
      />

      <div className="min-w-0 flex-1 space-y-0.5">
        <p className="text-[14px] font-semibold leading-snug tracking-tight text-[var(--color-text)]">
          {title}
        </p>
        {reason ? (
          <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
            {reason}
          </p>
        ) : null}
      </div>

      {action ? (
        <div className="flex shrink-0 items-center self-center">{action}</div>
      ) : null}
    </div>
  );
}
