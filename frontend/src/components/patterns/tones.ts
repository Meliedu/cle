import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Info,
  Lock,
  type LucideIcon,
} from "lucide-react";

export type StateTone = "info" | "waiting" | "warning" | "blocked" | "success";

export interface ToneStyle {
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
 * consistently. Consumed by `StateBanner`, and by `EmptyState` for its
 * waiting variant.
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
    // Darker honey-family gold: --color-gold on cream is too faint for a glyph.
    icon: "text-[var(--color-primary-hover)]",
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
