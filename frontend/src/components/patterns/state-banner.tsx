import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Info,
  Lock,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export type StateTone = "info" | "waiting" | "warning" | "blocked" | "success";

interface ToneStyle {
  /** Icon that carries the tone's identity (decorative — always aria-hidden). */
  readonly Icon: LucideIcon;
  /** Container background + border tint for this tone. */
  readonly container: string;
  /** Icon color for this tone. */
  readonly icon: string;
}

/**
 * Single source of truth for tone → visual treatment. One entry per semantic
 * tone so every waiting / blocked / warning surface across the product reads
 * consistently. `EmptyState` reuses the `waiting` entry for its waiting variant.
 */
export const toneStyles: Record<StateTone, ToneStyle> = {
  info: {
    Icon: Info,
    container:
      "border-[var(--color-accent)]/40 bg-[var(--color-accent-light)]",
    icon: "text-[var(--color-accent)]",
  },
  waiting: {
    Icon: Clock,
    container: "border-[var(--color-gold)]/45 bg-[var(--color-cream)]",
    icon: "text-[var(--color-gold)]",
  },
  warning: {
    Icon: AlertTriangle,
    container:
      "border-[var(--color-warning)]/45 bg-[var(--color-warning-light)]",
    icon: "text-[var(--color-warning)]",
  },
  blocked: {
    Icon: Lock,
    container: "border-[var(--color-error)]/35 bg-[var(--color-error-light)]",
    icon: "text-[var(--color-error)]",
  },
  success: {
    Icon: CheckCircle2,
    container:
      "border-[var(--color-success)]/40 bg-[var(--color-success-light)]",
    icon: "text-[var(--color-success)]",
  },
};

export interface StateBannerProps {
  /** Semantic tone; drives icon + color treatment. */
  readonly tone: StateTone;
  /** Short headline describing the state. */
  readonly title: string;
  /** Optional explanation of why the user is seeing this state. */
  readonly reason?: string;
  /** Optional trailing action (link, button). Focus styling is the caller's job. */
  readonly action?: ReactNode;
  readonly className?: string;
}

/**
 * Horizontal status banner: tone icon | title + reason | action slot. Announced
 * via `role="status"`; the `waiting` tone adds `aria-live="polite"` so async
 * progress is read out to assistive tech.
 */
export function StateBanner({
  tone,
  title,
  reason,
  action,
  className,
}: StateBannerProps) {
  const { Icon, container, icon } = toneStyles[tone];

  return (
    <div
      role="status"
      aria-live={tone === "waiting" ? "polite" : undefined}
      data-tone={tone}
      className={cn(
        "flex items-start gap-3 rounded-[var(--radius-lg)] border px-4 py-3",
        container,
        className
      )}
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
