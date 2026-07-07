import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Small presentational primitives shared across the teacher-insights surface:
 * a bordered `InsightCard` section wrapper, a `StatTile` figure, and a
 * `ProgressBar` proportion bar. Tokens only — no hardcoded colors.
 */

interface InsightCardProps {
  readonly title: string;
  readonly subtitle?: string;
  readonly icon?: LucideIcon;
  readonly actions?: ReactNode;
  readonly children: ReactNode;
  readonly className?: string;
}

export function InsightCard({
  title,
  subtitle,
  icon: Icon,
  actions,
  children,
  className,
}: InsightCardProps) {
  return (
    <section
      className={cn(
        "space-y-4 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5",
        className
      )}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5">
          {Icon ? (
            <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] text-[var(--color-primary)]">
              <Icon aria-hidden="true" strokeWidth={1.85} className="size-4" />
            </span>
          ) : null}
          <div className="space-y-0.5">
            <h2 className="text-[14px] font-semibold tracking-tight text-[var(--color-text)]">
              {title}
            </h2>
            {subtitle ? (
              <p className="text-[12px] leading-relaxed text-[var(--color-text-muted)]">
                {subtitle}
              </p>
            ) : null}
          </div>
        </div>
        {actions ? <div className="shrink-0">{actions}</div> : null}
      </header>
      {children}
    </section>
  );
}

interface StatTileProps {
  readonly label: string;
  readonly value: ReactNode;
  readonly hint?: string;
  readonly tone?: "default" | "warning" | "critical";
}

export function StatTile({ label, value, hint, tone = "default" }: StatTileProps) {
  const valueColor =
    tone === "critical"
      ? "text-[var(--color-error)]"
      : tone === "warning"
        ? "text-[var(--color-warning)]"
        : "text-[var(--color-text)]";
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--color-border)]/70 bg-[var(--color-surface-hover)] p-3.5">
      <p className="text-[12px] text-[var(--color-text-muted)]">{label}</p>
      <p
        className={cn(
          "mt-1 text-[22px] font-bold leading-tight tracking-tight",
          valueColor
        )}
      >
        {value}
      </p>
      {hint ? (
        <p className="mt-1 text-[11px] leading-snug text-[var(--color-text-muted)]">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

interface ProgressBarProps {
  /** Pre-computed CSS width string, e.g. "62%". */
  readonly width: string;
  readonly tone?: "primary" | "success" | "warning" | "accent";
  readonly label?: string;
}

export function ProgressBar({ width, tone = "primary", label }: ProgressBarProps) {
  const fill =
    tone === "success"
      ? "bg-[var(--color-success)]"
      : tone === "warning"
        ? "bg-[var(--color-warning)]"
        : tone === "accent"
          ? "bg-[var(--color-accent)]"
          : "bg-[var(--color-primary)]";
  return (
    <div
      className="h-2 w-full overflow-hidden rounded-full bg-[var(--color-surface-hover)]"
      role="presentation"
      aria-label={label}
    >
      <div className={cn("h-full rounded-full", fill)} style={{ width }} />
    </div>
  );
}
